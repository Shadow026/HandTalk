#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realtime_translator.py

TRADUCTOR UNIFICADO CON SOPORTE PARA SEÑAS ESTÁTICAS Y DINÁMICAS.

Lógica de inferencia:
1. Detecta si hay movimiento significativo en la muñeca.
2. Si hay movimiento -> Inicia grabación de secuencia -> Usa modelo dinámico.
3. Si no hay movimiento -> Usa modelo estático.
4. Confirma la seña solo cuando el movimiento cesa (en modo dinámico).
"""

import argparse
import json
import os
import time
import numpy as np

import cv2
import mediapipe as mp
import joblib

import camera_utils
import hand_features
import temporal_pooling
from smoothing import PredictionSmoother

MODELS_DIR = "./models"
NOMBRE_VENTANA = "Traductor de Senas Personalizado"

class CustomSignTranslator:
    def __init__(self, models_dir=MODELS_DIR, max_hands=2, rotate_invariant=True,
                 confidence_threshold=0.75, mode="auto"):
        # --- Modelos Estáticos ---
        self.model_s_path = os.path.join(models_dir, "custom_sign_model.pkl")
        self.encoder_s_path = os.path.join(models_dir, "custom_sign_labels.pkl")
        self.meta_s_path = os.path.join(models_dir, "custom_sign_meta.json")

        self.mode = mode # "auto", "estatico", "dinamico"

        # --- Modelos Dinámicos ---
        self.model_d_path = os.path.join(models_dir, "custom_sign_model_dinamico.pkl")
        self.encoder_d_path = os.path.join(models_dir, "custom_sign_labels_dinamico.pkl")
        self.meta_d_path = os.path.join(models_dir, "custom_sign_meta_dinamico.json")

        # Modelos de Dos Manos (Opcionales)
        self.model_2h_path = os.path.join(models_dir, "custom_sign_model_two_hands.pkl")
        self.encoder_2h_path = os.path.join(models_dir, "custom_sign_labels_two_hands.pkl")
        self.meta_2h_path = os.path.join(models_dir, "custom_sign_meta_two_hands.json")

        # Cargar modelos estáticos (Obligatorios)
        for p in (self.model_s_path, self.encoder_s_path, self.meta_s_path):
            if not os.path.exists(p):
                raise FileNotFoundError(f"No se encontro {p}. Entrena primero el modelo.")

        self.model_s = joblib.load(self.model_s_path)
        self.encoder_s = joblib.load(self.encoder_s_path)
        with open(self.meta_s_path, "r", encoding="utf-8") as f:
            self.meta_s = json.load(f)

        # Cargar modelos dinámicos (Opcionales)
        self.model_d = None
        self.encoder_d = None
        if os.path.exists(self.model_d_path) and os.path.exists(self.encoder_d_path):
            self.model_d = joblib.load(self.model_d_path)
            self.encoder_d = joblib.load(self.encoder_d_path)
            with open(self.meta_d_path, "r", encoding="utf-8") as f:
                self.meta_d = json.load(f)

        # Cargar modelos de dos manos (Opcionales)
        self.model_2h = None
        self.encoder_2h = None
        if os.path.exists(self.model_2h_path) and os.path.exists(self.encoder_2h_path):
            self.model_2h = joblib.load(self.model_2h_path)
            self.encoder_2h = joblib.load(self.encoder_2h_path)
            with open(self.meta_2h_path, "r", encoding="utf-8") as f:
                self.meta_2h = json.load(f)

        self.max_hands = max_hands
        self.rotate_invariant = rotate_invariant

        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=0.70,
            min_tracking_confidence=0.60,
        )

        # Ajustamos el umbral de confianza para el suavizador
        # Las señas dinámicas suelen tener picos de confianza más bajos que las estáticas
        dyn_conf = 0.60 if mode == "dinamico" else confidence_threshold
        self.smoother = PredictionSmoother(confidence_threshold=dyn_conf)
        self.history = []
        self._callbacks = []

        # --- Estado para Señas Dinámicas ---
        self.dyn_buffer = []            # Secuencia de vectores
        self.is_recording_dyn = False   # ¿Estamos en medio de un gesto?
        self.still_frames_count = 0      # Frames que la mano ha estado quieta
        self.FRAMES_QUIETO_PARA_FINALIZAR = 10 # Reducido de 12 para una respuesta más rápida
        self.MOV_THRESHOLD = 0.05      # Aumentado de 0.03 para evitar ruido del sensor
        self.last_wrist_pos = None
        self.recording_start_time = None # Para evitar bloqueos infinitos
        self.last_confirmed_word = None  # Para implementar histéresis
        self.confirmed_persistence = 30  # Frames que mantenemos la palabra en pantalla (~1 seg)
        self.persistence_counter = 0      # Contador actual de frames restantes

    def register_callback(self, callback):
        self._callbacks.append(callback)

    def _emit_confirmed(self, word, confidence):
        timestamp = time.time()
        for callback in self._callbacks:
            try:
                callback(word, confidence, timestamp)
            except Exception as e:
                print(f"[WARN] Error en callback: {e}")

    def _medir_movimiento(self, landmarks):
        """Calcula el desplazamiento de la muñeca para detectar inicio de gesto."""
        # Muñeca es landmark 0
        wrist = landmarks.landmark[0]
        curr_pos = np.array([wrist.x, wrist.y])

        if self.last_wrist_pos is None:
            self.last_wrist_pos = curr_pos
            return 0.0

        dist = np.linalg.norm(curr_pos - self.last_wrist_pos)
        self.last_wrist_pos = curr_pos
        return dist

    def predict(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        # --- GESTIÓN DE PERSISTENCIA ---
        if self.persistence_counter > 0:
            self.persistence_counter -= 1
        else:
            self.last_confirmed_word = None

        if not results.multi_hand_landmarks:
            self.smoother.reset()
            self.is_recording_dyn = False
            self.dyn_buffer = []
            self.last_wrist_pos = None
            return None, 0.0, results, None

        # Usamos la primera mano detectada
        landmarks = results.multi_hand_landmarks[0]
        features = hand_features.build_feature_vector(
            landmarks, rotate=self.rotate_invariant
        )

        # --- Lógica de Segmentación Dinámica ---
        mov = self._medir_movimiento(landmarks)

        # 1. MODO ESTÁTICO: Ignoramos todo lo dinámico
        if self.mode == "estatico":
            probs_s = self.model_s.predict_proba([features])[0]
            best_idx_s = probs_s.argmax()
            label_s = self.encoder_s.inverse_transform([best_idx_s])[0]
            conf_s = float(probs_s[best_idx_s])

            confirmed, avg_conf = self.smoother.update(label_s, conf_s)
            if confirmed:
                self.history.append(confirmed)
                self._emit_confirmed(confirmed, avg_conf)
            return label_s, conf_s, results, confirmed

        # 2. MODO DINÁMICO: Ignoramos las predicciones estáticas
        if self.mode == "dinamico":
            if mov > self.MOV_THRESHOLD:
                if not self.is_recording_dyn:
                    self.recording_start_time = time.time()
                self.is_recording_dyn = True
                self.still_frames_count = 0
                self.dyn_buffer.append(features)
                if len(self.dyn_buffer) > 60:
                    self.dyn_buffer.pop(0)
                return None, 0.0, results, None
            else:
                if self.is_recording_dyn:
                    self.still_frames_count += 1
                    self.dyn_buffer.append(features)

                    # Seguridad: Si la grabación dura más de 4 segundos, forzar reset
                    if self.recording_start_time and (time.time() - self.recording_start_time > 4.0):
                        self.is_recording_dyn = False
                        self.dyn_buffer = []
                        return None, 0.0, results, None

                    if self.still_frames_count >= self.FRAMES_QUIETO_PARA_FINALIZAR:
                        if self.model_d and self.encoder_d:
                            pooled = temporal_pooling.pool_sequence(self.dyn_buffer)
                            probs_d = self.model_d.predict_proba([pooled])[0]
                            best_idx_d = probs_d.argmax()
                            label_d = self.encoder_d.inverse_transform([best_idx_d])[0]
                            conf_d = float(probs_d[best_idx_d])

                            confirmed, avg_conf = self.smoother.update(label_d, conf_d)
                            if confirmed:
                                self.history.append(confirmed)
                                self._emit_confirmed(confirmed, avg_conf)
                                # ACTIVAR PERSISTENCIA
                                self.last_confirmed_word = confirmed
                                self.persistence_counter = self.confirmed_persistence

                            self.is_recording_dyn = False
                            self.dyn_buffer = []
                            return label_d, conf_d, results, confirmed
                        else:
                            self.is_recording_dyn = False
                            self.dyn_buffer = []
                return None, 0.0, results, None

        # 3. MODO AUTO: Lógica híbrida original
        if mov > self.MOV_THRESHOLD:
            self.is_recording_dyn = True
            self.still_frames_count = 0
            self.dyn_buffer.append(features)
            if len(self.dyn_buffer) > 60:
                self.dyn_buffer.pop(0)

            probs_s = self.model_s.predict_proba([features])[0]
            best_idx_s = probs_s.argmax()
            label_s = self.encoder_s.inverse_transform([best_idx_s])[0]
            conf_s = float(probs_s[best_idx_s])
            return label_s, conf_s, results, None

        else:
            if self.is_recording_dyn:
                self.still_frames_count += 1
                self.dyn_buffer.append(features)

                if self.still_frames_count >= self.FRAMES_QUIETO_PARA_FINALIZAR:
                    if self.model_d and self.encoder_d:
                        pooled = temporal_pooling.pool_sequence(self.dyn_buffer)
                        probs_d = self.model_d.predict_proba([pooled])[0]
                        best_idx_d = probs_d.argmax()
                        label_d = self.encoder_d.inverse_transform([best_idx_d])[0]
                        conf_d = float(probs_d[best_idx_d])

                        confirmed, avg_conf = self.smoother.update(label_d, conf_d)
                        if confirmed:
                            self.history.append(confirmed)
                            self._emit_confirmed(confirmed, avg_conf)
                            # ACTIVAR PERSISTENCIA
                            self.last_confirmed_word = confirmed
                            self.persistence_counter = self.confirmed_persistence

                        self.is_recording_dyn = False
                        self.dyn_buffer = []
                        return label_d, conf_d, results, confirmed
                    else:
                        self.is_recording_dyn = False
                        self.dyn_buffer = []

            probs_s = self.model_s.predict_proba([features])[0]
            best_idx_s = probs_s.argmax()
            label_s = self.encoder_s.inverse_transform([best_idx_s])[0]
            conf_s = float(probs_s[best_idx_s])

            confirmed, avg_conf = self.smoother.update(label_s, conf_s)
            if confirmed:
                self.history.append(confirmed)
                self._emit_confirmed(confirmed, avg_conf)

            return label_s, conf_s, results, confirmed

    def draw_overlay(self, frame, label, confidence, results, confirmed):
        if results and results.multi_hand_landmarks:
            for hand_lm in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame, hand_lm, self.mp_hands.HAND_CONNECTIONS)

        # Priorizar palabra persistente si existe
        display_label = label
        display_confirmed = confirmed

        if self.last_confirmed_word:
            display_label = self.last_confirmed_word
            display_confirmed = True

        if display_label:
            color = (0, 255, 0) if display_confirmed else (100, 100, 100)
            cv2.putText(frame, f"{display_label} ({confidence*100:.0f}%)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, color, 2)
        else:
            cv2.putText(frame, "Muestra tu mano", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)

        if display_confirmed:
            cv2.putText(frame, f"CONFIRMADO: {display_label}", (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 0), 3)

        if self.is_recording_dyn:
            cv2.putText(frame, "Capturando movimiento...", (30, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        return frame

    def run_webcam(self, camera_id=None):
        cap, resolved_id = camera_utils.open_camera(camera_id)
        if cap is None:
            print("[ERROR] No se encontro ninguna camara disponible")
            return

        cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL)
        print(f"[OK] Camara {resolved_id} abierta. Presiona Q para salir.")
        try:
            while True:
                ret, frame = cap.read()
                if not ret: break
                frame = cv2.flip(frame, 1)
                label, confidence, results, confirmed = self.predict(frame)
                frame = self.draw_overlay(frame, label, confidence, results, confirmed)
                cv2.imshow(NOMBRE_VENTANA, frame)
                if cv2.waitKey(1) & 0xFF == ord("q"): break
                if cv2.getWindowProperty(NOMBRE_VENTANA, cv2.WND_PROP_VISIBLE) < 1: break
        finally:
            cap.release()
            cv2.destroyAllWindows()

def main():
    parser = argparse.ArgumentParser(description="Traductor de señas personalizado")
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    args = parser.parse_args()
    translator = CustomSignTranslator(models_dir=args.models_dir)
    translator.run_webcam(camera_id=args.camera)

if __name__ == "__main__":
    main()
