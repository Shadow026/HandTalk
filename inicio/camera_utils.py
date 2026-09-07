#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
camera_utils.py

RESCATADO de:
- camera_config.py            -> read_default_camera(), write_default_camera()
- sign_language_capture_gui.py -> scan_cameras()
- translator_realtime.py / translator_headless.py -> logica de fallback al
  abrir la camara (probar varios indices si el default falla)

Se limpio la dependencia de Tkinter para que estas funciones se puedan usar
tanto desde una GUI como desde un script de linea de comandos.
"""

import json
import os
import cv2

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_config.json")


def read_default_camera():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                val = data.get("default_camera")
                return int(val) if val is not None else None
    except Exception:
        return None
    return None


def write_default_camera(index):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"default_camera": int(index)}, f)
        return True
    except Exception:
        return False


def scan_cameras(max_devices=6):
    """Devuelve la lista de indices de camara que se pueden abrir."""
    found = []
    for i in range(max_devices):
        try:
            cap = cv2.VideoCapture(i)
            if cap is not None and cap.isOpened():
                found.append(i)
            cap.release()
        except Exception:
            continue
    return found


def open_camera(camera_id=None, width=1280, height=720, max_fallback=5):
    """
    Abre una camara con fallback automatico:
    1. Intenta con camera_id (o con la guardada como default si camera_id es None).
    2. Si falla, prueba indices 0..max_fallback hasta encontrar una que funcione.
    Devuelve el objeto cv2.VideoCapture ya configurado, o None si no hay camara.
    """
    if camera_id is None:
        camera_id = read_default_camera()
        if camera_id is None:
            camera_id = 0

    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        for i in range(max_fallback):
            cap.release()
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                camera_id = i
                break
        else:
            return None, None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap, camera_id
