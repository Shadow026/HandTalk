#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_classifier.py

REEMPLAZA a train_model.py y train_model_letters.py.

Diferencia clave: aqui NO se entrena una CNN sobre pixeles de un dataset
descargado. Se entrena un clasificador clasico (scikit-learn) sobre los
vectores de landmarks normalizados que el propio usuario grabo con su
camara para SUS palabras/señas personalizadas.
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
import temporal_pooling

MODELS_DIR = "./models"


def train_core(X, y_labels, model_type, augment_factor, test_size):
    """Lógica interna de entrenamiento compartida para estáticos y dinámicos."""
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

    clf.fit(X_train, y_train)
    scores = cross_val_score(clf, X_train, y_train, cv=5)

    y_pred = clf.predict(X_test)
    print(classification_report(y_test, y_pred, target_names=encoder.classes_))

    return clf, encoder, scores.mean()


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

    # ------------------------------------------------------------------
    # 1. ENTRENAMIENTO ESTÁTICO
    # ------------------------------------------------------------------
    print("\n--- Entrenando Modelo Estático ---")
    X_stat, y_stat = dataset_manager.build_training_arrays(
        dataset_dir, augment_factor=augment_factor
    )

    # Verificación robusta para evitar el error de "truth value of an array"
    if X_stat is not None and (isinstance(X_stat, list) and len(X_stat) > 0 or
                              isinstance(X_stat, np.ndarray) and X_stat.size > 0):
        clf_s, enc_s, score_s = train_core(X_stat, y_stat, model_type, augment_factor, test_size)

        joblib.dump(clf_s, os.path.join(models_dir, "custom_sign_model.pkl"))
        joblib.dump(enc_s, os.path.join(models_dir, "custom_sign_labels.pkl"))
        with open(os.path.join(models_dir, "custom_sign_meta.json"), "w", encoding="utf-8") as f:
            json.dump({
                "model_type": model_type,
                "feature_length": X_stat.shape[1] if hasattr(X_stat, 'shape') else len(X_stat[0]),
                "words": list(enc_s.classes_),
                "type": "static"
            }, f, ensure_ascii=False, indent=2)
        print(f"Modelo estático guardado. Precision: {score_s*100:.2f}%")
    else:
        print("No se encontraron muestras estáticas.")

    # ------------------------------------------------------------------
    # 2. ENTRENAMIENTO DINÁMICO
    # ------------------------------------------------------------------
    print("\n--- Entrenando Modelo Dinámico ---")
    X_dyn_raw, y_dyn_raw = dataset_manager.load_dataset(dataset_dir, sample_type="dynamic")

    # Verificación simple sobre la longitud de la lista para evitar ambigüedad de NumPy
    if X_dyn_raw is not None and len(X_dyn_raw) > 0:
        # Aplicar Temporal Pooling: convertir secuencias en vectores resumen
        X_dyn_pooled = np.array([temporal_pooling.pool_sequence(s) for s in X_dyn_raw])

        # Aumentación sintética simple para dinámicos (ruido gaussiano)
        X_dyn, y_dyn = [], []
        for feat, label in zip(X_dyn_pooled, y_dyn_raw):
            X_dyn.append(feat)
            y_dyn.append(label)
            # Generamos algunas variaciones para evitar sobreajuste
            for _ in range(augment_factor // 2): # Menos aumentación que en estáticos
                noise = np.random.normal(0, 0.01, size=feat.shape).astype(np.float32)
                X_dyn.append(feat + noise)
                y_dyn.append(label)

        X_dyn = np.array(X_dyn)
        y_dyn = np.array(y_dyn)

        clf_d, enc_d, score_d = train_core(X_dyn, y_dyn, model_type, augment_factor, test_size)

        joblib.dump(clf_d, os.path.join(models_dir, "custom_sign_model_dinamico.pkl"))
        joblib.dump(enc_d, os.path.join(models_dir, "custom_sign_labels_dinamico.pkl"))
        with open(os.path.join(models_dir, "custom_sign_meta_dinamico.json"), "w", encoding="utf-8") as f:
            json.dump({
                "model_type": model_type,
                "feature_length": X_dyn.shape[1] if hasattr(X_dyn, 'shape') else len(X_dyn[0]),
                "words": list(enc_d.classes_),
                "type": "dynamic"
            }, f, ensure_ascii=False, indent=2)
        print(f"Modelo dinámico guardado. Precision: {score_d*100:.2f}%")
    else:
        print("No se encontraron muestras dinámicas.")

    return clf_s if 'clf_s' in locals() else None, enc_s if 'enc_s' in locals() else None


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
