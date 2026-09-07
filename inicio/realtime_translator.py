#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realtime_translator.py

REEMPLAZA a translator_realtime.py, translator_unified.py y
translator_headless.py, unificando su logica en un solo traductor que
funciona con CUALQUIER conjunto de palabras que el usuario haya definido
(ya no hay "digitos" ni "letras" hardcodeados).

RESCATADO de los traductores originales:
  - Apertura de camara con fallback (ahora en camera_utils.open_camera)
  - Deteccion de manos con MediaPipe y umbrales altos de confianza
    (0.85 deteccion / 0.75 tracking) para evitar falsos positivos
  - Dibujo de landmarks y bounding box
  - Sistema de confirmacion por frames consecutivos (ahora en smoothing.py)
"""

import argparse
import json
import os
import time

import cv2
import mediapipe as mp
import joblib

import camera_utils
import hand_features
from smoothing import PredictionSmoother

MODELS_DIR = "./models"


class CustomSignTranslator:
    def __init__(self, models_dir=MODELS_DIR, max_hands=1, rotate_invariant=True,
                 confidence_threshold=0.75):
        model_path = os.path.join(models_dir, "custom_sign_model.pkl")
        encoder_path = os.path.join(models_dir, "custom_sign_labels.pkl")
        meta_path = os.path.join(models_dir, "custom_sign_meta.json")

        for p in (model_path, encoder_path, meta_path):
            if not os.path.exists(p):
                raise FileNotFoundError(
                    f"No se encontro {p}. Primero entrena un modelo con train_classifier.py"
                )

        self.model = joblib.load(model_path)
        self.encoder = joblib.load(encoder_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)

        self.max_hands = max_hands
        self.rotate_invariant = rotate_invariant

        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=0.85,
            min_tracking_confidence=0.75,
        )

        self.smoother = PredictionSmoother(confidence_threshold=confidence_threshold)
        self.history = []

    def predict(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        if not results.multi_hand_landmarks:
            self.smoother.reset()
            return None, 0.0, results, None

        if self.max_hands == 1:
            features = hand_features.build_feature_vector(
                results.multi_hand_landmarks[0], rotate=self.rotate_invariant
            )
        else:
            features = hand_features.build_two_hand_feature_vector(
                results.multi_hand_landmarks,
                getattr(results, "multi_handedness", None),
                rotate=self.rotate_invariant,
            )

        expected_len = self.meta["feature_length"]
        if len(features) != expected_len:
            # El modelo fue entrenado con otra configuracion (p.ej. 1 vs 2 manos)
            return None, 0.0, results, None

        probs = self.model.predict_proba([features])[0]
        best_idx = probs.argmax()
        label = self.encoder.inverse_transform([best_idx])[0]
        confidence = float(probs[best_idx])

        confirmed, avg_conf = self.smoother.update(label, confidence)
        if confirmed:
            self.history.append(confirmed)

        return label, confidence, results, confirmed

    def draw_overlay(self, frame, label, confidence, results, confirmed):
        if results and results.multi_hand_landmarks:
            for hand_lm in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame, hand_lm, self.mp_hands.HAND_CONNECTIONS)

        if label:
            cv2.putText(frame, f"{label} ({confidence*100:.0f}%)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, (100, 100, 100), 2)
        else:
            cv2.putText(frame, "Muestra tu mano", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)

        if confirmed:
            cv2.putText(frame, f"CONFIRMADO: {confirmed}", (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 0), 3)

        return frame

    def run_webcam(self, camera_id=None):
        cap, resolved_id = camera_utils.open_camera(camera_id)
        if cap is None:
            print("[ERROR] No se encontro ninguna camara disponible")
            return

        print(f"[OK] Camara {resolved_id} abierta. Presiona Q para salir, S para guardar captura.")
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[ERROR] No se pudo leer un frame de la camara")
                    break

                frame = cv2.flip(frame, 1)
                label, confidence, results, confirmed = self.predict(frame)
                frame = self.draw_overlay(frame, label, confidence, results, confirmed)

                cv2.imshow("Traductor de Senas Personalizado", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q")):
                    break
                elif key in (ord("s"), ord("S")):
                    fname = f"captura_{int(time.time())}.jpg"
                    cv2.imwrite(fname, frame)
                    print(f"[OK] Imagen guardada: {fname}")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            print(f"\\n[OK] Historial de traduccion: {' '.join(self.history[-20:])}")


def main():
    parser = argparse.ArgumentParser(description="Traductor de señas personalizado en tiempo real")
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--hands", type=int, choices=[1, 2], default=1)
    args = parser.parse_args()

    translator = CustomSignTranslator(models_dir=args.models_dir, max_hands=args.hands)
    translator.run_webcam(camera_id=args.camera)


if __name__ == "__main__":
    main()
