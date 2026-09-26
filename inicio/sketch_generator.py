#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sketch_generator.py

Genera un boceto (diagrama de puntos y líneas) de cada seña a partir de los
landmarks normalizados guardados en el dataset (ver dataset_manager.py),
usando las cadenas de dedos (FINGER_CHAINS) de hand_features.py para saber
qué puntos conectar. Es la Tarea 2 de Herber (ver PLAN_DE_TRABAJO_EQUIPO.md
sección 4.1): sirve para alimentar una pantalla tipo "diccionario" con todas
las palabras creadas por el usuario (ver diccionario_gui.py).

De dónde salen los puntos a dibujar
------------------------------------
Cada muestra guardada por dataset_manager.save_sample() trae un campo
"features" que es el vector que arma hand_features.build_feature_vector():

    features = [landmarks_normalizados.flatten()]   <- SIEMPRE van primero
             + [angulos_de_dedos]                    <- opcional
             + [distancias_entre_puntas]              <- opcional

Es decir, los primeros 63 valores (21 puntos x,y,z) de cada mano SIEMPRE son
los landmarks normalizados aplanados, sin importar si se incluyeron ángulos
o distancias después. Para señas de dos manos (ver
build_two_hand_feature_vector), el vector es la mano IZQUIERDA completa
seguida de la DERECHA completa, en ese orden fijo.

Este módulo no vuelve a tocar la cámara ni MediaPipe: solo lee los JSON ya
guardados en custom_dataset/ y dibuja con Pillow.
"""

import glob
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import dataset_manager
import hand_features

# Tamaño en features de UNA mano con la configuracion por defecto de
# hand_features.build_feature_vector (63 landmarks + 5 angulos + 10 distancias).
# Se usa solo para decidir si una muestra trae una o dos manos; el dibujo en
# si siempre usa nada mas los primeros 63 valores de cada mitad.
_SINGLE_HAND_LEN_HINT = 63 + 5 + 10  # 78

DEFAULT_SKETCH_DIR = "sketches"
DEFAULT_SIZE = 320
DEFAULT_MARGIN = 36
DEFAULT_BG = (255, 255, 255)
DEFAULT_LINE_COLOR = (30, 30, 30)
DEFAULT_POINT_COLOR = (200, 40, 40)
DEFAULT_WRIST_COLOR = (30, 90, 200)


# ----------------------------------------------------------------------
# 1. Extraer puntos (x, y) por mano a partir del vector de features guardado
# ----------------------------------------------------------------------
def extract_hand_points(features):
    """
    Dado el 'features' de UNA muestra del dataset, devuelve una lista de
    arrays (21, 2) -- uno por cada mano detectada en esa muestra (1 o 2).

    Los landmarks normalizados dejan la muñeca en el origen (0,0) y ya
    vienen escalados por el tamaño de la propia mano (ver
    hand_features.normalize_landmarks), asi que estos puntos ya estan
    listos para dibujarse sin importar el tamaño real de la mano de quien
    capturo la seña.
    """
    features = np.asarray(features, dtype=np.float32)
    total = len(features)

    # Heuristica simple: si el vector es par y >= 2x el largo minimo de una
    # mano (63), asumimos que son dos mitades (izquierda + derecha) como
    # las arma build_two_hand_feature_vector. Si no, es de una sola mano.
    if total >= 2 * 63 and total % 2 == 0:
        half = total // 2
        halves = [features[:half], features[half:]]
    else:
        halves = [features]

    hands = []
    for half in halves:
        if len(half) < 63:
            continue  # muestra corrupta o demasiado corta, se ignora
        points_3d = half[:63].reshape(21, 3)
        points_2d = points_3d[:, :2]
        if np.allclose(points_2d, 0.0):
            continue  # mano "vacia" (rellenada con ceros, no se detecto)
        hands.append(points_2d)

    return hands


# ----------------------------------------------------------------------
# 2. Cargar y promediar las muestras de una palabra
# ----------------------------------------------------------------------
def load_word_hand_samples(word, dataset_dir=dataset_manager.DEFAULT_DATASET_DIR):
    """
    Carga todas las muestras ESTATICAS guardadas para `word` y devuelve una
    lista de "manos" (cada una un array (21,2)), una por cada mano detectada
    en cada muestra. Si una muestra es dinamica (una seña con movimiento),
    se usa su frame de en medio como representante estatico del boceto.
    """
    pattern = os.path.join(dataset_dir, f"{word}_*.json")
    hands_per_sample = []

    for path in sorted(glob.glob(pattern)):
        import json
        with open(path, "r", encoding="utf-8") as f:
            sample = json.load(f)

        if sample.get("label") != word:
            continue

        features = sample["features"]
        if sample.get("type") == "dynamic":
            # Una muestra dinamica es una lista de vectores (uno por frame);
            # tomamos el de en medio como pose representativa para el boceto.
            if not features:
                continue
            features = features[len(features) // 2]

        hands_per_sample.append(extract_hand_points(features))

    return hands_per_sample


def average_hand_pose(hands_per_sample):
    """
    Promedia los puntos de todas las muestras para obtener un boceto mas
    estable (menos ruidoso que usar una sola captura). Promedia por
    separado cada "mano" segun su posicion (mano 0 = la primera detectada
    en cada muestra -- para senas de una sola mano coincide siempre; para
    senas de dos manos, build_two_hand_feature_vector ya deja la izquierda
    primero y la derecha segunda de forma consistente).

    Devuelve una lista de arrays (21,2), una por mano (1 o 2), o [] si no
    hay muestras validas.
    """
    if not hands_per_sample:
        return []

    max_hands = max(len(h) for h in hands_per_sample)
    averaged = []
    for hand_idx in range(max_hands):
        pts_for_this_hand = [
            sample[hand_idx] for sample in hands_per_sample
            if len(sample) > hand_idx
        ]
        if not pts_for_this_hand:
            continue
        averaged.append(np.mean(np.stack(pts_for_this_hand, axis=0), axis=0))

    return averaged


# ----------------------------------------------------------------------
# 3. Dibujar el boceto con Pillow
# ----------------------------------------------------------------------
def _fit_points_to_canvas(points, width, height, margin):
    """Escala y centra un array (21,2) para que quepa en un lienzo width x height."""
    min_xy = points.min(axis=0)
    max_xy = points.max(axis=0)
    span = np.maximum(max_xy - min_xy, 1e-6)

    usable_w = width - 2 * margin
    usable_h = height - 2 * margin
    scale = min(usable_w, usable_h) / span.max()

    centered = points - (min_xy + max_xy) / 2.0
    pixel_pts = centered * scale
    pixel_pts[:, 0] += width / 2.0
    pixel_pts[:, 1] += height / 2.0
    return pixel_pts


def draw_hand_sketch(hands_points, word=None, size=DEFAULT_SIZE, margin=DEFAULT_MARGIN,
                      bg_color=DEFAULT_BG, line_color=DEFAULT_LINE_COLOR,
                      point_color=DEFAULT_POINT_COLOR, wrist_color=DEFAULT_WRIST_COLOR,
                      line_width=4, point_radius=6):
    """
    hands_points: lista de arrays (21,2) -- una o dos manos ya promediadas
                  (ver average_hand_pose). Si hay dos manos, se dibujan
                  ambas en el mismo lienzo, separadas horizontalmente para
                  que no queden superpuestas (cada una tiene su propio
                  origen en (0,0) porque estan normalizadas a su propia
                  muñeca).
    Devuelve una imagen PIL.Image lista para guardar o mostrar.
    """
    img = Image.new("RGB", (size, size), bg_color)
    draw = ImageDraw.Draw(img)

    n_hands = len(hands_points)
    if n_hands == 0:
        draw.text((margin, size // 2), "(sin datos)", fill=line_color)
        return img

    # Si hay dos manos, cada una se dibuja en su propia mitad del lienzo.
    slot_width = size // n_hands

    for slot, points in enumerate(hands_points):
        # El margen se limita a una fraccion del ancho disponible por mano:
        # sin este limite, en miniaturas pequeñas (o con 2 manos, que ya
        # dividen el lienzo a la mitad) un margen fijo grande dejaba casi
        # sin espacio util para dibujar la mano.
        local_margin = max(4, min(margin, slot_width // 5, size // 5))
        pixel_pts = _fit_points_to_canvas(points, slot_width, size, local_margin)
        pixel_pts[:, 0] += slot * slot_width  # desplazar a su mitad del lienzo

        for chain in hand_features.FINGER_CHAINS:
            chain_pts = [tuple(pixel_pts[i]) for i in chain]
            draw.line(chain_pts, fill=line_color, width=line_width, joint="curve")

        for i, (x, y) in enumerate(pixel_pts):
            color = wrist_color if i == hand_features.WRIST else point_color
            r = point_radius + 2 if i == hand_features.WRIST else point_radius
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

    if word:
        draw.text((margin // 2, size - margin // 2 - 4), word, fill=line_color)

    return img


# ----------------------------------------------------------------------
# 4. Funcion de alto nivel: de una palabra a un archivo PNG
# ----------------------------------------------------------------------
def generate_sketch_for_word(word, dataset_dir=dataset_manager.DEFAULT_DATASET_DIR,
                              output_dir=DEFAULT_SKETCH_DIR, **draw_kwargs):
    """
    Genera (o regenera) el boceto de `word` a partir de sus muestras
    guardadas y lo guarda como PNG en output_dir/word.png.
    Devuelve la ruta del PNG generado, o None si la palabra no tiene
    muestras validas todavia.
    """
    hands_per_sample = load_word_hand_samples(word, dataset_dir)
    averaged = average_hand_pose(hands_per_sample)
    if not averaged:
        return None

    img = draw_hand_sketch(averaged, word=word, **draw_kwargs)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{word}.png")
    img.save(out_path)
    return out_path


def generate_all_sketches(dataset_dir=dataset_manager.DEFAULT_DATASET_DIR,
                           output_dir=DEFAULT_SKETCH_DIR, **draw_kwargs):
    """
    Genera el boceto de TODAS las palabras que existen actualmente en el
    dataset. Pensado para llamarse cada vez que se abre la pantalla de
    catalogo/diccionario (ver diccionario_gui.py), asi siempre se ve
    actualizada aunque se hayan agregado palabras nuevas.
    Devuelve un dict {palabra: ruta_png_o_None}.
    """
    words = dataset_manager.get_existing_words(dataset_dir)
    return {
        word: generate_sketch_for_word(word, dataset_dir, output_dir, **draw_kwargs)
        for word in words
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Genera bocetos (PNG) de las señas guardadas en el dataset."
    )
    parser.add_argument("--dataset", default=dataset_manager.DEFAULT_DATASET_DIR)
    parser.add_argument("--output", default=DEFAULT_SKETCH_DIR)
    parser.add_argument("--word", default=None, help="Genera solo esta palabra (default: todas).")
    args = parser.parse_args()

    if args.word:
        path = generate_sketch_for_word(args.word, args.dataset, args.output)
        print(f"[OK] {args.word} -> {path}" if path else f"[WARN] Sin muestras para '{args.word}'")
    else:
        resultados = generate_all_sketches(args.dataset, args.output)
        for word, path in resultados.items():
            print(f"[OK] {word} -> {path}" if path else f"[WARN] Sin muestras para '{word}'")
