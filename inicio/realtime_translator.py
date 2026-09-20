#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realtime_translator.py (optimizado)

Mejoras de rendimiento:
  - Arbitro movimiento/no-movimiento: en cada frame solo se evalua UN modelo.
  - Downscale antes de MediaPipe (--input-size, default 480).
  - El modelo dinamico solo predice cada N frames (--cada-n-dinamico).
  - El buffer dinamico solo se alimenta cuando hay movimiento real.
  - Modos: ambos | estatico | dinamico (para pruebas aisladas).
"""

import argparse
import json
import os
import time
from collections import deque

import cv2
import mediapipe as mp
import joblib

import camera_utils
import hand_features
from smoothing import PredictionSmoother
from temporal_pooling import pool_sequence

MODELS_DIR = "./models"
NOMBRE_VENTANA = "Traductor de Senas Personalizado"
VENTANA_DINAMICA_DEFAULT = 20
MINIMO_FRAMES_PARA_PREDECIR = 5
MODOS_VALIDOS = ("ambos", "estatico", "dinamico")

# Cuando no hay movimiento durante N frames seguidos, se limpia el buffer
# dinamico: evita arrastrar frames viejos de una seña anterior.
FRAMES_SIN_MOVIMIENTO_PARA_LIMPIAR = 15


class CustomSignTranslator:
    def __init__(self, models_dir=MODELS_DIR, max_hands=1, rotate_invariant=True,
                 confidence_threshold=0.75, ventana_dinamica=VENTANA_DINAMICA_DEFAULT,
                 confidence_threshold_dinamico=0.65, umbral_movimiento=0.015,
                 modo="ambos", input_size=480, cada_n_dinamico=2):

        if modo not in MODOS_VALIDOS:
            raise ValueError(f"modo invalido: {modo}. Usa uno de {MODOS_VALIDOS}")

        self.modo = modo
        self.input_size = input_size
        self.cada_n_dinamico = max(1, cada_n_dinamico)
        self.max_hands = max_hands
        self.rotate_invariant = rotate_invariant
        self.history = []

        # --- MediaPipe ---
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=0.85,
            min_tracking_confidence=0.75,
        )

        # --- Modelo estatico (segun modo) ---
        self.model = None
        self.encoder = None
        self.meta = None
        self.smoother = None

        if modo in ("ambos", "estatico"):
            model_path = os.path.join(models_dir, "custom_sign_model.pkl")
            encoder_path = os.path.join(models_dir, "custom_sign_labels.pkl")
            meta_path = os.path.join(models_dir, "custom_sign_meta.json")
            for p in (model_path, encoder_path, meta_path):
                if not os.path.exists(p):
                    raise FileNotFoundError(
                        f"[modo={modo}] No se encontro {p}. Entrena el modelo estatico."
                    )
            self.model = joblib.load(model_path)
            self.encoder = joblib.load(encoder_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                self.meta = json.load(f)
            self.smoother = PredictionSmoother(confidence_threshold=confidence_threshold)
            print(f"[OK] Modelo ESTATICO cargado. Senas: {self.meta.get('words', [])}")
        else:
            print("[INFO] modo=dinamico: modelo estatico NO cargado")

        # --- Modelo dinamico (segun modo) ---
        self.modelo_dinamico = None
        self.encoder_dinamico = None
        self.meta_dinamico = None
        self.buffer_dinamico = deque(maxlen=ventana_dinamica)
        self.smoother_dinamico = PredictionSmoother(confidence_threshold=confidence_threshold_dinamico)

        if modo in ("ambos", "dinamico"):
            self._cargar_modelo_dinamico(models_dir)
        else:
            print("[INFO] modo=estatico: modelo dinamico NO cargado")

        # --- Estado del detector de movimiento ---
        self.wrist_anterior = None
        self.umbral_movimiento = umbral_movimiento
        self.frames_sin_movimiento = 0

        # --- Cache de la ultima prediccion dinamica (para no recalcular cada frame) ---
        self._frame_idx = 0
        self._ultimo_dinamico = (None, 0.0, None, 0.0)


    def _cargar_modelo_dinamico(self, models_dir):
        model_path = os.path.join(models_dir, "custom_sign_model_dinamico.pkl")
        encoder_path = os.path.join(models_dir, "custom_sign_labels_dinamico.pkl")
        meta_path = os.path.join(models_dir, "custom_sign_meta_dinamico.json")
        if not all(os.path.exists(p) for p in (model_path, encoder_path, meta_path)):
            print("[AVISO] Modelo dinamico no encontrado. Solo senas estaticas.")
            return
        self.modelo_dinamico = joblib.load(model_path)
        self.encoder_dinamico = joblib.load(encoder_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta_dinamico = json.load(f)
        print(f"[OK] Modelo DINAMICO cargado. Senas: {self.meta_dinamico.get('words', [])}")


    def _procesar_mediapipe(self, frame):
        """Downscale + BGR->RGB + MediaPipe. Devuelve (results, escala)."""
        h, w = frame.shape[:2]
        scale = 1.0
        if self.input_size and max(h, w) > self.input_size:
            scale = self.input_size / max(h, w)
            small = cv2.resize(frame, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_LINEAR)
        else:
            small = frame
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.hands.process(rgb)
        return results, small


    def _medir_movimiento(self, results):
        """Devuelve (en_movimiento, movimiento). Usa posicion cruda de la muñeca."""
        if not results.multi_hand_landmarks:
            self.wrist_anterior = None
            return False, 0.0
        wrist_lm = results.multi_hand_landmarks[0].landmark[0]
        wrist_actual = (wrist_lm.x, wrist_lm.y)
        if self.wrist_anterior is None:
            self.wrist_anterior = wrist_actual
            return False, 0.0
        dx = wrist_actual[0] - self.wrist_anterior[0]
        dy = wrist_actual[1] - self.wrist_anterior[1]
        mov = (dx * dx + dy * dy) ** 0.5
        self.wrist_anterior = wrist_actual
        return mov > self.umbral_movimiento, mov


    def predict(self, frame):
        self._frame_idx += 1
        results, _ = self._procesar_mediapipe(frame)

        # ---- Sin mano ----
        if not results.multi_hand_landmarks:
            if self.smoother is not None:
                self.smoother.reset()
            self.wrist_anterior = None
            self.frames_sin_movimiento += 1

            # Alimentar el buffer dinamico solo si el modo lo usa y hay algo que mantener.
            resultado_dinamico = (None, 0.0, None, 0.0)
            if self.modelo_dinamico is not None and self.buffer_dinamico:
                resultado_dinamico = self._actualizar_dinamico(None)
            return None, 0.0, results, None, resultado_dinamico, False

        # ---- Features ----
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

        en_movimiento, _ = self._medir_movimiento(results)
        if en_movimiento:
            self.frames_sin_movimiento = 0
        else:
            self.frames_sin_movimiento += 1

        # ==================================================================
        # MODO DINAMICO PURO
        # ==================================================================
        if self.modo == "dinamico":
            if self.modelo_dinamico is None:
                return None, 0.0, results, None, (None, 0.0, None, 0.0), True
            resultado_dinamico = self._actualizar_dinamico(features)
            return None, 0.0, results, None, resultado_dinamico, True

        # ==================================================================
        # MODO ESTATICO PURO
        # ==================================================================
        if self.modo == "estatico":
            resultado_dinamico = (None, 0.0, None, 0.0)
            if len(features) != self.meta["feature_length"]:
                return None, 0.0, results, None, resultado_dinamico, en_movimiento
            probs = self.model.predict_proba([features])[0]
            best_idx = probs.argmax()
            label = self.encoder.inverse_transform([best_idx])[0]
            confidence = float(probs[best_idx])
            confirmed, _ = self.smoother.update(label, confidence)
            if confirmed:
                self.history.append(confirmed)
            return label, confidence, results, confirmed, resultado_dinamico, en_movimiento

        # ==================================================================
        # MODO AMBOS  ->  ARBITRO
        # ------------------------------------------------------------------
        # Regla:
        #   - Si HAY movimiento: manda el DINAMICO. El estatico no se toca.
        #   - Si NO hay movimiento: manda el ESTATICO. El dinamico NO predice,
        #     solo se le deja "envejecer" el buffer o se limpia si lleva
        #     demasiado tiempo quieto.
        # ==================================================================
        resultado_dinamico = self._ultimo_dinamico  # por defecto, mantener el ultimo mostrado

        if en_movimiento:
            # --- Rama DINAMICA ---
            if self.smoother is not None:
                self.smoother.reset()  # el estatico no acumula progreso mientras hay movimiento
            if self.modelo_dinamico is not None:
                resultado_dinamico = self._actualizar_dinamico(features)
                self._ultimo_dinamico = resultado_dinamico
            return None, 0.0, results, None, resultado_dinamico, True
        else:
            # --- Rama ESTATICA ---
            # Si llevamos mucho tiempo quieto, limpiamos buffer dinamico
            # para no arrastrar movimiento viejo.
            if (self.buffer_dinamico and
                    self.frames_sin_movimiento >= FRAMES_SIN_MOVIMIENTO_PARA_LIMPIAR):
                self.buffer_dinamico.clear()
                self.smoother_dinamico.reset()
                self._ultimo_dinamico = (None, 0.0, None, 0.0)
                resultado_dinamico = self._ultimo_dinamico

            if len(features) != self.meta["feature_length"]:
                return None, 0.0, results, None, resultado_dinamico, False

            probs = self.model.predict_proba([features])[0]
            best_idx = probs.argmax()
            label = self.encoder.inverse_transform([best_idx])[0]
            confidence = float(probs[best_idx])

            confirmed, _ = self.smoother.update(label, confidence)
            if confirmed:
                self.history.append(confirmed)
            return label, confidence, results, confirmed, resultado_dinamico, False

    def _actualizar_dinamico(self, feature_vector):
        """
        Alimenta el buffer y, solo cada `cada_n_dinamico` frames o cuando la
        ventana se acaba de llenar, corre predict_proba. Devuelve
        (confirmado, conf, label_vivo, conf_vivo).
        """
        if self.modelo_dinamico is None:
            return None, 0.0, None, 0.0

        if feature_vector is not None:
            self.buffer_dinamico.append(feature_vector)
        elif self.buffer_dinamico:
            self.buffer_dinamico.append(self.buffer_dinamico[-1])
        else:
            return None, 0.0, None, 0.0

        if len(self.buffer_dinamico) < MINIMO_FRAMES_PARA_PREDECIR:
            return None, 0.0, None, 0.0

        ventana_completa = len(self.buffer_dinamico) >= self.buffer_dinamico.maxlen

        # Cache: si no toca predecir todavia y no esta llena, devuelve lo anterior.
        debe_predecir = ventana_completa or (self._frame_idx % self.cada_n_dinamico == 0)
        if not debe_predecir:
            return self._ultimo_dinamico if ventana_completa else (None, 0.0, None, 0.0)

        vector_pooled = pool_sequence(list(self.buffer_dinamico))
        if len(vector_pooled) != self.meta_dinamico["feature_length"]:
            return None, 0.0, None, 0.0

        probs = self.modelo_dinamico.predict_proba([vector_pooled])[0]
        best_idx = probs.argmax()
        label_din = self.encoder_dinamico.inverse_transform([best_idx])[0]
        conf_din = float(probs[best_idx])

        if not ventana_completa:
            return None, 0.0, label_din, conf_din

        confirmado, _ = self.smoother_dinamico.update(label_din, conf_din)
        if confirmado:
            self.history.append(confirmado)
            self.buffer_dinamico.clear()
            self.smoother_dinamico.reset()
            self._ultimo_dinamico = (None, 0.0, None, 0.0)
            return None, 0.0, None, 0.0

        return None, conf_din, label_din, conf_din

    def draw_overlay(self, frame, label, confidence, results, confirmed,
                     resultado_dinamico=(None, 0.0, None, 0.0), en_movimiento=False):
        if results and results.multi_hand_landmarks:
            for hand_lm in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame, hand_lm, self.mp_hands.HAND_CONNECTIONS)

        confirmado_dinamico, _, label_dinamico_en_vivo, conf_din_vivo = resultado_dinamico

        # ---- Texto superior ----
        if en_movimiento and label_dinamico_en_vivo:
            cv2.putText(frame, f"{label_dinamico_en_vivo} ({conf_din_vivo*100:.0f}%)",
                        (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 140, 0), 2)
        elif en_movimiento:
            cv2.putText(frame, "Moviendo... (analizando)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 140, 0), 2)
        elif label:
            cv2.putText(frame, f"{label} ({confidence*100:.0f}%)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, (100, 100, 100), 2)
        else:
            cv2.putText(frame, "Muestra tu mano", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)

        # ---- Confirmacion ----
        texto_conf = None
        color_conf = (0, 255, 0)
        if confirmed:
            texto_conf = f"CONFIRMADO: {confirmed}"
            color_conf = (0, 255, 0)
        elif confirmado_dinamico:
            texto_conf = f"CONFIRMADO: {confirmado_dinamico}"
            color_conf = (255, 140, 0)
        if texto_conf:
            cv2.putText(frame, texto_conf, (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, color_conf, 3)

        # Barra de progreso del buffer dinamico 
        if self.modelo_dinamico is not None:
            progreso = len(self.buffer_dinamico)
            objetivo = self.buffer_dinamico.maxlen
            h = frame.shape[0]
            cv2.putText(frame, f"[dinamica] buffer: {progreso}/{objetivo}", (30, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 150, 0), 2)

        # FPS + modo (util para medir la mejora) 
        cv2.putText(frame, f"modo: {self.modo}", (30, 160),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)

        return frame

    def run_webcam(self, camera_id=None):
        cap, resolved_id = camera_utils.open_camera(camera_id)
        if cap is None:
            print("[ERROR] No se encontro ninguna camara disponible")
            return

        # Baja el buffer interno de la camara: menos latencia, mas FPS estables.
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL)
        print(f"[OK] Camara {resolved_id} abierta. modo={self.modo}. "
              f"Q para salir, S para guardar captura.")

        # --- Contador de FPS ---
        t_prev = time.time()
        fps = 0.0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[ERROR] No se pudo leer un frame de la camara")
                    break

                frame = cv2.flip(frame, 1)
                label, confidence, results, confirmed, resultado_dinamico, en_movimiento = self.predict(frame)
                frame = self.draw_overlay(frame, label, confidence, results, confirmed,
                                          resultado_dinamico, en_movimiento)

                # FPS suavizado
                t_now = time.time()
                dt = t_now - t_prev
                t_prev = t_now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt
                cv2.putText(frame, f"FPS: {fps:.1f}", (frame.shape[1] - 180, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

                cv2.imshow(NOMBRE_VENTANA, frame)
                key = cv2.waitKey(1) & 0xFF

                if cv2.getWindowProperty(NOMBRE_VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                    print("[OK] Ventana cerrada por el usuario.")
                    break
                if key in (ord("q"), ord("Q")):
                    break
                elif key in (ord("s"), ord("S")):
                    fname = f"captura_{int(time.time())}.jpg"
                    cv2.imwrite(fname, frame)
                    print(f"[OK] Imagen guardada: {fname}")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            print(f"\n[OK] Historial de traduccion: {' '.join(self.history[-20:])}")

def main():
    parser = argparse.ArgumentParser(description="Traductor de señas personalizado (optimizado)")
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--hands", type=int, choices=[1, 2], default=1)
    parser.add_argument("--ventana-dinamica", type=int, default=VENTANA_DINAMICA_DEFAULT)
    parser.add_argument("--umbral-movimiento", type=float, default=0.015)
    parser.add_argument("--modo", choices=MODOS_VALIDOS, default="ambos")
    parser.add_argument("--input-size", type=int, default=480,
                        help="Lado mayor maximo antes de MediaPipe. 480 = rapido, 720 = preciso.")
    parser.add_argument("--cada-n-dinamico", type=int, default=2,
                        help="Corre predict_proba del dinamico 1 de cada N frames (ademas de al llenar la ventana).")
    args = parser.parse_args()

    translator = CustomSignTranslator(
        models_dir=args.models_dir,
        max_hands=args.hands,
        ventana_dinamica=args.ventana_dinamica,
        umbral_movimiento=args.umbral_movimiento,
        modo=args.modo,
        input_size=args.input_size,
        cada_n_dinamico=args.cada_n_dinamico,
    )
    translator.run_webcam(camera_id=args.camera)


if __name__ == "__main__":
    main()
