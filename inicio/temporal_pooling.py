#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
temporal_pooling.py

Convierte una secuencia de vectores de landmarks (una seña CON movimiento,
capturada frame a frame) en UN SOLO vector de tamaño fijo, para poder
seguir usando el mismo tipo de clasificador (RandomForest) que ya usan
para señas estáticas, sin necesitar una red recurrente (LSTM/GRU).

IMPORTANTE: esta misma función debe usarse tanto al entrenar
(train_dinamico.py) como al predecir en vivo (realtime_translator.py).
Si la lógica de pooling difiere entre entrenamiento e inferencia, el
modelo va a recibir vectores con una "forma" distinta a la que aprendió
y las predicciones no van a tener sentido.
"""

import numpy as np


def pool_sequence(secuencia):
    """
    secuencia: lista o array de forma (n_frames, n_features) — la secuencia
               de vectores de landmarks de UNA seña dinámica.

    Devuelve un vector 1D de tamaño (3 * n_features), concatenando:
      - promedio de cada feature a lo largo del tiempo (la "postura media")
      - desviación estándar de cada feature (cuánto varió = qué tanto se movió)
      - diferencia entre el último y el primer frame (dirección neta del movimiento)

    Funciona igual sin importar cuántos frames tenga la secuencia (no
    requiere que todas las capturas duren exactamente lo mismo), a
    diferencia de una LSTM que normalmente necesita secuencias de
    longitud fija o padding.
    """
    secuencia = np.asarray(secuencia, dtype=np.float32)

    if secuencia.ndim != 2:
        raise ValueError(
            f"Se esperaba una secuencia 2D (frames, features), se recibió forma {secuencia.shape}"
        )

    promedio = secuencia.mean(axis=0)
    desviacion = secuencia.std(axis=0)
    delta_inicio_fin = secuencia[-1] - secuencia[0]

    return np.concatenate([promedio, desviacion, delta_inicio_fin]).astype(np.float32)


def longitud_vector_pooled(n_features_por_frame):
    """Tamaño que va a tener el vector resultante de pool_sequence(), dado
    el largo del feature_vector de un solo frame (útil para meta.json)."""
    return n_features_por_frame * 3