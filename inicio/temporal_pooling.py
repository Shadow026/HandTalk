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
    Convierte una secuencia de vectores en un único vector resumen mediante muestreo estratégico.

    En lugar de promedios, tomamos frames en puntos clave (0%, 25%, 50%, 75%, 100%)
    para preservar la trayectoria y el orden del movimiento.

    Args:
        secuencia (list o np.array): Lista de vectores de landmarks.
                                    Ej: [[f1, f2...], [f1, f2...], ...]

    Returns:
        np.array: Vector concatenado de los frames muestreados.
    """
    if not secuencia or len(secuencia) == 0:
        return np.array([])

    data = np.asarray(secuencia, dtype=np.float32)
    n_frames = len(data)

    # Definimos los índices de muestreo (inicio, 25%, 50%, 75%, fin)
    indices = [
        0,
        n_frames // 4,
        n_frames // 2,
        (3 * n_frames) // 4,
        n_frames - 1
    ]

    # Seleccionamos los vectores en esos puntos
    sampled_frames = [data[i] for i in indices]

    # Concatenamos todos los vectores muestreados en uno solo plano
    pooled_vector = np.concatenate(sampled_frames)

    return pooled_vector

