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

NUEVO:
  - Carga TAMBIEN el modelo dinamico (custom_sign_model_dinamico.pkl) si
    existe, de forma opcional/graceful: si no esta entrenado todavia, el
    traductor sigue funcionando solo con senas estaticas, sin romperse.
  - Mantiene una ventana deslizante (deque) de los ultimos N vectores de
    landmarks, aplicando la MISMA funcion temporal_pooling.pool_sequence()
    que se uso al entrenar, para predecir senas dinamicas en paralelo a
    las estaticas.
  - Usa un PredictionSmoother SEPARADO para lo dinamico (no comparte
    estado con el de estaticas), y limpia el buffer tras confirmar una
    sena dinamica para evitar que la misma confirmacion se repita varias
    veces mientras la ventana sigue llena/deslizando.
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
MINIMO_FRAMES_PARA_PREDECIR = 5  # no hace falta esperar a llenar toda la ventana para dar una primera predicción


class CustomSignTranslator:
    def __init__(self, models_dir=MODELS_DIR, max_hands=1, rotate_invariant=True,
                 confidence_threshold=0.75, ventana_dinamica=VENTANA_DINAMICA_DEFAULT,
                 confidence_threshold_dinamico=0.65, umbral_movimiento=0.015):
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

        # --- Carga OPCIONAL del modelo dinamico ---
        self.modelo_dinamico = None
        self.encoder_dinamico = None
        self.meta_dinamico = None
        self._cargar_modelo_dinamico(models_dir)

        self.buffer_dinamico = deque(maxlen=ventana_dinamica)
        self.smoother_dinamico = PredictionSmoother(confidence_threshold=confidence_threshold_dinamico)

        # --- Detector de movimiento (basado en la posicion CRUDA de la
        # muñeca, NO en el vector normalizado/invariante a rotacion) ---
        # El feature_vector de hand_features.py es invariante a rotacion y
        # escala para que el modelo estatico funcione sin importar el
        # angulo de la mano -- pero esa misma invariancia hace que un
        # movimiento como agitar la mano (que es basicamente una rotacion
        # de la muñeca) casi no cambie el vector normalizado entre frames.
        # Por eso el movimiento se mide aparte, sobre la posicion real
        # (x, y) de la muñeca en la imagen.
        self.wrist_anterior = None
        self.umbral_movimiento = umbral_movimiento

    def _cargar_modelo_dinamico(self, models_dir):
        """Carga el modelo dinamico si existe. Si no, el traductor sigue
        funcionando solo con senas estaticas (no se rompe nada)."""
        model_path = os.path.join(models_dir, "custom_sign_model_dinamico.pkl")
        encoder_path = os.path.join(models_dir, "custom_sign_labels_dinamico.pkl")
        meta_path = os.path.join(models_dir, "custom_sign_meta_dinamico.json")

        if not all(os.path.exists(p) for p in (model_path, encoder_path, meta_path)):
            print("[AVISO] Modelo dinamico no encontrado. Solo se reconoceran senas estaticas.")
            print("[AVISO] Entrena senas dinamicas con gui_captura.py + train_classifier.py para habilitarlo.")
            return

        self.modelo_dinamico = joblib.load(model_path)
        self.encoder_dinamico = joblib.load(encoder_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta_dinamico = json.load(f)
        print(f"[OK] Modelo dinamico cargado. Senas reconocibles: {self.meta_dinamico.get('words', [])}")

    def predict(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        if not results.multi_hand_landmarks:
            self.smoother.reset()
            self.wrist_anterior = None  # mano perdida: reinicia la referencia de movimiento
            resultado_dinamico = self._actualizar_dinamico(None)
            return None, 0.0, results, None, resultado_dinamico, False

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

        # --- Medición de movimiento real (posición cruda de la muñeca) ---
        wrist_lm = results.multi_hand_landmarks[0].landmark[0]
        wrist_actual = (wrist_lm.x, wrist_lm.y)
        if self.wrist_anterior is not None:
            dx = wrist_actual[0] - self.wrist_anterior[0]
            dy = wrist_actual[1] - self.wrist_anterior[1]
            movimiento = (dx ** 2 + dy ** 2) ** 0.5
        else:
            movimiento = 0.0
        self.wrist_anterior = wrist_actual
        en_movimiento = movimiento > self.umbral_movimiento

        # Actualiza el buffer dinamico con el vector de este frame,
        # independientemente de si el estatico logra clasificarlo o no.
        resultado_dinamico = self._actualizar_dinamico(features)

        expected_len = self.meta["feature_length"]
        if len(features) != expected_len:
            # El modelo estatico fue entrenado con otra configuracion (p.ej. 1 vs 2 manos)
            return None, 0.0, results, None, resultado_dinamico, en_movimiento

        probs = self.model.predict_proba([features])[0]
        best_idx = probs.argmax()
        label = self.encoder.inverse_transform([best_idx])[0]
        confidence = float(probs[best_idx])

        if en_movimiento:
            # Hay movimiento real: no se confirma estatica en este frame,
            # solo se sigue alimentando el buffer dinamico. Se resetea el
            # smoother para que no arrastre progreso de confirmacion previo.
            self.smoother.reset()
            confirmed = None
        else:
            confirmed, avg_conf = self.smoother.update(label, confidence)
            if confirmed:
                self.history.append(confirmed)

        return label, confidence, results, confirmed, resultado_dinamico, en_movimiento

    def _actualizar_dinamico(self, feature_vector):
        """
        Mantiene la ventana deslizante y predice con el modelo dinamico
        cuando hay suficientes frames acumulados.

        Devuelve (confirmado, confianza_confirmado, label_en_vivo, confianza_en_vivo):
          - confirmado/confianza_confirmado: solo cuando el smoother ya
            confirmo una sena (igual que antes).
          - label_en_vivo/confianza_en_vivo: la prediccion CRUDA mas
            reciente del modelo dinamico (aunque aun no este confirmada),
            para poder mostrarla en pantalla mientras la persona se sigue
            moviendo, en vez de un texto generico de "en movimiento".
            Es None si el buffer todavia no se llena o el modelo dinamico
            no esta disponible.
        """
        if self.modelo_dinamico is None:
            return None, 0.0, None, 0.0

        if feature_vector is not None:
            self.buffer_dinamico.append(feature_vector)
        elif self.buffer_dinamico:
            # Mano perdida por un frame puntual: se repite el ultimo vector
            # conocido, igual que hace capturar/gui_captura.py al grabar,
            # para no descartar la ventana completa por un frame fallido.
            self.buffer_dinamico.append(self.buffer_dinamico[-1])
        else:
            return None, 0.0, None, 0.0

        if len(self.buffer_dinamico) < MINIMO_FRAMES_PARA_PREDECIR:
            return None, 0.0, None, 0.0  # muy pocos frames todavia, ni para una primera estimacion

        # Se predice con lo que haya en el buffer hasta ahora (parcial o
        # completo) -- pool_sequence funciona igual de bien sin importar
        # cuantos frames tenga, así que no hace falta esperar a llenar
        # toda la ventana para dar una primera palabra en pantalla.
        vector_pooled = pool_sequence(list(self.buffer_dinamico))

        expected_len = self.meta_dinamico["feature_length"]
        if len(vector_pooled) != expected_len:
            return None, 0.0, None, 0.0

        probs = self.modelo_dinamico.predict_proba([vector_pooled])[0]
        best_idx = probs.argmax()
        label_dinamico = self.encoder_dinamico.inverse_transform([best_idx])[0]
        confianza_dinamico = float(probs[best_idx])

        ventana_completa = len(self.buffer_dinamico) >= self.buffer_dinamico.maxlen
        if not ventana_completa:
            # Todavia no hay suficientes frames para confirmar con
            # seguridad -- se muestra la palabra como referencia en vivo,
            # pero no se alimenta el smoother (evita confirmar de mas
            # rapido con poca informacion real de movimiento).
            return None, 0.0, label_dinamico, confianza_dinamico

        confirmado, avg_conf = self.smoother_dinamico.update(label_dinamico, confianza_dinamico)
        if confirmado:
            self.history.append(confirmado)
            # Se limpia el buffer tras confirmar, para exigir una ventana
            # nueva antes de volver a confirmar la misma sena repetidamente
            # mientras la ventana sigue llena y deslizando.
            self.buffer_dinamico.clear()
            self.smoother_dinamico.reset()

        return confirmado, confianza_dinamico, label_dinamico, confianza_dinamico

    def draw_overlay(self, frame, label, confidence, results, confirmed, resultado_dinamico=(None, 0.0, None, 0.0), en_movimiento=False):
        if results and results.multi_hand_landmarks:
            for hand_lm in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame, hand_lm, self.mp_hands.HAND_CONNECTIONS)

        confirmado_dinamico, _, label_dinamico_en_vivo, confianza_dinamico_en_vivo = resultado_dinamico

        if en_movimiento:
            if label_dinamico_en_vivo:
                # Muestra la palabra que el modelo dinamico esta prediciendo
                # EN VIVO (aun sin confirmar), en vez de un texto generico.
                cv2.putText(frame, f"{label_dinamico_en_vivo} ({confianza_dinamico_en_vivo*100:.0f}%)",
                            (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 140, 0), 2)
            else:
                # Se detecto movimiento pero el buffer aun no se llena
                # para poder darle al modelo dinamico algo que predecir.
                cv2.putText(frame, "Moviendo... (analizando)", (30, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 140, 0), 2)
        elif label:
            cv2.putText(frame, f"{label} ({confidence*100:.0f}%)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, (100, 100, 100), 2)
        else:
            cv2.putText(frame, "Muestra tu mano", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)

        # --- Confirmación unificada: estática o dinámica, misma posición ---
        # Si ambas confirman en el mismo frame (poco común), la estática
        # tiene prioridad visual ya que es la más instantánea de las dos.
        # (confirmado_dinamico ya se desempaquetó arriba, junto con la
        # predicción en vivo, al inicio de este método)
        texto_confirmado = None
        color_confirmado = (0, 255, 0)  # verde = estática

        if confirmed:
            texto_confirmado = f"CONFIRMADO: {confirmed}"
            color_confirmado = (0, 255, 0)
        elif confirmado_dinamico:
            texto_confirmado = f"CONFIRMADO: {confirmado_dinamico}"
            color_confirmado = (255, 140, 0)  # naranja = dinámica

        if texto_confirmado:
            cv2.putText(frame, texto_confirmado, (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, color_confirmado, 3)

        # --- Progreso del buffer dinámico: abajo del todo, discreto ---
        if self.modelo_dinamico is not None:
            progreso = len(self.buffer_dinamico)
            objetivo = self.buffer_dinamico.maxlen
            alto_frame = frame.shape[0]
            cv2.putText(frame, f"[dinamica] buffer: {progreso}/{objetivo}", (30, alto_frame - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 150, 0), 2)

        return frame

    def run_webcam(self, camera_id=None):

        cap, resolved_id = camera_utils.open_camera(camera_id)
        if cap is None:
            print("[ERROR] No se encontro ninguna camara disponible")
            return

        cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL)

        print(f"[OK] Camara {resolved_id} abierta. Presiona Q para salir, S para guardar captura.")
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[ERROR] No se pudo leer un frame de la camara")
                    break

                frame = cv2.flip(frame, 1)
                label, confidence, results, confirmed, resultado_dinamico, en_movimiento = self.predict(frame)
                frame = self.draw_overlay(frame, label, confidence, results, confirmed, resultado_dinamico, en_movimiento)

                cv2.imshow(NOMBRE_VENTANA, frame)

                # waitKey es quien procesa los eventos de la ventana (incluido
                # el clic en la X), por eso debe ir ANTES de revisar la propiedad.
                key = cv2.waitKey(1) & 0xFF

                # Si el usuario cerró la ventana con la X, esta propiedad
                # ya queda en < 1 justo después del waitKey de arriba.
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
    parser = argparse.ArgumentParser(description="Traductor de señas personalizado en tiempo real")
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--hands", type=int, choices=[1, 2], default=1)
    parser.add_argument("--ventana-dinamica", type=int, default=VENTANA_DINAMICA_DEFAULT)
    parser.add_argument("--umbral-movimiento", type=float, default=0.015,
                         help="Sensibilidad del detector de movimiento (mas bajo = mas sensible)")
    args = parser.parse_args()

    translator = CustomSignTranslator(
        models_dir=args.models_dir, max_hands=args.hands,
        ventana_dinamica=args.ventana_dinamica,
        umbral_movimiento=args.umbral_movimiento,
    )
    translator.run_webcam(camera_id=args.camera)


if __name__ == "__main__":
    main()