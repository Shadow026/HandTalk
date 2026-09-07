#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoothing.py

RESCATADO Y GENERALIZADO de la logica de confirmacion de predicciones
presente en translator_realtime.py y translator_unified.py:
  - deque de confianza para promediar (hand_confidence_history)
  - conteo de frames consecutivos con la misma clase (consecutive_predictions)
  - retraso minimo entre dos detecciones confirmadas (DETECTION_DELAY)

Esta logica es la responsable de que el traductor NO parpadee entre
predicciones (ruido frame a frame) y de que una seña solo se "confirme"
cuando el modelo estuvo consistentemente seguro varios frames seguidos.
Se mantiene igual de valiosa en el nuevo sistema basado en landmarks.
"""

import time
from collections import deque


class PredictionSmoother:
    def __init__(self, confidence_threshold=0.75, smoothing_window=5,
                 confirmation_frames=5, detection_delay_ms=500):
        self.confidence_threshold = confidence_threshold
        self.confidence_history = deque(maxlen=smoothing_window)
        self.confirmation_frames = confirmation_frames
        self.detection_delay_ms = detection_delay_ms

        self._consecutive = None  # [label, count]
        self._last_confirmed_time = 0

    def reset(self):
        self.confidence_history.clear()
        self._consecutive = None

    def update(self, label, confidence):
        """
        Alimenta el suavizador con la prediccion cruda de un frame.
        Devuelve (label_confirmado_o_None, confianza_promedio).
        """
        if label is None:
            self.reset()
            return None, 0.0

        self.confidence_history.append(confidence)
        avg_confidence = sum(self.confidence_history) / len(self.confidence_history)

        if confidence < self.confidence_threshold or avg_confidence < self.confidence_threshold * 0.9:
            self._consecutive = None
            return None, avg_confidence

        if self._consecutive and self._consecutive[0] == label:
            self._consecutive[1] += 1
        else:
            self._consecutive = [label, 1]

        now_ms = time.time() * 1000
        enough_frames = self._consecutive[1] >= self.confirmation_frames
        enough_delay = (now_ms - self._last_confirmed_time) >= self.detection_delay_ms

        if enough_frames and enough_delay:
            self._last_confirmed_time = now_ms
            self._consecutive[1] = 0
            return label, avg_confidence

        return None, avg_confidence
