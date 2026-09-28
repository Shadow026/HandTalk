#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realtime_translator.py

TRADUCTOR UNIFICADO: SEÑAS ESTÁTICAS (1 Y 2 MANOS) Y DINÁMICAS, CON FILTROS DE PRECISIÓN.

Mejoras por modelo
------------------
UNA MANO (estático)
  - Solo clasifica con la mano quieta (evita leer poses "de paso" al levantar la mano).
  - Descarta frames donde MediaPipe no está seguro de la mano (score bajo).
  - Smoother propio por modelo (los votos de 1 y 2 manos no se mezclan).

DOS MANOS (estático)
  - Solo se usa cuando el nº de manos es estable varios frames y ambas son fiables.

DINÁMICO
  - Confirmación directa (sin smoother) y TEMPRANA (opcional): la palabra sale mientras
    haces el gesto si el modelo es muy seguro y coincide en evaluaciones consecutivas.
  - Si la mano sale de cámara, se espera unos frames (parpadeo del tracker) y se clasifica.
  - Respuesta rápida al terminar el gesto y sin bloquear la siguiente seña.
  - ZONA MUERTA de movimiento: los micro-temblores de la mano no activan el modo dinámico.
    Solo se graba cuando hay movimiento REAL sostenido varios frames.
"""

import argparse
import json
import os
import time
import unicodedata
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
                 confidence_threshold=0.75, mode="auto", debug=False):
        # --- Modelos Estáticos ---
        self.model_s_path = os.path.join(models_dir, "custom_sign_model.pkl")
        self.encoder_s_path = os.path.join(models_dir, "custom_sign_labels.pkl")
        self.meta_s_path = os.path.join(models_dir, "custom_sign_meta.json")

        self.mode = mode  # "auto", "estatico", "dinamico"
        self.debug = debug

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
        self.meta_d = None
        if os.path.exists(self.model_d_path) and os.path.exists(self.encoder_d_path):
            self.model_d = joblib.load(self.model_d_path)
            self.encoder_d = joblib.load(self.encoder_d_path)
            if os.path.exists(self.meta_d_path):
                with open(self.meta_d_path, "r", encoding="utf-8") as f:
                    self.meta_d = json.load(f)
            print("[OK] Modelo dinamico cargado.")
        else:
            print("[INFO] No hay modelo dinamico; las senas con movimiento no se reconoceran.")

        # Cargar modelos de dos manos (Opcionales)
        self.model_2h = None
        self.encoder_2h = None
        self.meta_2h = None
        if os.path.exists(self.model_2h_path) and os.path.exists(self.encoder_2h_path):
            self.model_2h = joblib.load(self.model_2h_path)
            self.encoder_2h = joblib.load(self.encoder_2h_path)
            if os.path.exists(self.meta_2h_path):
                with open(self.meta_2h_path, "r", encoding="utf-8") as f:
                    self.meta_2h = json.load(f)
            print("[OK] Modelo de dos manos cargado.")
        else:
            print("[INFO] No hay modelo de dos manos; se usara solo el de una mano.")

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

        # Un smoother por modelo estático (los votos no se mezclan). Las dinámicas no lo usan.
        self.smoothers = {
            "1h": PredictionSmoother(confidence_threshold=confidence_threshold),
            "2h": PredictionSmoother(confidence_threshold=confidence_threshold),
        }
        self.history = []
        self._callbacks = []

        # ==============================================================
        # PARÁMETROS AJUSTABLES
        # ==============================================================
        # --- Movimiento ---
        # Desplazamiento por frame (normalizado y suavizado). Si las dinámicas no se activan,
        # BAJA MOV_THRESHOLD; si se activan solas con la mano quieta, SÚBELO.
        self.MOV_THRESHOLD = 0.012
        # Zona muerta: distancias menores a esto se consideran ruido/temblor (no movimiento).
        # Súbelo si con la mano "quieta" igual se activa el modo dinámico.
        self.MOV_NOISE_FLOOR = 0.008
        # Frames consecutivos con movimiento real antes de ARRANCAR la grabación dinámica.
        # Evita que un solo frame ruidoso (o la mano entrando en cámara) dispare el gesto.
        self.MOV_FRAMES_TO_START = 3
        # Frames consecutivos quieto (por debajo del umbral) para considerar que ya paró.
        self.MOV_FRAMES_TO_STOP = 3

        # --- Estático ---
        self.STATIC_STILL_FRAMES = 4       # frames quietos antes de clasificar estático
        self.HAND_SCORE_MIN = 0.40         # score mínimo de MediaPipe por mano
        self.HAND_COUNT_STABLE_FRAMES = 4  # frames estables antes de cambiar 1h <-> 2h
        self.STATIC_COOLDOWN = 12          # frames sin estático tras detectar movimiento
        self.IGNORE_LABELS = {"reposo", "neutral", "neutro", "ninguna", "nada", "none", "idle"}

        # --- Dinámico ---
        self.FRAMES_QUIETO_PARA_FINALIZAR = 5   # ~0.17 s quieto para dar por terminado
        self.MIN_DYN_FRAMES = 8                 # secuencias más cortas = ruido
        self.DYN_CONF_MIN = 0.80                # confianza mínima al terminar el gesto
        self.MAX_DYN_SECONDS = 4.0
        self.LOST_FRAMES_TO_FINALIZE = 4        # frames sin mano antes de cerrar el gesto
        self.POST_DYN_COOLDOWN_OK = 18          # frames sin estático tras dinámica confirmada
        self.POST_DYN_COOLDOWN_FAIL = 8
        self.confirmed_persistence = 15         # frames que se mantiene la palabra en pantalla

        # Confirmación TEMPRANA: la palabra sale mientras haces el gesto
        self.EARLY_CONFIRM = False               # pon True para confirmar mientras haces el gesto
        self.EARLY_MIN_FRAMES = 12
        self.EARLY_EVAL_EVERY = 3               # evalúa cada N frames de movimiento
        self.EARLY_CONF_MIN = 0.90              # exigente: evita disparos falsos
        self.EARLY_HITS_REQUIRED = 2            # evaluaciones consecutivas que deben coincidir

        # --- Estado dinámico ---
        self.dyn_buffer = []
        self.is_recording_dyn = False
        self.still_frames_count = 0
        self.recording_start_time = None
        self.dyn_confirmed_early = False
        self.early_candidate = None
        self.early_hits = 0
        self.dyn_frames_since_eval = 0

        # --- Seguimiento de movimiento y manos ---
        self.last_wrist_pos = None
        self.last_hand_count = 0
        self.mov_ema = 0.0
        self.still_run = 0
        self.mov_run = 0            # frames consecutivos con movimiento real
        self.static_cooldown = 0
        self.lost_frames = 0
        self.raw_count = 0
        self.raw_count_frames = 0
        self.stable_count = 0

        # --- Persistencia en pantalla ---
        self.last_confirmed_word = None
        self.last_confirmed_conf = 0.0
        self.persistence_counter = 0

        # --- Overlay ---
        self.current_source = "1h"
        self._warned_2h_dim = False

    # ------------------------------------------------------------------
    # Utilidades generales
    # ------------------------------------------------------------------
    @staticmethod
    def _norm_label(label):
        s = unicodedata.normalize("NFD", str(label))
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return s.lower().strip()

    def register_callback(self, callback):
        self._callbacks.append(callback)

    def _emit_confirmed(self, word, confidence):
        timestamp = time.time()
        for callback in self._callbacks:
            try:
                callback(word, confidence, timestamp)
            except Exception as e:
                print(f"[WARN] Error en callback: {e}")

    def _reset_smoothers(self):
        for sm in self.smoothers.values():
            sm.reset()

    @staticmethod
    def _decodificar(probs, encoder):
        """Clase más probable del modelo. Devuelve (label, prob)."""
        idx = int(np.argmax(probs))
        return encoder.inverse_transform([idx])[0], float(probs[idx])

    # ------------------------------------------------------------------
    # Manos y movimiento
    # ------------------------------------------------------------------
    def _manos_ordenadas(self, results):
        """Ordena por x de la muñeca (izq -> der): orden estable entre frames."""
        return sorted(results.multi_hand_landmarks, key=lambda h: h.landmark[0].x)

    def _manos_fiables(self, results):
        """True si MediaPipe está seguro de todas las manos visibles."""
        handed = getattr(results, "multi_handedness", None)
        if not handed:
            return True
        try:
            return all(h.classification[0].score >= self.HAND_SCORE_MIN for h in handed)
        except Exception:
            return True

    def _actualizar_conteo_manos(self, n):
        """True si el nº de manos actual ya es estable (se sostuvo N frames)."""
        if n == self.raw_count:
            self.raw_count_frames += 1
        else:
            self.raw_count = n
            self.raw_count_frames = 1
        if self.raw_count_frames >= self.HAND_COUNT_STABLE_FRAMES:
            self.stable_count = n
        return self.stable_count == n

    def _medir_movimiento(self, results):
        """
        Movimiento suavizado (EMA) del centro de las muñecas visibles.

        CLAVES PARA NO CONFUNDIR "MANO EN PANTALLA" CON "GESTO DINÁMICO":
          - Si cambia el nº de manos (entra/sale una mano), no se cuenta como movimiento.
          - Se aplica una ZONA MUERTA: temblores menores a MOV_NOISE_FLOOR se ignoran.
          - El EMA solo acumula el exceso sobre la zona muerta (evita que el ruido
            persistente mantenga el valor alto aunque no haya gesto real).
        """
        hands = results.multi_hand_landmarks
        n = len(hands)
        curr_pos = np.mean([[h.landmark[0].x, h.landmark[0].y] for h in hands], axis=0)

        # Cambio en el nº de manos: el centro salta artificialmente. No es movimiento.
        if self.last_wrist_pos is None or n != self.last_hand_count:
            self.last_wrist_pos = curr_pos
            self.last_hand_count = n
            self.mov_ema = 0.0
            self.mov_run = 0
            return 0.0

        dist = float(np.linalg.norm(curr_pos - self.last_wrist_pos))
        self.last_wrist_pos = curr_pos

        # Zona muerta: lo que esté por debajo es temblor/ruido, no gesto.
        effective = max(0.0, dist - self.MOV_NOISE_FLOOR)

        # EMA con decaimiento: si no hay movimiento real, baja rápido a 0.
        if effective > 0.0:
            self.mov_ema = 0.6 * self.mov_ema + 0.4 * effective
        else:
            self.mov_ema *= 0.6

        return self.mov_ema

    def _reset_tracking(self):
        self.last_wrist_pos = None
        self.last_hand_count = 0
        self.mov_ema = 0.0
        self.still_run = 0
        self.mov_run = 0
        self.raw_count = 0
        self.raw_count_frames = 0
        self.stable_count = 0

    # ------------------------------------------------------------------
    # Estático (1 mano / 2 manos)
    # ------------------------------------------------------------------
    def _clasificar_estatico(self, results, features_1h):
        """Devuelve (label, confianza, source)."""
        usar_2h = (
            len(results.multi_hand_landmarks) == 2
            and self.model_2h is not None
            and self.encoder_2h is not None
        )

        feats = None
        if usar_2h:
            feats = hand_features.build_two_hand_feature_vector(
                results.multi_hand_landmarks,
                results.multi_handedness,
                rotate=self.rotate_invariant,
            )
            n_esperado = getattr(self.model_2h, "n_features_in_", None)
            if n_esperado is not None and len(feats) != n_esperado:
                if not self._warned_2h_dim:
                    print(f"[WARN] Features de 2 manos: {len(feats)} vs esperado "
                          f"{n_esperado}. Usando modelo de 1 mano.")
                    self._warned_2h_dim = True
                usar_2h = False

        if usar_2h:
            model, encoder, source = self.model_2h, self.encoder_2h, "2h"
        else:
            feats = features_1h
            model, encoder, source = self.model_s, self.encoder_s, "1h"

        probs = model.predict_proba([feats])[0]
        label, conf = self._decodificar(probs, encoder)
        return label, conf, source

    def _paso_estatico(self, results, features):
        """Clasifica, ignora reposo y vota con el smoother del modelo correspondiente."""
        label_s, conf_s, source = self._clasificar_estatico(results, features)
        self.current_source = source

        # El smoother del otro modelo no debe conservar votos viejos
        self.smoothers["2h" if source == "1h" else "1h"].reset()
        sm = self.smoothers[source]

        if label_s is None or self._norm_label(label_s) in self.IGNORE_LABELS:
            sm.reset()
            return None, 0.0, None

        confirmed, avg_conf = sm.update(label_s, conf_s)
        if confirmed:
            self.history.append(confirmed)
            self._emit_confirmed(confirmed, avg_conf)
        return label_s, conf_s, confirmed

    # ------------------------------------------------------------------
    # Dinámico
    # ------------------------------------------------------------------
    def _reset_dinamico(self):
        self.is_recording_dyn = False
        self.dyn_buffer = []
        self.still_frames_count = 0
        self.recording_start_time = None
        self.dyn_confirmed_early = False
        self.early_candidate = None
        self.early_hits = 0
        self.dyn_frames_since_eval = 0

    def _push_dinamico(self, features):
        self.dyn_buffer.append(features)
        if len(self.dyn_buffer) > 60:
            self.dyn_buffer.pop(0)

    def _clasificar_secuencia(self):
        """Clasifica la secuencia acumulada. -> (label, conf)."""
        pooled = temporal_pooling.pool_sequence(self.dyn_buffer)
        probs = self.model_d.predict_proba([pooled])[0]
        label, conf = self._decodificar(probs, self.encoder_d)
        if self._norm_label(label) in self.IGNORE_LABELS:
            return None, 0.0
        return label, conf

    def _emitir_dinamico(self, label, conf):
        """Confirma la palabra: historial, callbacks, persistencia y cooldown del estático."""
        self.history.append(label)
        self._emit_confirmed(label, conf)
        self.last_confirmed_word = label
        self.last_confirmed_conf = conf
        self.persistence_counter = self.confirmed_persistence
        self.static_cooldown = self.POST_DYN_COOLDOWN_OK
        self._reset_smoothers()

    def _confirmacion_temprana(self):
        """Evalúa la secuencia parcial. Devuelve (listo, label, conf, confirmed)."""
        no = (False, None, 0.0, None)
        if not self.EARLY_CONFIRM or self.dyn_confirmed_early or not self.model_d:
            return no

        self.dyn_frames_since_eval += 1
        if (len(self.dyn_buffer) < self.EARLY_MIN_FRAMES
                or self.dyn_frames_since_eval < self.EARLY_EVAL_EVERY):
            return no
        self.dyn_frames_since_eval = 0

        label, conf = self._clasificar_secuencia()
        if self.debug:
            print(f"[DIN-temprano] {label} ({conf:.2f}) frames={len(self.dyn_buffer)}")

        if label is not None and conf >= self.EARLY_CONF_MIN:
            if label == self.early_candidate:
                self.early_hits += 1
            else:
                self.early_candidate = label
                self.early_hits = 1
        else:
            self.early_candidate = None
            self.early_hits = 0

        if self.early_hits >= self.EARLY_HITS_REQUIRED:
            self.dyn_confirmed_early = True
            self._emitir_dinamico(label, conf)
            print(f"[DIN] {label} ({conf:.2f}) confirmada TEMPRANO, frames={len(self.dyn_buffer)}")
            return True, label, conf, label
        return no

    def _confirmar_dinamico(self):
        """
        Cierre del gesto. Si ya se confirmó temprano no se vuelve a emitir.
        Devuelve (label, conf, confirmed).
        """
        label_d, conf_d, confirmed = None, 0.0, None

        if self.dyn_confirmed_early:
            # Ya emitida: solo limpiar. (confirmed=None para no duplicar eventos)
            label_d = self.last_confirmed_word
            conf_d = self.last_confirmed_conf
        elif self.model_d and len(self.dyn_buffer) >= self.MIN_DYN_FRAMES:
            label_d, conf_d = self._clasificar_secuencia()
            print(f"[DIN] {label_d} ({conf_d:.2f}) frames={len(self.dyn_buffer)}")
            if label_d is not None and conf_d >= self.DYN_CONF_MIN:
                confirmed = label_d
                self._emitir_dinamico(label_d, conf_d)
            else:
                self.static_cooldown = self.POST_DYN_COOLDOWN_FAIL
                self._reset_smoothers()
        elif self.model_d:
            print(f"[DIN] secuencia muy corta ({len(self.dyn_buffer)} frames), descartada")
            self.static_cooldown = self.POST_DYN_COOLDOWN_FAIL
            self._reset_smoothers()

        self._reset_dinamico()
        return label_d, conf_d, confirmed

    def _actualizar_dinamico(self, features, mov):
        """
        Segmentador de gestos CON ZONA MUERTA.

        - Solo ARRANCA a grabar cuando hay MOV_FRAMES_TO_START frames consecutivos
          de movimiento real (> umbral). Así, que la mano aparezca en pantalla o un
          temblor puntual NO activa el modo dinámico.
        - Mientras graba, mantiene la grabación con el movimiento real.
        - Para terminar, requiere FRAMES_QUIETO_PARA_FINALIZAR frames quieto.
        """
        no = (False, None, 0.0, None)

        if mov > self.MOV_THRESHOLD:
            self.mov_run += 1
            self.still_run = 0
        else:
            self.mov_run = 0

        # ¿Hay movimiento "de verdad"? Necesitamos N frames consecutivos.
        movimiento_real = self.mov_run >= self.MOV_FRAMES_TO_START

        if not self.is_recording_dyn:
            if not movimiento_real:
                # Aún no arrancamos: esperamos a confirmar movimiento real
                return no
            # Arrancar grabación
            self._reset_dinamico()
            self.is_recording_dyn = True
            self.recording_start_time = time.time()
            self.still_frames_count = 0
            self._push_dinamico(features)
            return self._confirmacion_temprana()

        # Ya estamos grabando: seguir acumulando
        if mov > self.MOV_THRESHOLD:
            self.still_frames_count = 0
        else:
            self.still_frames_count += 1

        self._push_dinamico(features)

        # Seguridad: grabación demasiado larga
        if (self.recording_start_time
                and time.time() - self.recording_start_time > self.MAX_DYN_SECONDS):
            self._reset_dinamico()
            return no

        # Confirmación temprana mientras hay movimiento
        if mov > self.MOV_THRESHOLD:
            listo, label, conf, confirmed = self._confirmacion_temprana()
            if listo:
                return listo, label, conf, confirmed

        # ¿Terminó el gesto? (suficientes frames quieto)
        if self.still_frames_count >= self.FRAMES_QUIETO_PARA_FINALIZAR:
            label_d, conf_d, confirmed = self._confirmar_dinamico()
            return True, label_d, conf_d, confirmed

        return no

    # ------------------------------------------------------------------
    # Inferencia
    # ------------------------------------------------------------------
    def _sin_manos(self, results):
        self.lost_frames += 1

        if self.is_recording_dyn and self.mode != "estatico":
            # El tracker pierde la mano un instante en gestos rápidos: esperar unos frames
            if self.lost_frames < self.LOST_FRAMES_TO_FINALIZE:
                return None, 0.0, results, None
            label_d, conf_d, confirmed = self._confirmar_dinamico()
            self._reset_tracking()
            return label_d, conf_d, results, confirmed

        self._reset_smoothers()
        self._reset_dinamico()
        self._reset_tracking()
        return None, 0.0, results, None

    def predict(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        # --- Persistencia de la palabra confirmada ---
        if self.persistence_counter > 0:
            self.persistence_counter -= 1
        else:
            self.last_confirmed_word = None

        if self.static_cooldown > 0:
            self.static_cooldown -= 1

        if not results.multi_hand_landmarks:
            return self._sin_manos(results)
        self.lost_frames = 0

        manos = self._manos_ordenadas(results)
        conteo_estable = self._actualizar_conteo_manos(len(manos))
        fiables = self._manos_fiables(results)

        # Features de UNA mano (la más a la izquierda) para el modelo de 1 mano y el buffer dinámico
        features = hand_features.build_feature_vector(manos[0], rotate=self.rotate_invariant)
        mov = self._medir_movimiento(results)

        # Racha de frames quietos (para clasificar estático solo con la mano parada)
        if mov < self.MOV_THRESHOLD * 0.6:
            self.still_run += 1
        else:
            self.still_run = 0

        def estatico_permitido():
            return (conteo_estable and fiables
                    and self.still_run >= self.STATIC_STILL_FRAMES)

        # 1. MODO ESTÁTICO: ignoramos todo lo dinámico
        if self.mode == "estatico":
            if self.still_run == 0:
                self._reset_smoothers()
            if not estatico_permitido():
                return None, 0.0, results, None
            label_s, conf_s, confirmed = self._paso_estatico(results, features)
            return label_s, conf_s, results, confirmed

        # 2. MODO DINÁMICO: ignoramos las predicciones estáticas
        if self.mode == "dinamico":
            listo, label_d, conf_d, confirmed = self._actualizar_dinamico(features, mov)
            if listo:
                return label_d, conf_d, results, confirmed
            return None, 0.0, results, None

        # 3. MODO AUTO: híbrido
        if mov > self.MOV_THRESHOLD:
            # Hay movimiento: silenciar el estático y limpiar sus votos
            self.static_cooldown = self.STATIC_COOLDOWN
            self._reset_smoothers()

        listo, label_d, conf_d, confirmed = self._actualizar_dinamico(features, mov)
        if listo:
            return label_d, conf_d, results, confirmed

        # Grabando un gesto o en cooldown: el estático no debe "adivinar"
        if self.is_recording_dyn or self.static_cooldown > 0:
            return None, 0.0, results, None

        if self.still_run == 0:
            self._reset_smoothers()
        if not estatico_permitido():
            return None, 0.0, results, None

        label_s, conf_s, confirmed = self._paso_estatico(results, features)
        return label_s, conf_s, results, confirmed

    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------
    def draw_overlay(self, frame, label, confidence, results, confirmed):
        n_manos = 0
        if results and results.multi_hand_landmarks:
            n_manos = len(results.multi_hand_landmarks)
            for hand_lm in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame, hand_lm, self.mp_hands.HAND_CONNECTIONS)

        display_label = label
        display_confirmed = confirmed
        display_conf = confidence

        # Priorizar la palabra persistente (con SU confianza, no la del frame actual)
        if self.last_confirmed_word:
            display_label = self.last_confirmed_word
            display_confirmed = True
            display_conf = self.last_confirmed_conf

        if display_label:
            color = (0, 255, 0) if display_confirmed else (100, 100, 100)
            cv2.putText(frame, f"{display_label} ({display_conf*100:.0f}%)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, color, 2)
        else:
            cv2.putText(frame, "Muestra tu mano", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)

        if display_confirmed:
            cv2.putText(frame, f"CONFIRMADO: {display_label}", (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 0), 3)

        if self.is_recording_dyn:
            cv2.putText(frame, f"Capturando movimiento... ({len(self.dyn_buffer)})", (30, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        if n_manos:
            h = frame.shape[0]
            modelo = "2 manos" if self.current_source == "2h" else "1 mano"
            cv2.putText(
                frame,
                f"Manos: {n_manos} | Modelo: {modelo} | mov={self.mov_ema:.3f} (umbral {self.MOV_THRESHOLD})",
                (30, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)

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
                if not ret:
                    break
                frame = cv2.flip(frame, 1)
                label, confidence, results, confirmed = self.predict(frame)
                frame = self.draw_overlay(frame, label, confidence, results, confirmed)
                cv2.imshow(NOMBRE_VENTANA, frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                if cv2.getWindowProperty(NOMBRE_VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Traductor de señas personalizado")
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--mode", choices=["auto", "estatico", "dinamico"], default="auto")
    parser.add_argument("--debug", action="store_true",
                        help="Imprime en consola las evaluaciones de la confirmación temprana")
    args = parser.parse_args()
    translator = CustomSignTranslator(models_dir=args.models_dir, mode=args.mode,
                                      debug=args.debug)
    translator.run_webcam(camera_id=args.camera)


if __name__ == "__main__":
    main()