#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts_output.py

Salida de VOZ (TTS) para el traductor de señas. Es un "Módulo de Salida" en
los términos de EVENTOS.md: no conoce nada del motor de traducción, solo
implementa la firma acordada y se suscribe con register_callback():

    from tts_output import TTSOutput

    tts = TTSOutput()                       # pyttsx3 offline por defecto
    translator.register_callback(tts.on_translation_confirmed)
    ...
    tts.disable()   # / tts.enable() / tts.toggle()   -> activar/desactivar
    ...
    tts.stop()       # al cerrar la app, para apagar el hilo de fondo

Motor por defecto: pyttsx3 (offline, no requiere internet).
Motor alternativo: edge-tts (mejor calidad de voz, requiere internet),
seleccionable con engine="edge-tts".

Diseño:
- El habla ocurre en un HILO DE FONDO con una cola (queue.Queue). Así,
  aunque pyttsx3.runAndWait() bloquee mientras dice la palabra, el bucle de
  video de realtime_translator.py (cv2.imshow / cap.read) NUNCA se congela
  esperando al audio.
- "repeat_cooldown": el PredictionSmoother puede re-confirmar la MISMA
  palabra cada ~500ms mientras el usuario mantiene la seña quieta (ver
  smoothing.py: detection_delay_ms=500). Sin este cooldown, el TTS diría la
  palabra en bucle sin parar. Por defecto se ignoran repeticiones de la
  misma palabra durante 2.5s.
"""

import queue
import threading
import time


class TTSOutput:
    def __init__(self, enabled=True, engine="pyttsx3", voice=None, rate=175,
                 repeat_cooldown=2.5, edge_voice="es-MX-DaliaNeural"):
        """
        enabled: si es False, el suscriptor queda registrado pero no habla
                 (se puede activar en caliente con enable()/toggle()).
        engine: "pyttsx3" (offline, por defecto) o "edge-tts" (online).
        voice: id de voz para pyttsx3 (None = voz por defecto del sistema).
               Usa `python -c "import pyttsx3; [print(v.id) for v in pyttsx3.init().getProperty('voices')]"`
               para listar las voces disponibles en tu máquina.
        rate: palabras por minuto aproximadas (solo pyttsx3).
        repeat_cooldown: segundos mínimos antes de volver a decir la MISMA
                palabra en voz alta (ver nota de diseño arriba).
        edge_voice: voz de Azure/edge-tts a usar si engine == "edge-tts".
                Ejemplos: "es-MX-DaliaNeural", "es-ES-AlvaroNeural".
        """
        if engine not in ("pyttsx3", "edge-tts"):
            raise ValueError("engine debe ser 'pyttsx3' o 'edge-tts'")

        self.enabled = enabled
        self.engine_name = engine
        self.voice = voice
        self.rate = rate
        self.repeat_cooldown = repeat_cooldown
        self.edge_voice = edge_voice

        self._last_word = None
        self._last_spoken_time = 0.0

        self._queue = queue.Queue()
        self._stop_event = threading.Event()

        if self.engine_name == "pyttsx3":
            self._init_pyttsx3()

        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # Configuración del motor
    # ------------------------------------------------------------------
    def _init_pyttsx3(self):
        try:
            import pyttsx3
        except ImportError as exc:
            raise ImportError(
                "Falta pyttsx3. Instalalo con: pip install pyttsx3"
            ) from exc

        # OJO: aqui solo VALIDAMOS que el driver de TTS del sistema
        # arranca bien (falla rapido con un error claro si no).
        # NO guardamos este engine para hablar con el mas adelante:
        # en Windows (driver sapi5, via COM/win32com) y en macOS (driver
        # nsss) reutilizar el MISMO objeto engine para varias rondas de
        # say()+runAndWait() es un bug conocido de pyttsx3 -- habla la
        # primera vez y despues se queda "mudo" en silencio, sin lanzar
        # ninguna excepcion. Por eso _speak_pyttsx3() crea un engine
        # nuevo en cada palabra (ver mas abajo).
        try:
            probe = pyttsx3.init()
            probe.stop()
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo inicializar el motor de voz del sistema (pyttsx3): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Activar / desactivar en caliente (entregable de la Tarea 3)
    # ------------------------------------------------------------------
    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled

    # ------------------------------------------------------------------
    # Suscriptor: firma exacta de EVENTOS.md
    # ------------------------------------------------------------------
    def on_translation_confirmed(self, word, confidence, timestamp):
        """
        Callback a registrar con translator.register_callback(...).
        No bloquea: solo valida el cooldown y encola la palabra; quien
        realmente reproduce el audio es _run_worker() en su propio hilo.
        """
        if not self.enabled:
            return

        now = time.time()
        if word == self._last_word and (now - self._last_spoken_time) < self.repeat_cooldown:
            return  # misma palabra sostenida: no repetir en bucle

        self._last_word = word
        self._last_spoken_time = now
        self._queue.put(word)

    # ------------------------------------------------------------------
    # Hilo de fondo
    # ------------------------------------------------------------------
    def _run_worker(self):
        while not self._stop_event.is_set():
            try:
                word = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                if self.engine_name == "pyttsx3":
                    self._speak_pyttsx3(word)
                else:
                    self._speak_edge_tts(word)
            except Exception as exc:
                print(f"[WARN] Error al reproducir TTS para '{word}': {exc}")

    def _speak_pyttsx3(self, word):
        # Motor nuevo por cada palabra (ver nota en _init_pyttsx3): esto
        # tiene un pequeño costo (~100-300ms de arranque) pero es la
        # forma confiable de que pyttsx3 hable mas de una vez.
        import pyttsx3

        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", self.rate)
            if self.voice:
                engine.setProperty("voice", self.voice)
            engine.say(word)
            engine.runAndWait()
        finally:
            engine.stop()

    def _speak_edge_tts(self, word):
        try:
            import asyncio
            import os
            import tempfile
            import edge_tts
        except ImportError as exc:
            raise ImportError(
                "Para usar engine='edge-tts' instala: pip install edge-tts playsound"
            ) from exc

        async def _generate(path):
            communicate = edge_tts.Communicate(word, self.edge_voice)
            await communicate.save(path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asyncio.run(_generate(tmp_path))
            try:
                from playsound import playsound
                playsound(tmp_path)
            except ImportError as exc:
                raise ImportError(
                    "Para reproducir audio de edge-tts instala: pip install playsound"
                ) from exc
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    def stop(self):
        """Detiene el hilo de fondo (llamar al cerrar la aplicación)."""
        self._stop_event.set()
        self._worker.join(timeout=1.0)
