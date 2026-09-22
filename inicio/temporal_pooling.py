#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
temporal_pooling.py

Este módulo implementa la estrategia de "Temporal Pooling" para el reconocimiento
de señas dinámicas.

En lugar de usar redes neuronales recurrentes (como LSTM), que requieren miles de
muestras, convertimos una SECUENCIA de vectores de landmarks en un UNICO vector
estático que resume el movimiento.

Estrategia: Para cada característica (feature) de la secuencia:
  1. Media: Representa la postura promedio del gesto.
  2. Desviación Estándar: Representa la amplitud del movimiento (qué tanto varió).
  3. Delta (Final - Inicial): Representa la dirección neta del desplazamiento.

Si el vector de una sola frame tiene N elementos, el vector pooled tendrá 3*N.
Esto permite seguir usando clasificadores eficientes como RandomForestClassifier.
"""

import numpy as np

def pool_sequence(secuencia):
    """
    Convierte una secuencia de vectores en un único vector resumen.

    Args:
        secuencia (list o np.array): Lista de vectores de landmarks.
                                    Ej: [[f1, f2...], [f1, f2...], ...]

    Returns:
        np.array: Vector concatenado [medias, stds, deltas]
    """
    if not secuencia or len(secuencia) == 0:
        return np.array([])

    # Convertir a array de numpy para operaciones vectorizadas
    data = np.asarray(secuencia, dtype=np.float32)

    # 1. Media (Average posture)
    means = np.mean(data, axis=0)

    # 2. Desviación Estándar (Movement amplitude)
    stds = np.std(data, axis=0)

    # 3. Delta (Net movement: Last frame - First frame)
    deltas = data[-1] - data[0]

    # Concatenar todo en un solo vector plano
    pooled_vector = np.concatenate([means, stds, deltas])

    return pooled_vector
