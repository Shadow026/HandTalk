#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_classifier.py

Entrenador polimórfico que soporta señas de una y dos manos separadamente.
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
import hand_features

MODELS_DIR = "./models"


def train_core(X, y_labels, model_type, augment_factor, test_size):
    """Lógica interna de entrenamiento compartida."""
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
        raise RuntimeError(f"Se necesitan al menos 2 palabras distintas. Encontradas: {words}")

    print(f"Palabras encontradas ({len(words)}): {', '.join(words)}")
    single_hand_len = hand_features.feature_vector_length(two_hands=False)

    # ------------------------------------------------------------------
    # 1. ENTRENAMIENTO ESTÁTICO
    # ------------------------------------------------------------------
    print("\n--- Entrenando Modelos Estáticos ---")
    X_stat_raw, y_stat_raw = dataset_manager.build_training_arrays(
        dataset_dir, augment_factor=augment_factor
    )

    if X_stat_raw is not None and len(X_stat_raw) > 0:
        X_1h, y_1h = [], []
        X_2h, y_2h = [], []

        for x, y in zip(X_stat_raw, y_stat_raw):
            if len(x) == single_hand_len:
                X_1h.append(x)
                y_1h.append(y)
            elif len(x) == single_hand_len * 2:
                X_2h.append(x)
                y_2h.append(y)

        if len(X_1h) >= 2:
            clf_s, enc_s, score_s = train_core(np.array(X_1h), y_1h, model_type, augment_factor, test_size)
            joblib.dump(clf_s, os.path.join(models_dir, "custom_sign_model.pkl"))
            joblib.dump(enc_s, os.path.join(models_dir, "custom_sign_labels.pkl"))
            with open(os.path.join(models_dir, "custom_sign_meta.json"), "w", encoding="utf-8") as f:
                json.dump({"model_type": model_type, "feature_length": single_hand_len, "words": list(enc_s.classes_), "type": "static"}, f, ensure_ascii=False, indent=2)
            print(f"Modelo estático (1 mano) guardado. Precision: {score_s*100:.2f}%")

        if len(X_2h) >= 2:
            clf_2h, enc_2h, score_2h = train_core(np.array(X_2h), y_2h, model_type, augment_factor, test_size)
            joblib.dump(clf_2h, os.path.join(models_dir, "custom_sign_model_two_hands.pkl"))
            joblib.dump(enc_2h, os.path.join(models_dir, "custom_sign_labels_two_hands.pkl"))
            with open(os.path.join(models_dir, "custom_sign_meta_two_hands.json"), "w", encoding="utf-8") as f:
                json.dump({"model_type": model_type, "feature_length": single_hand_len * 2, "words": list(enc_2h.classes_), "type": "static_two_hands"}, f, ensure_ascii=False, indent=2)
            print(f"Modelo estático (2 manos) guardado. Precision: {score_2h*100:.2f}%")
    else:
        print("No se encontraron muestras estáticas.")

    # ------------------------------------------------------------------
    # 2. ENTRENAMIENTO DINÁMICO
    # ------------------------------------------------------------------
    print("\n--- Entrenando Modelos Dinámicos ---")
    X_dyn_raw, y_dyn_raw = dataset_manager.load_dataset(dataset_dir, sample_type="dynamic")

    if X_dyn_raw is not None and len(X_dyn_raw) > 0:
        X_dyn_1h, y_dyn_1h = [], []
        X_dyn_2h, y_dyn_2h = [], []

        for seq, label in zip(X_dyn_raw, y_dyn_raw):
            # Usamos el primer frame de la secuencia para determinar la dimensionalidad
            first_frame_len = len(seq[0])
            pooled = temporal_pooling.pool_sequence(seq)

            if first_frame_len == single_hand_len:
                X_dyn_1h.append(pooled)
                y_dyn_1h.append(label)
            elif first_frame_len == single_hand_len * 2:
                X_dyn_2h.append(pooled)
                y_dyn_2h.append(label)

        # Entrenamiento Modelo Dinámico 1 Mano
        if len(X_dyn_1h) >= 2:
            # Aumentación simple
            final_X, final_y = [], []
            for feat, label in zip(X_dyn_1h, y_dyn_1h):
                final_X.append(feat)
                final_y.append(label)
                for _ in range(augment_factor // 2):
                    final_X.append(feat + np.random.normal(0, 0.01, size=feat.shape).astype(np.float32))
                    final_y.append(label)

            clf_d, enc_d, score_d = train_core(np.array(final_X), np.array(final_y), model_type, augment_factor, test_size)
            joblib.dump(clf_d, os.path.join(models_dir, "custom_sign_model_dinamico.pkl"))
            joblib.dump(enc_d, os.path.join(models_dir, "custom_sign_labels_dinamico.pkl"))
            with open(os.path.join(models_dir, "custom_sign_meta_dinamico.json"), "w", encoding="utf-8") as f:
                json.dump({"model_type": model_type, "feature_length": single_hand_len, "words": list(enc_d.classes_), "type": "dynamic"}, f, ensure_ascii=False, indent=2)
            print(f"Modelo dinámico (1 mano) guardado. Precision: {score_d*100:.2f}%")

        # Entrenamiento Modelo Dinámico 2 Manos
        if len(X_dyn_2h) >= 2:
            final_X_2h, final_y_2h = [], []
            for feat, label in zip(X_dyn_2h, y_dyn_2h):
                final_X_2h.append(feat)
                final_y_2h.append(label)
                for _ in range(augment_factor // 2):
                    final_X_2h.append(feat + np.random.normal(0, 0.01, size=feat.shape).astype(np.float32))
                    final_y_2h.append(label)

            clf_d2, enc_d2, score_d2 = train_core(np.array(final_X_2h), np.array(final_y_2h), model_type, augment_factor, test_size)
            joblib.dump(clf_d2, os.path.join(models_dir, "custom_sign_model_dinamico_two_hands.pkl"))
            joblib.dump(enc_d2, os.path.join(models_dir, "custom_sign_labels_dinamico_two_hands.pkl"))
            with open(os.path.join(models_dir, "custom_sign_meta_dinamico_two_hands.json"), "w", encoding="utf-8") as f:
                json.dump({"model_type": model_type, "feature_length": single_hand_len * 2, "words": list(enc_d2.classes_), "type": "dynamic_two_hands"}, f, ensure_ascii=False, indent=2)
            print(f"Modelo dinámico (2 manos) guardado. Precision: {score_d2*100:.2f}%")
    else:
        print("No se encontraron muestras dinámicas.")


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
