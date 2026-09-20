#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_classifier.py

REEMPLAZA a train_model.py y train_model_letters.py.

Diferencia clave: aqui NO se entrena una CNN sobre pixeles de un dataset
descargado. Se entrena un clasificador clasico (scikit-learn) sobre los
vectores de landmarks normalizados que el propio usuario grabo con su
camara para SUS palabras/señas personalizadas.

NUEVO:
  - Entrena AMBOS modelos (estatico y dinamico) en una sola corrida,
    detectando automaticamente con dataset_manager.get_available_types()
    que tipos de muestra existen en el dataset. Si solo hay estaticas,
    solo entrena ese modelo (comportamiento identico al original); si
    tambien hay dinamicas, entrena un segundo modelo por separado
    (custom_sign_model_dinamico.pkl), sin mezclar ambos tipos en un
    mismo vector de entrada.
  - Las senas dinamicas se resumen con temporal_pooling.pool_sequence()
    (promedio + desviacion + delta inicio-fin) antes de entrenar, para
    poder seguir usando el mismo tipo de clasificador (RandomForest/MLP)
    sin necesitar una red recurrente.
  - Se reutiliza dataset_manager.augment_static_sample() tambien para
    los vectores dinamicos ya "pooled": despues del pooling son vectores
    planos de la misma naturaleza que los estaticos, asi que la misma
    funcion de aumento de datos sirve sin duplicar logica.

Ventajas del enfoque original para el objetivo pedido (maxima precision,
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
from sklearn.metrics import classification_report, confusion_matrix
import joblib

import dataset_manager
from temporal_pooling import pool_sequence

MODELS_DIR = "./models"


def _crear_clasificador(model_type):
    if model_type == "mlp":
        return MLPClassifier(
            hidden_layer_sizes=(128, 64),
            activation="relu",
            max_iter=2000,
            random_state=42,
        )
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )


def train_static(dataset_dir, model_type="random_forest", augment_factor=20,
                  test_size=0.2, models_dir=MODELS_DIR):
    """Entrena el modelo de señas ESTÁTICAS. Comportamiento idéntico al
    train_classifier.py original -- no se tocó esta parte."""
    words = dataset_manager.get_existing_words(dataset_dir)
    print(f"\n{'='*60}\nENTRENANDO MODELO ESTÁTICO\n{'='*60}")
    print(f"Palabras encontradas ({len(words)}): {', '.join(words)}")
    for w in words:
        print(f"  - {w}: {dataset_manager.count_samples_for_word(w, dataset_dir)} muestras reales")

    X, y_labels = dataset_manager.build_training_arrays(dataset_dir, augment_factor=augment_factor)
    print(f"\nTotal de muestras tras aumentación: {len(X)}")

    encoder = LabelEncoder()
    y = encoder.fit_transform(y_labels)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    clf = _crear_clasificador(model_type)
    print(f"\nEntrenando modelo ({model_type})...")
    clf.fit(X_train, y_train)

    scores = cross_val_score(clf, X_train, y_train, cv=5)
    print(f"Precisión validación cruzada (5-fold): {scores.mean()*100:.2f}% (+/- {scores.std()*100:.2f}%)")

    y_pred = clf.predict(X_test)
    print("\nReporte de clasificación (conjunto de prueba):")
    print(classification_report(y_test, y_pred, target_names=encoder.classes_))

    os.makedirs(models_dir, exist_ok=True)
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

    print(f"\nModelo guardado en: {model_path}")
    print(f"Codificador de etiquetas guardado en: {encoder_path}")
    print(f"Metadatos guardados en: {meta_path}")

    return clf, encoder


def train_dynamic(dataset_dir, model_type="random_forest", augment_factor=20,
                   test_size=0.2, models_dir=MODELS_DIR):
    """
    Entrena el modelo de señas DINÁMICAS (con movimiento).
    Cada secuencia se resume con pool_sequence() antes de entrenar, y
    luego se reutiliza augment_static_sample() sobre esos vectores ya
    planos para compensar que las secuencias son más lentas de capturar
    (normalmente hay menos muestras reales que en el caso estático).
    """
    secuencias, etiquetas = dataset_manager.load_dataset(dataset_dir, sample_type="dynamic")

    print(f"\n{'='*60}\nENTRENANDO MODELO DINÁMICO\n{'='*60}")
    palabras = sorted(set(etiquetas))
    print(f"Palabras dinámicas encontradas ({len(palabras)}): {', '.join(palabras)}")
    for w in palabras:
        cantidad = sum(1 for e in etiquetas if e == w)
        print(f"  - {w}: {cantidad} secuencias reales")

    if len(palabras) < 2:
        print("\n[AVISO] Se necesitan al menos 2 señas dinámicas distintas para entrenar. Se omite este modelo.")
        return None, None

    X, y_labels = [], []
    for secuencia, etiqueta in zip(secuencias, etiquetas):
        vector_pooled = pool_sequence(secuencia)
        X.append(vector_pooled)
        y_labels.append(etiqueta)

        if augment_factor > 0:
            for variante in dataset_manager.augment_static_sample(
                vector_pooled, augment_factor, noise_std=0.01, scale_range=0.05
            ):
                X.append(variante)
                y_labels.append(etiqueta)

    X = np.array(X, dtype=np.float32)
    print(f"\nTotal de muestras tras aumentación: {len(X)}")

    encoder = LabelEncoder()
    y = encoder.fit_transform(y_labels)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    clf = _crear_clasificador(model_type)
    print(f"\nEntrenando modelo dinámico ({model_type})...")
    clf.fit(X_train, y_train)

    scores = cross_val_score(clf, X_train, y_train, cv=5)
    print(f"Precisión validación cruzada (5-fold): {scores.mean()*100:.2f}% (+/- {scores.std()*100:.2f}%)")

    y_pred = clf.predict(X_test)
    print("\nReporte de clasificación (conjunto de prueba):")
    print(classification_report(y_test, y_pred, target_names=encoder.classes_))
    print("Matriz de confusión:")
    print(confusion_matrix(y_test, y_pred))

    os.makedirs(models_dir, exist_ok=True)
    model_path = os.path.join(models_dir, "custom_sign_model_dinamico.pkl")
    encoder_path = os.path.join(models_dir, "custom_sign_labels_dinamico.pkl")
    meta_path = os.path.join(models_dir, "custom_sign_meta_dinamico.json")

    joblib.dump(clf, model_path)
    joblib.dump(encoder, encoder_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "model_type": model_type,
            "feature_length": int(X.shape[1]),
            "words": list(encoder.classes_),
            "tipo": "dynamic",
            "pooling": "mean+std+delta",
        }, f, ensure_ascii=False, indent=2)

    print(f"\nModelo dinámico guardado en: {model_path}")
    print(f"Codificador de etiquetas guardado en: {encoder_path}")
    print(f"Metadatos guardados en: {meta_path}")

    return clf, encoder


def train(dataset_dir, model_type="random_forest", augment_factor=20,
          test_size=0.2, models_dir=MODELS_DIR, solo_estatico=False, solo_dinamico=False):
    """
    Punto de entrada principal: detecta qué tipos de muestra hay en el
    dataset y entrena el/los modelo(s) correspondientes.
    """
    tipos_disponibles = dataset_manager.get_available_types(dataset_dir)

    if not tipos_disponibles:
        raise RuntimeError(f"No se encontraron muestras en '{dataset_dir}'. Captura señas primero.")

    entrenar_estatico = "static" in tipos_disponibles and not solo_dinamico
    entrenar_dinamico = "dynamic" in tipos_disponibles and not solo_estatico

    resultados = {}

    if entrenar_estatico:
        words = dataset_manager.get_existing_words(dataset_dir)
        # get_existing_words no distingue tipo, así que se valida con al
        # menos 2 palabras dentro de las muestras estáticas específicamente.
        _, y_static = dataset_manager.load_dataset(dataset_dir, sample_type="static")
        if len(set(y_static)) < 2:
            print("\n[AVISO] Se necesitan al menos 2 palabras estáticas distintas para entrenar. Se omite este modelo.")
        else:
            resultados["static"] = train_static(
                dataset_dir, model_type, augment_factor, test_size, models_dir
            )

    if entrenar_dinamico:
        resultados["dynamic"] = train_dynamic(
            dataset_dir, model_type, augment_factor, test_size, models_dir
        )

    if not resultados:
        print("\n[AVISO] No se entrenó ningún modelo. Revisa que haya al menos 2 palabras por tipo.")

    return resultados


def main():
    parser = argparse.ArgumentParser(description="Entrena el/los clasificador(es) de señas personalizadas")
    parser.add_argument("--dataset", default=dataset_manager.DEFAULT_DATASET_DIR)
    parser.add_argument("--model", choices=["random_forest", "mlp"], default="random_forest")
    parser.add_argument("--augment", type=int, default=20, help="Muestras sintéticas por muestra real")
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--solo-estatico", action="store_true", help="Entrena solo el modelo estático, aunque haya dinámicas")
    parser.add_argument("--solo-dinamico", action="store_true", help="Entrena solo el modelo dinámico, aunque haya estáticas")
    args = parser.parse_args()

    train(
        args.dataset, args.model, args.augment,
        models_dir=args.models_dir,
        solo_estatico=args.solo_estatico,
        solo_dinamico=args.solo_dinamico,
    )


if __name__ == "__main__":
    main()