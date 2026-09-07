#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hand_features.py

Extraccion y normalizacion de caracteristicas de la mano a partir de los
landmarks que entrega MediaPipe Hands.

RESCATADO Y MEJORADO de:
- sign_language_capture_gui.py -> extract_landmarks(), calculate_angles()

MEJORA CLAVE respecto al original:
El original guardaba landmark.x, landmark.y, landmark.z tal cual los entrega
MediaPipe (normalizados 0-1 respecto al FRAME de la camara). Esto significa
que la misma seña, hecha mas cerca o mas lejos de la camara, o en una zona
distinta del encuadre, generaba vectores de caracteristicas diferentes.

Aqui, ademas de las coordenadas relativas al frame, se calcula una version
CANONICA de los landmarks:
  1. Traslacion: la muñeca (landmark 0) pasa a ser el origen (0,0,0).
  2. Escala: se divide todo por una distancia de referencia de la propia
     mano (muñeca -> nudillo del dedo medio), asi la distancia a la camara
     deja de importar.
  3. (Opcional) Rotacion: se alinea el eje muñeca->dedo medio con el eje Y,
     para que la inclinacion de la mano en el encuadre no afecte tanto.

Esto es lo que permite que el sistema funcione igual de bien en interiores
y exteriores, con manos grandes o pequeñas en la imagen: MediaPipe ya se
encarga de la parte dificil (encontrar la mano pese a fondo/luz variables),
y esta normalizacion se encarga de que la clasificacion no dependa de en
que parte del cuadro, a que distancia o con que inclinacion se hizo la seña.
"""

import numpy as np

# Indices de MediaPipe Hands
WRIST = 0
MIDDLE_MCP = 9  # nudillo base del dedo medio, usado como referencia de escala

FINGER_CHAINS = [
    [0, 1, 2, 3, 4],      # pulgar
    [0, 5, 6, 7, 8],       # indice
    [0, 9, 10, 11, 12],    # medio
    [0, 13, 14, 15, 16],   # anular
    [0, 17, 18, 19, 20],   # meñique
]

FINGERTIPS = [4, 8, 12, 16, 20]


def extract_raw_landmarks(hand_landmarks):
    """Devuelve un array (21, 3) con x,y,z tal como los da MediaPipe."""
    pts = np.array(
        [[lm.x, lm.y, lm.z] for lm in hand_landmarks.landmark],
        dtype=np.float32,
    )
    return pts


def normalize_landmarks(raw_points, rotate=True):
    """
    Normaliza landmarks para que sean invariantes a posicion y escala,
    y opcionalmente a rotacion en el plano de la imagen.

    raw_points: array (21, 3)
    return: array (21, 3) normalizado
    """
    pts = raw_points.copy()

    # 1. Traslacion: origen en la muñeca
    pts -= pts[WRIST]

    # 2. Escala: normalizar por tamaño de la mano
    ref_dist = np.linalg.norm(pts[MIDDLE_MCP]) + 1e-6
    pts /= ref_dist

    # 3. Rotacion (opcional): alinear muñeca->dedo medio con el eje Y
    if rotate:
        ref_vec = pts[MIDDLE_MCP][:2]  # solo X,Y para rotacion 2D
        angle = np.arctan2(ref_vec[0], ref_vec[1])  # angulo respecto a Y
        cos_a, sin_a = np.cos(-angle), np.sin(-angle)
        rot = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
        pts[:, :2] = pts[:, :2] @ rot.T

    return pts


def calculate_finger_angles(points):
    """
    Angulo de flexion de cada dedo (muñeca - nudillo medio - punta).
    Sirve para distinguir dedos extendidos vs doblados, algo que las
    coordenadas normalizadas por si solas expresan de forma menos directa.
    """
    angles = []
    for chain in FINGER_CHAINS:
        p1, p2, p3 = points[chain[0]], points[chain[2]], points[chain[4]]
        v1, v2 = p1 - p2, p3 - p2
        cos_angle = np.dot(v1, v2) / (
            np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6
        )
        angles.append(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
    return np.array(angles, dtype=np.float32)


def calculate_fingertip_distances(points):
    """
    Distancias entre puntas de dedos consecutivas (y pulgar-indice, clave
    para gestos de pinza). Ayuda a distinguir señas donde la forma general
    de la mano es parecida pero los dedos se tocan o se separan distinto.
    """
    dists = []
    for i in range(len(FINGERTIPS)):
        for j in range(i + 1, len(FINGERTIPS)):
            d = np.linalg.norm(points[FINGERTIPS[i]] - points[FINGERTIPS[j]])
            dists.append(d)
    return np.array(dists, dtype=np.float32)


def build_feature_vector(hand_landmarks, rotate=True,
                          include_angles=True, include_distances=True):
    """
    Construye el vector de caracteristicas final para UNA mano detectada.
    Este es el vector que se guarda al capturar dataset y el que se le
    pasa al clasificador para predecir.
    """
    raw = extract_raw_landmarks(hand_landmarks)
    norm = normalize_landmarks(raw, rotate=rotate)

    features = [norm.flatten()]  # 21*3 = 63 valores

    if include_angles:
        features.append(calculate_finger_angles(norm))
    if include_distances:
        features.append(calculate_fingertip_distances(norm))

    return np.concatenate(features).astype(np.float32)


def build_two_hand_feature_vector(multi_hand_landmarks, multi_handedness=None,
                                   rotate=True, include_angles=True,
                                   include_distances=True):
    """
    Igual que build_feature_vector pero soporta hasta 2 manos, ordenadas
    Izquierda/Derecha cuando MediaPipe entrega esa informacion. Si solo
    hay una mano detectada, la mitad correspondiente se rellena con ceros.
    Util para señas que se hacen con las dos manos.
    """
    single_len = len(
        build_feature_vector(
            multi_hand_landmarks[0], rotate, include_angles, include_distances
        )
    ) if multi_hand_landmarks else 0

    left_vec = np.zeros(single_len, dtype=np.float32)
    right_vec = np.zeros(single_len, dtype=np.float32)

    for idx, hand_lm in enumerate(multi_hand_landmarks):
        vec = build_feature_vector(hand_lm, rotate, include_angles, include_distances)
        label = "Right"
        if multi_handedness and idx < len(multi_handedness):
            label = multi_handedness[idx].classification[0].label
        if label == "Left":
            left_vec = vec
        else:
            right_vec = vec

    return np.concatenate([left_vec, right_vec])


def feature_vector_length(rotate=True, include_angles=True, include_distances=True, two_hands=False):
    """Utilidad para saber de antemano el tamaño del vector (para validar modelos)."""
    n = 63
    if include_angles:
        n += 5
    if include_distances:
        n += 10
    return n * 2 if two_hands else n
