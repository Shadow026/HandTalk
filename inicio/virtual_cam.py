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
    Gestor de Cámara Virtual con soporte multiplataforma (Linux / Windows),
    desacoplamiento por hilos (non-blocking frame sender) y tolerancia a fallos.
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        device: Optional[str] = None,
        auto_start: bool = False,
        mirror_flip: bool = False,
        subtitle_duration: float = 3.8,
        banner_position: str = "bottom_safe",
    ):
        """
        Inicializa el gestor de cámara virtual.

        Args:
            width: Ancho del cuadro de video (por defecto 1280, estándar 16:9 HD).
            height: Alto del cuadro de video (por defecto 720, estándar 16:9 HD).
            fps: Cuadros por segundo deseados (por defecto 30).
            device: Dispositivo específico (ej. '/dev/video10' en Linux).
            auto_start: Si es True, intenta abrir la cámara inmediatamente.
            mirror_flip: Si es True, compensa el reflejo de apps invirtiendo el video
                         pero conservando el texto derecho.
            subtitle_duration: Tiempo en segundos que persiste un subtítulo (por defecto 3.8s).
            banner_position: 'bottom_safe' (zona segura elevada contra barras de Teams/Meet)
                             o 'top' (subtítulo flotante superior).
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.os_name = platform.system()
        self.device = device
        self.mirror_flip = mirror_flip
        self.subtitle_duration = subtitle_duration
        self.banner_position = banner_position

        self._cam = None
        self._is_active = False
        self._state_lock = threading.Lock()

        # Buffer atómico de cuadros (para desacoplar inferencia de la tasa de refresco)
        self._frame_lock = threading.Lock()
        self._latest_bgr_frame: Optional[np.ndarray] = None
        self._latest_custom_text: Optional[str] = None
        self._worker_thread: Optional[threading.Thread] = None

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
        with self._state_lock:
            return self._is_active and self._cam is not None

    def start(self) -> bool:
        """
        Inicia la cámara virtual y el hilo de transmisión asíncrono.
        Captura cualquier excepción si el driver no está presente o faltan permisos,
        asegurando degradación suave sin crashear.

        Returns:
            bool: True si la cámara se inició con éxito, False en caso contrario.
        """
        with self._state_lock:
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
                logger.info("✓ Cámara Virtual inicializada exitosamente: %s", getattr(self._cam, "device", "Virtual Device"))

                # Iniciar hilo secundario de transmisión continua desacoplada
                self._worker_thread = threading.Thread(
                    target=self._transmission_worker,
                    name="HandTalk-VirtualCamWorker",
                    daemon=True,
                )
                self._worker_thread.start()

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
        """Detiene y libera la cámara virtual y su hilo de transmisión de forma segura."""
        with self._state_lock:
            self._is_active = False

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None

        with self._state_lock:
            if self._cam is not None:
                try:
                    self._cam.close()
                except Exception as e:
                    logger.debug("Error al cerrar cámara virtual: %s", e)
                finally:
                    self._cam = None
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
        self.last_confirmed_word = str(word).strip().upper()
        self.last_confidence = float(confidence)
        self.last_timestamp = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.last_update_time = time.time()
        logger.debug("VirtualCam recibió traducción confirmada: '%s' (%.2f)", self.last_confirmed_word, confidence)

    def draw_subtitle_overlay(self, frame: np.ndarray, text: Optional[str] = None) -> np.ndarray:
        """
        Dibuja un banner con subtítulo de alto contraste, indicador de confirmación y
        desvanecimiento suave (fadeout), posicionado en una zona segura para no colisionar
        con la interfaz de Teams, Meet o Zoom.

        Args:
            frame: Imagen OpenCV en formato BGR.
            text: Texto opcional a dibujar. Si es None, usa `last_confirmed_word`.

        Returns:
            np.ndarray: Frame con el banner dibujado.
        """
        now = time.time()
        if text is None:
            elapsed = now - self.last_update_time
            if self.last_confirmed_word and (elapsed < self.subtitle_duration):
                text = self.last_confirmed_word
                # Cálculo de fade-out en los últimos 0.7 segundos
                remaining = self.subtitle_duration - elapsed
                if remaining < 0.7:
                    box_alpha = max(0.2, 0.75 * (remaining / 0.7))
                else:
                    box_alpha = 0.75
            else:
                text = ""
                box_alpha = 0.0
        else:
            box_alpha = 0.75

        if not text or box_alpha <= 0.05:
            return frame

        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = max(0.85, min(1.35, w / 1100.0))
        thickness = max(2, int(font_scale * 2.1))

        # Badge superior de confirmación (Verde esmeralda brillante)
        badge_text = "CONFIRMADO"
        conf_pct = f"{int(self.last_confidence * 100)}%" if self.last_confidence > 0 else ""
        badge_full = f"✓ {badge_text} ({conf_pct})" if conf_pct else f"✓ {badge_text}"

        badge_scale = font_scale * 0.48
        badge_thick = 1
        (b_w, b_h), _ = cv2.getTextSize(badge_full, cv2.FONT_HERSHEY_SIMPLEX, badge_scale, badge_thick)
        (t_w, t_h), _ = cv2.getTextSize(text, font, font_scale, thickness)

        padding_x = int(24 * (w / 1280.0) + 14)
        padding_y = int(10 * (h / 720.0) + 8)

        content_w = max(b_w, t_w)
        box_w = content_w + (padding_x * 2)
        box_h = b_h + t_h + (padding_y * 2) + 8

        box_x = max(15, (w - box_w) // 2)

        # Ubicación respetando la zona segura de Teams/Meet/Zoom
        if self.banner_position == "top":
            box_y = max(20, int(h * 0.05))
        else:
            # bottom_safe: Margen de seguridad (13% a 15% de la altura).
            # En 720p es ~95 px, situando el banner por encima de la barra de nombres e iconos de Teams/Meet
            safe_margin_bottom = max(85, int(h * 0.13))
            box_y = max(15, h - box_h - safe_margin_bottom)

        # Capa semitransparente oscura para el banner
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (box_x, box_y),
            (box_x + box_w, box_y + box_h),
            (16, 16, 24),
            cv2.FILLED,
        )
        # Borde de acento esmeralda/morado (#6C5CE7 aproximado en BGR)
        cv2.rectangle(
            overlay,
            (box_x, box_y),
            (box_x + box_w, box_y + box_h),
            (231, 92, 108),
            2,
        )

        # Fusión con canal alfa calculado
        cv2.addWeighted(overlay, box_alpha, frame, 1.0 - box_alpha, 0, frame)

        # 1. Dibujar badge superior (verde esmeralda brillante BGR: 0, 230, 115)
        b_x = box_x + padding_x
        b_y = box_y + padding_y + b_h
        cv2.putText(
            frame,
            badge_full,
            (b_x, b_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            badge_scale,
            (0, 230, 115),
            badge_thick,
            cv2.LINE_AA,
        )

        # 2. Dibujar palabra confirmada (blanco de alto contraste con sombra negra)
        t_x = box_x + padding_x
        t_y = b_y + 8 + t_h
        cv2.putText(
            frame,
            text,
            (t_x + 1, t_y + 1),
            font,
            font_scale,
            (0, 0, 0),
            thickness + 1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            text,
            (t_x, t_y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

        return frame

    def _fit_frame_to_target(self, frame: np.ndarray) -> np.ndarray:
        """
        Ajusta el cuadro a la resolución estándar 16:9 (1280x720) mediante
        recorte central inteligente, evitando que la imagen se estire o distorsione
        si la cámara física entrega una relación de aspecto distinta (ej. 4:3).
        """
        h, w = frame.shape[:2]
        if w == self.width and h == self.height:
            return frame

        target_aspect = self.width / float(self.height)
        current_aspect = w / float(h)

        if abs(current_aspect - target_aspect) < 0.03:
            return cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

        # Si el frame es más angosto que 16:9 (ej. 4:3 640x480)
        if current_aspect < target_aspect:
            desired_h = int(w / target_aspect)
            offset_y = max(0, (h - desired_h) // 2)
            cropped = frame[offset_y:offset_y + desired_h, 0:w]
            return cv2.resize(cropped, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        else:
            # Si el frame es más ancho que 16:9
            desired_w = int(h * target_aspect)
            offset_x = max(0, (w - desired_w) // 2)
            cropped = frame[0:h, offset_x:offset_x + desired_w]
            return cv2.resize(cropped, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    def send_frame(self, frame_bgr: np.ndarray, overlay_text: Optional[str] = None) -> bool:
        """
        Recibe un cuadro OpenCV en formato BGR y lo deposita en el buffer de salida.
        Esta llamada es no bloqueante (<0.1ms), permitiendo que el hilo de IA / MediaPipe
        continúe a máxima velocidad sin esperar la tasa de refresco de la cámara virtual.

        Args:
            frame_bgr: Matriz numpy con la imagen en BGR.
            overlay_text: Texto opcional específico para este frame.

        Returns:
            bool: True si la cámara está activa y el cuadro fue encolado, False si está inactiva.
        """
        if not self.is_active:
            return False

        with self._frame_lock:
            self._latest_bgr_frame = frame_bgr.copy()
            self._latest_custom_text = overlay_text

        return True

    def _transmission_worker(self) -> None:
        """
        Bucle interno en segundo plano que consume el último cuadro disponible,
        aplica transformaciones de escala, efecto espejo, overlay y color, y transmite
        al driver pyvirtualcam a la tasa de refresco exacta configurada (ej. 30 FPS).
        """
        logger.info("Hilo de transmisión VirtualCam iniciado.")
        last_sent_frame = None

        while True:
            with self._state_lock:
                if not self._is_active or self._cam is None:
                    break

            # 1. Obtener copia del último frame recibido
            with self._frame_lock:
                frame_bgr = self._latest_bgr_frame
                custom_text = self._latest_custom_text

            if frame_bgr is not None:
                try:
                    # 2. Compensar espejo si está activo antes de subtitular
                    if self.mirror_flip:
                        working_frame = cv2.flip(frame_bgr, 1)
                    else:
                        working_frame = frame_bgr.copy()

                    # 3. Estandarizar a resolución objetivo (1280x720 16:9) sin distorsión
                    working_frame = self._fit_frame_to_target(working_frame)

                    # 4. Dibujar banner de subtítulos y confirmación en zona segura
                    working_frame = self.draw_subtitle_overlay(working_frame, custom_text)

                    # 5. Conversión de color obligatoria: OpenCV BGR -> pyvirtualcam RGB
                    frame_rgb = cv2.cvtColor(working_frame, cv2.COLOR_BGR2RGB)
                    last_sent_frame = frame_rgb

                    # 6. Envío al driver y sincronización de frame rate
                    self._cam.send(frame_rgb)
                    self._cam.sleep_until_next_frame()

                except Exception as e:
                    logger.debug("Aviso de transmisión en VirtualCam worker: %s", e)
                    time.sleep(0.01)
            elif last_sent_frame is not None:
                # Si la IA aún no envía un nuevo cuadro, mantener la señal transmitiendo el anterior
                try:
                    self._cam.send(last_sent_frame)
                    self._cam.sleep_until_next_frame()
                except Exception:
                    time.sleep(0.02)
            else:
                # En espera del primer cuadro
                time.sleep(0.02)

        logger.info("Hilo de transmisión VirtualCam finalizado.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def main():
    """Prueba rápida de funcionamiento y tolerancia a fallos del módulo."""
    print("=" * 60)
    print("HandTalk - Comprobación de Cámara Virtual Desacoplada (Punto 4.2)")
    print("=" * 60)
    print(f"Sistema Operativo detectado: {platform.system()} ({platform.release()})")

    manager = VirtualCamManager(width=1280, height=720, fps=30)
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
            # Generar fondo degradado de prueba (1280x720 16:9)
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
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
            if i % 25 == 0:
                idx_palabra = (i // 25) % len(palabras_demo)
                manager.on_translation_confirmed(palabras_demo[idx_palabra], 0.95)

            manager.send_frame(frame)
            time.sleep(0.03)

        print("[OK] Transmisión de prueba completada exitosamente.")
    finally:
        manager.stop()
        print("=" * 60)


if __name__ == "__main__":
    main()
