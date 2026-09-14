#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inicio/virtual_cam.py
Módulo de Cámara Virtual para HandTalk.

Responsable: Jason (Seguridad, Redes y Sistemas)
Punto 4.2 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.

Provee la clase `VirtualCamManager` desacoplada para publicar video con
subtítulos en tiempo real hacia aplicaciones como Google Meet, Zoom o Teams.
Implementa detección automática de plataforma (Linux v4l2loopback vs Windows OBS),
conversión de espacio de color (BGR -> RGB) y degradación suave (graceful fallback)
para garantizar que la aplicación nunca colapse si el driver no está disponible.
"""

import logging
import platform
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

# Configuración del logger
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("HandTalk.VirtualCam")


class VirtualCamManager:
    """
    Gestor de Cámara Virtual con soporte multiplataforma (Linux / Windows)
    y tolerancia a fallos.
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        device: Optional[str] = None,
        auto_start: bool = False,
    ):
        """
        Inicializa el gestor de cámara virtual.

        Args:
            width: Ancho del cuadro de video (por defecto 640).
            height: Alto del cuadro de video (por defecto 480).
            fps: Cuadros por segundo deseados (por defecto 30).
            device: Dispositivo específico (ej. '/dev/video10' en Linux).
            auto_start: Si es True, intenta abrir la cámara inmediatamente.
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.os_name = platform.system()
        self.device = device
        self._cam = None
        self._is_active = False
        self._lock = threading.Lock()

        # Última traducción confirmada (Contrato EVENTOS.md)
        self.last_confirmed_word: str = ""
        self.last_confidence: float = 0.0
        self.last_timestamp: str = ""
        self.last_update_time: float = 0.0

        # Resolver backend según sistema operativo
        if self.os_name == "Linux":
            if self.device is None:
                self.device = "/dev/video10"
            self.backend = "v4l2loopback"
        elif self.os_name == "Windows":
            self.backend = "obs"
        else:
            self.backend = "default"

        if auto_start:
            self.start()

    @property
    def is_active(self) -> bool:
        """Indica si la cámara virtual está actualmente inicializada y enviando frames."""
        with self._lock:
            return self._is_active and self._cam is not None

    def start(self) -> bool:
        """
        Inicia la cámara virtual. Captura cualquier excepción si el driver no está
        presente o faltan permisos, asegurando degradación suave sin crashear.

        Returns:
            bool: True si la cámara se inició con éxito, False en caso contrario.
        """
        with self._lock:
            if self._is_active and self._cam is not None:
                logger.info("La cámara virtual ya se encuentra en ejecución.")
                return True

            try:
                import pyvirtualcam
            except ImportError:
                logger.warning(
                    "Librería 'pyvirtualcam' no instalada. "
                    "Instale las dependencias con 'pip install pyvirtualcam>=0.11.0'. "
                    "HandTalk continuará operando en modo GUI local."
                )
                self._is_active = False
                return False

            try:
                kwargs = {
                    "width": self.width,
                    "height": self.height,
                    "fps": self.fps,
                    "fmt": pyvirtualcam.PixelFormat.RGB,
                }

                if self.os_name == "Linux":
                    kwargs["device"] = self.device
                    logger.info(
                        "Iniciando VirtualCam en Linux con backend '%s' en dispositivo '%s' (%dx%d @ %dfps)...",
                        self.backend,
                        self.device,
                        self.width,
                        self.height,
                        self.fps,
                    )
                elif self.os_name == "Windows":
                    kwargs["backend"] = "obs"
                    logger.info(
                        "Iniciando VirtualCam en Windows con backend 'obs' DirectShow (%dx%d @ %dfps)...",
                        self.width,
                        self.height,
                        self.fps,
                    )
                else:
                    logger.info("Iniciando VirtualCam en plataforma %s...", self.os_name)

                self._cam = pyvirtualcam.Camera(**kwargs)
                self._is_active = True
                logger.info("✓ Cámara Virtual inicializada exitosamente: %s", self._cam.device)
                return True

            except Exception as exc:
                self._cam = None
                self._is_active = False
                logger.warning(
                    "No se pudo iniciar la Cámara Virtual (%s: %s). "
                    "Degradación suave activa: HandTalk seguirá funcionando normalmente sin salida virtual. "
                    "(En Linux verifique 'sudo modprobe v4l2loopback devices=1 video_nr=10 exclusive_caps=1'. "
                    "En Windows instale OBS Studio para disponer del driver DirectShow).",
                    type(exc).__name__,
                    exc,
                )
                return False

    def stop(self) -> None:
        """Detiene y libera la cámara virtual de forma segura."""
        with self._lock:
            if self._cam is not None:
                try:
                    self._cam.close()
                except Exception as e:
                    logger.debug("Error al cerrar cámara virtual: %s", e)
                finally:
                    self._cam = None
            self._is_active = False
            logger.info("Cámara Virtual detenida.")

    def toggle(self) -> bool:
        """
        Alterna el estado de la cámara virtual (On/Off).

        Returns:
            bool: Nuevo estado activo de la cámara virtual.
        """
        if self.is_active:
            self.stop()
            return False
        else:
            return self.start()

    def on_translation_confirmed(self, word: str, confidence: float, timestamp: Optional[str] = None) -> None:
        """
        Callback de integración con el Contrato de Interfaz EVENTOS.md.
        Almacena la palabra confirmada para superponerla en los frames salientes.

        Args:
            word: Palabra o etiqueta de la seña confirmada.
            confidence: Nivel de certeza del modelo (0.0 a 1.0).
            timestamp: Marca de tiempo ISO 8601 o None.
        """
        self.last_confirmed_word = str(word).strip()
        self.last_confidence = float(confidence)
        self.last_timestamp = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.last_update_time = time.time()
        logger.debug("VirtualCam recibió traducción confirmada: '%s' (%.2f)", word, confidence)

    def draw_subtitle_overlay(self, frame: np.ndarray, text: Optional[str] = None) -> np.ndarray:
        """
        Dibuja un banner con subtítulo de alto contraste sobre el frame.

        Args:
            frame: Imagen OpenCV en formato BGR.
            text: Texto opcional a dibujar. Si es None, usa `last_confirmed_word`.

        Returns:
            np.ndarray: Frame con el banner dibujado.
        """
        if text is None:
            # Mostrar la última palabra si fue confirmada hace menos de 4 segundos
            if self.last_confirmed_word and (time.time() - self.last_update_time < 4.0):
                text = self.last_confirmed_word
            else:
                text = ""

        if not text:
            return frame

        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.7, min(1.3, w / 600.0))
        thickness = max(2, int(font_scale * 2))

        (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        # Dimensiones y posición del banner (inferior centrado)
        padding_x = 18
        padding_y = 12
        box_w = text_w + (padding_x * 2)
        box_h = text_h + (padding_y * 2)

        box_x = max(10, (w - box_w) // 2)
        box_y = max(10, h - box_h - 25)

        # Crear capa para rectángulo semitransparente oscuro
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (box_x, box_y),
            (box_x + box_w, box_y + box_h),
            (20, 20, 20),
            cv2.FILLED,
        )
        # Borde decorativo con color acento cyan/esmeralda
        cv2.rectangle(
            overlay,
            (box_x, box_y),
            (box_x + box_w, box_y + box_h),
            (0, 220, 130),
            2,
        )

        # Mezclar con transparencia (alpha 0.75)
        alpha = 0.75
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Dibujar texto blanco con sombra sutil
        text_origin = (box_x + padding_x, box_y + box_h - padding_y - 2)
        cv2.putText(
            frame,
            text,
            (text_origin[0] + 1, text_origin[1] + 1),
            font,
            font_scale,
            (0, 0, 0),
            thickness + 1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            text,
            text_origin,
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

        return frame

    def send_frame(self, frame_bgr: np.ndarray, overlay_text: Optional[str] = None) -> bool:
        """
        Recibe un cuadro OpenCV en formato BGR, aplica el overlay si corresponde,
        lo convierte a RGB y lo transmite a la cámara virtual.

        Args:
            frame_bgr: Matriz numpy con la imagen en BGR.
            overlay_text: Texto opcional específico para este frame.

        Returns:
            bool: True si el frame fue enviado, False si la cámara está inactiva.
        """
        with self._lock:
            if not self._is_active or self._cam is None:
                return False

            try:
                # 1. Ajustar resolución si el frame entrante difiere
                h, w = frame_bgr.shape[:2]
                if w != self.width or h != self.height:
                    processed = cv2.resize(frame_bgr, (self.width, self.height))
                else:
                    processed = frame_bgr.copy()

                # 2. Dibujar overlay si hay texto
                processed = self.draw_subtitle_overlay(processed, overlay_text)

                # 3. Conversión de color obligatoria: OpenCV BGR -> pyvirtualcam RGB
                frame_rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)

                # 4. Envío al driver y sincronización de tasa de refresco
                self._cam.send(frame_rgb)
                self._cam.sleep_until_next_frame()
                return True

            except Exception as e:
                logger.error("Error al transmitir frame a la cámara virtual: %s", e)
                return False


def main():
    """Prueba rápida de funcionamiento y tolerancia a fallos del módulo."""
    print("=" * 60)
    print("HandTalk - Comprobación de Cámara Virtual (Punto 4.2)")
    print("=" * 60)
    print(f"Sistema Operativo detectado: {platform.system()} ({platform.release()})")

    manager = VirtualCamManager(width=640, height=480, fps=30)
    print(f"Dispositivo objetivo: {manager.device or 'OBS VirtualCam (Windows)'}")
    print("Intentando iniciar la cámara virtual...")

    success = manager.start()
    if not success:
        print("\n[INFO] Degradación suave verificada correctamente.")
        print("[INFO] El driver no está cargado o no está instalado.")
        print("[INFO] HandTalk seguirá funcionando normalmente sin fallar.")
        print("=" * 60)
        return

    print("\n[OK] ¡Cámara Virtual abierta con éxito!")
    print("Enviando 90 cuadros de prueba sintéticos con subtítulos...")

    palabras_demo = ["HOLA", "BUENOS DIAS", "GRACIAS", "HANDTALK"]
    try:
        for i in range(90):
            # Generar fondo degradado de prueba
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:, :, 0] = int(i * 2.5) % 255  # Canal B
            frame[:, :, 1] = 60                   # Canal G
            frame[:, :, 2] = 120                  # Canal R

            cv2.putText(
                frame,
                f"HandTalk Virtual Cam Test - Frame {i+1}",
                (30, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (200, 200, 200),
                2,
            )

            # Simular confirmación de evento cada 25 frames
            idx_palabra = (i // 25) % len(palabras_demo)
            manager.on_translation_confirmed(palabras_demo[idx_palabra], 0.95)

            manager.send_frame(frame)

        print("[OK] Transmisión de prueba completada exitosamente.")
    finally:
        manager.stop()
        print("=" * 60)


if __name__ == "__main__":
    main()
