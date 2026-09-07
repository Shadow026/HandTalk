#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_classifier.py

REEMPLAZA a train_model.py y train_model_letters.py.

Diferencia clave: aqui NO se entrena una CNN sobre pixeles de un dataset
descargado. Se entrena un clasificador clasico (scikit-learn) sobre los
vectores de landmarks normalizados que el propio usuario grabo con su
camara para SUS palabras/señas personalizadas.

Ventajas de este enfoque para el objetivo pedido (maxima precision,
funcionar igual en interior/exterior):
  - El vector de entrada ya es invariante a fondo, iluminacion, posicion
    y escala (ver hand_features.py), asi que el clasificador no tiene
    que "aprender" a ignorar esas variaciones como si tendria que hacerlo
    una CNN sobre pixeles crudos.
  - Con 63-78 valores numericos por muestra, un RandomForest o una SVM
    aprende muy bien con apenas 20-50 muestras reales por palabra (mas
    la data aumentada sintetica), mientras que una CNN necesitaria miles
    de imagenes por clase para no sobreajustar.
  - Es mucho mas rapido de entrenar (segundos, no hay que instalar/usar
    GPU) y el modelo resultante pesa unos pocos KB/MB en vez de cientos
    de MB.
"""

import argparse
import json
import os

import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report
import joblib

import dataset_manager

MODELS_DIR = "./models"


def train(dataset_dir, model_type="random_forest", augment_factor=20,
          test_size=0.2, models_dir=MODELS_DIR):
    os.makedirs(models_dir, exist_ok=True)

    words = dataset_manager.get_existing_words(dataset_dir)
    if len(words) < 2:
        raise RuntimeError(
            "Se necesitan al menos 2 palabras/señas distintas capturadas "
            f"para entrenar. Encontradas: {words}"
        )

    print(f"Palabras encontradas ({len(words)}): {', '.join(words)}")
    for w in words:
        print(f"  - {w}: {dataset_manager.count_samples_for_word(w, dataset_dir)} muestras reales")

    X, y_labels = dataset_manager.build_training_arrays(
        dataset_dir, augment_factor=augment_factor
    )
    print(f"\\nTotal de muestras tras aumentacion: {len(X)}")

    encoder = LabelEncoder()
    y = encoder.fit_transform(y_labels)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    if model_type == "mlp":
        clf = MLPClassifier(
            hidden_layer_sizes=(128, 64),
            activation="relu",
            max_iter=2000,
            random_state=42,
        )
    else:
        clf = RandomForestClassifier(
            n_estimators=300,
            max_depth=None,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )

    print(f"\\nEntrenando modelo ({model_type})...")
    clf.fit(X_train, y_train)

    scores = cross_val_score(clf, X_train, y_train, cv=5)
    print(f"Precision validacion cruzada (5-fold): {scores.mean()*100:.2f}% (+/- {scores.std()*100:.2f}%)")

    y_pred = clf.predict(X_test)
    print("\\nReporte de clasificacion (conjunto de prueba):")
    print(classification_report(y_test, y_pred, target_names=encoder.classes_))

    model_path = os.path.join(models_dir, "custom_sign_model.pkl")
    encoder_path = os.path.join(models_dir, "custom_sign_labels.pkl")
    meta_path = os.path.join(models_dir, "custom_sign_meta.json")

    joblib.dump(clf, model_path)
    joblib.dump(encoder, encoder_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "model_type": model_type,
            "feature_length": X.shape[1],
            "words": list(encoder.classes_),
        }, f, ensure_ascii=False, indent=2)

    print(f"\\nModelo guardado en: {model_path}")
    print(f"Codificador de etiquetas guardado en: {encoder_path}")
    print(f"Metadatos guardados en: {meta_path}")

    return clf, encoder


def main():
    parser = argparse.ArgumentParser(description="Entrena el clasificador de señas personalizadas")
    parser.add_argument("--dataset", default=dataset_manager.DEFAULT_DATASET_DIR)
    parser.add_argument("--model", choices=["random_forest", "mlp"], default="random_forest")
    parser.add_argument("--augment", type=int, default=20, help="Muestras sinteticas por muestra real")
    parser.add_argument("--models-dir", default=MODELS_DIR)
    args = parser.parse_args()

    train(args.dataset, args.model, args.augment, models_dir=args.models_dir)


if __name__ == "__main__":
    main()
