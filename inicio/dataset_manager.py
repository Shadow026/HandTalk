#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dataset_manager.py

RESCATADO Y GENERALIZADO de sign_language_capture_gui.py:
  - save_sample(), get_existing_words(), count_samples_for_word(),
    delete_word() -> aqui sin dependencia de Tkinter/messagebox.

NUEVO:
  - load_dataset(): arma X, y listos para entrenar.
  - augment_static_sample(): como el usuario ya no usa un dataset publico
    de miles de imagenes sino que graba sus propias señas (pocas decenas
    de muestras), esta funcion genera variaciones sinteticas realistas
    (pequeños giros, escalados y ruido) de cada muestra para que el
    clasificador generalice mejor con poca data real. Esto reemplaza al
    ImageDataGenerator que usaban train_model.py / train_model_letters.py,
    pero operando sobre landmarks en vez de pixeles (mucho mas barato y
    no depende de fondo/iluminacion de la imagen original).
"""

import os
import json
import glob
from datetime import datetime

import numpy as np

DEFAULT_DATASET_DIR = "custom_dataset"


def ensure_dataset_dir(dataset_dir=DEFAULT_DATASET_DIR):
    os.makedirs(dataset_dir, exist_ok=True)
    return dataset_dir


def save_sample(features, label, sample_type="static", dataset_dir=DEFAULT_DATASET_DIR):
    """
    Guarda una muestra (una seña) como JSON.
    features: lista/array de floats (estatica) o lista de listas (dinamica,
              una lista de vectores de features por frame).
    """
    ensure_dataset_dir(dataset_dir)
    existing = count_samples_for_word(label, dataset_dir)

    sample = {
        "label": label,
        "type": sample_type,
        "features": np.asarray(features).tolist(),
        "timestamp": datetime.now().isoformat(),
    }

    filename = os.path.join(dataset_dir, f"{label}_{existing}_{sample_type}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(sample, f)
    return filename


def get_existing_words(dataset_dir=DEFAULT_DATASET_DIR):
    if not os.path.exists(dataset_dir):
        return []
    words = set()
    for filename in os.listdir(dataset_dir):
        if filename.endswith(".json"):
            parts = filename.replace(".json", "").split("_")
            if len(parts) >= 3:
                word = "_".join(parts[:-2])  # todo menos indice y tipo
                if word:
                    words.add(word)
    return sorted(words)


def count_samples_for_word(word, dataset_dir=DEFAULT_DATASET_DIR):
    if not os.path.exists(dataset_dir):
        return 0
    return len(glob.glob(os.path.join(dataset_dir, f"{word}_*.json")))


def delete_word(word, dataset_dir=DEFAULT_DATASET_DIR):
    removed = 0
    for path in glob.glob(os.path.join(dataset_dir, f"{word}_*.json")):
        os.remove(path)
        removed += 1
    return removed


def load_dataset(dataset_dir=DEFAULT_DATASET_DIR, sample_type=None):
    """
    Carga todas las muestras del dataset.
    sample_type: None = todas, "static" o "dynamic" para filtrar.
    Devuelve (X, y) donde:
      - para "static": X es lista de vectores 1D (todos del mismo largo).
      - para "dynamic": X es lista de secuencias (listas de vectores).
    """
    X, y = [], []
    if not os.path.exists(dataset_dir):
        return X, y

    for path in sorted(glob.glob(os.path.join(dataset_dir, "*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            sample = json.load(f)
        if sample_type and sample.get("type") != sample_type:
            continue
        X.append(np.array(sample["features"], dtype=np.float32))
        y.append(sample["label"])

    return X, y


def augment_static_sample(feature_vector, n_augmentations=20,
                           noise_std=0.01, scale_range=0.05):
    """
    Genera variaciones sinteticas de un vector de features estatico
    (landmarks ya normalizados + angulos + distancias) añadiendo:
      - ruido gaussiano pequeño (simula temblor de mano / imprecision de
        deteccion de MediaPipe)
      - una pequeña variacion de escala global (simula pequeñas
        diferencias de distancia a la camara que la normalizacion no
        elimina del todo)
    No se reconstruye una imagen ni se re-renderiza nada: se trabaja
    directo sobre el vector numerico, por eso es rapido (miles de
    variantes en milisegundos) y no arrastra artefactos de fondo/luz.
    """
    augmented = []
    base = np.asarray(feature_vector, dtype=np.float32)
    for _ in range(n_augmentations):
        scale = 1.0 + np.random.uniform(-scale_range, scale_range)
        noise = np.random.normal(0, noise_std, size=base.shape).astype(np.float32)
        augmented.append(base * scale + noise)
    return augmented


def build_training_arrays(dataset_dir=DEFAULT_DATASET_DIR, augment_factor=20,
                           noise_std=0.01, scale_range=0.05):
    """
    Carga las muestras estaticas del dataset, las aumenta y devuelve
    arrays numpy listos para entrenar (X, y_labels).
    """
    X_raw, y_raw = load_dataset(dataset_dir, sample_type="static")

    X, y = [], []
    for feat, label in zip(X_raw, y_raw):
        X.append(feat)
        y.append(label)
        if augment_factor > 0:
            for aug in augment_static_sample(feat, augment_factor, noise_std, scale_range):
                X.append(aug)
                y.append(label)

    return np.array(X, dtype=np.float32), np.array(y)
