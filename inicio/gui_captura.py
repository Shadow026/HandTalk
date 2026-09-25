#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui_captura.py

Implementación de la interfaz de captura de señas personalizadas.
Cierra la brecha de la Tarea 1 de Francisco: conecta la captura
de datos con la normalización de hand_features.py.

Flujo:
Cámara -> MediaPipe -> hand_features.build_feature_vector() -> dataset_manager.save_sample()
"""

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import mediapipe as mp
import threading
import os
import time
import numpy as np

import camera_utils
import hand_features
import dataset_manager

class CaptureGUI:
    def __init__(self, root, parent_frame=None, camera_id=None):
        self.root = root
        self.parent_frame = parent_frame or root
        self.is_standalone = (parent_frame is None)
        if self.is_standalone:
            self.root.title("Captura de Señas Personalizadas")
            self.root.geometry("1100x700")
            self.root.configure(bg="#F0F2F5")

        # Estado de la aplicación
        self.is_capturing = False
        self.current_word = ""
        self.sample_count = 0
        self.cap = None
        self.camera_id = camera_id

        # Trigger Autónomo
        self.trigger_active = False
        self.trigger_frames = 0
        self.TRIGGER_THRESHOLD = 15 # Frames de puño cerrado para activar
        self.is_counting_down = False
        self.countdown_value = 3

        # Modo de captura: "static" o "dynamic"
        self.capture_mode = tk.StringVar(value="static")

        # MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils

        self.setup_ui()

    def cleanup(self):
        """Detiene la cámara y limpia recursos para permitir que otra pestaña use la cámara."""
        if self.is_capturing or self.cap is not None:
            self.is_capturing = False
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            if hasattr(self, 'btn_camera'):
                self.btn_camera.config(text="Abrir Cámara")
            if hasattr(self, 'btn_capture'):
                self.btn_capture.config(state=tk.DISABLED)
            if hasattr(self, 'video_label'):
                self.video_label.config(image='', text="La cámara estará aquí")

    def setup_ui(self):
        # Panel Lateral (Controles)
        self.side_panel = tk.Frame(self.parent_frame, bg="#FFFFFF", width=300, padx=20, pady=20)
        self.side_panel.pack(side=tk.LEFT, fill=tk.Y)
        self.side_panel.pack_propagate(False)

        tk.Label(self.side_panel, text="Configuración de Captura", font=("Segoe UI", 14, "bold"),
                 bg="#FFFFFF", fg="#2D3436").pack(pady=(0, 20))

        # --- selector de modo: Estática vs Dinámica ---
        mode_frame = tk.Frame(self.side_panel, bg="#FFFFFF")
        mode_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(mode_frame, text="Modo de Captura:", bg="#FFFFFF", fg="#636E72", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        mode_options = tk.Frame(mode_frame, bg="#FFFFFF")
        mode_options.pack(fill=tk.X)

        tk.Radiobutton(mode_options, text="Estática", variable=self.capture_mode,
                      value="static", bg="#FFFFFF", activebackground="#FFFFFF").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(mode_options, text="Dinámica", variable=self.capture_mode,
                      value="dynamic", bg="#FFFFFF", activebackground="#FFFFFF").pack(side=tk.LEFT, padx=5)

        # Entrada de Palabra
        tk.Label(self.side_panel, text="Palabra/Seña:", bg="#FFFFFF", fg="#636E72").pack(anchor=tk.W)
        self.word_entry = ttk.Entry(self.side_panel, font=("Segoe UI", 12))
        self.word_entry.pack(fill=tk.X, pady=(5, 15))

        # Botón Iniciar Cámara
        self.btn_camera = ttk.Button(self.side_panel, text="Abrir Cámara", command=self.toggle_camera)
        self.btn_camera.pack(fill=tk.X, pady=5)

        # Botón Capturar Muestra
        self.btn_capture = ttk.Button(self.side_panel, text="Guardar Muestra (S)", command=self.save_current_sample, state=tk.DISABLED)
        self.btn_capture.pack(fill=tk.X, pady=5)

        # Botón Temporizador
        self.btn_timer = ttk.Button(self.side_panel, text="Temporizador (5s)", command=self.start_timer_capture, state=tk.DISABLED)
        self.btn_timer.pack(fill=tk.X, pady=5)

        # Contador de Muestras
        self.lbl_count = tk.Label(self.side_panel, text="Muestras: 0", font=("Segoe UI", 12, "bold"),
                                 bg="#FFFFFF", fg="#4834D4")
        self.lbl_count.pack(pady=20)

        # Lista de Palabras Existentes
        tk.Label(self.side_panel, text="Palabras en Dataset:", bg="#FFFFFF", fg="#636E72").pack(anchor=tk.W)
        self.words_list = tk.Listbox(self.side_panel, font=("Segoe UI", 10), height=15)
        self.words_list.pack(fill=tk.BOTH, expand=True, pady=5)

        self.update_words_list()

        # Panel Principal (Video)
        self.main_panel = tk.Frame(self.parent_frame, bg="#F0F2F5")
        self.main_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.video_label = tk.Label(self.main_panel, text="La cámara estará aquí",
                                   bg="#D1D8E0", fg="#778CA3", font=("Segoe UI", 14))
        self.video_label.pack(fill=tk.BOTH, expand=True)

    def show_capture_progress(self, show: bool):
        if show:
            self.progress_lbl = tk.Label(self.side_panel, text="Capturando secuencia...",
                                        bg="#FFFFFF", fg="#4834D4",
                                        font=("Segoe UI", 10, "bold"))
            self.progress_lbl.pack(pady=5)
        elif hasattr(self, 'progress_lbl'):
            self.progress_lbl.destroy()

    def _finalize_capture_success(self):
        self.sample_count += 1
        self.lbl_count.config(text=f"Muestras: {self.sample_count}")
        self.update_words_list()

    def _finalize_capture_error(self, error_msg):
        messagebox.showerror("Error Dinámico", f"Error capturando secuencia: {error_msg}")

    def update_words_list(self):
        self.words_list.delete(0, tk.END)
        for word in dataset_manager.get_existing_words():
            count = dataset_manager.count_samples_for_word(word)
            self.words_list.insert(tk.END, f"{word} ({count})")

    def toggle_camera(self):
        if self.cap is None:
            self.cap, self.camera_id = camera_utils.open_camera(self.camera_id)
            if self.cap is None:
                messagebox.showerror("Error", "No se pudo abrir la cámara.")
                return

            self.btn_camera.config(text="Cerrar Cámara")
            self.btn_capture.config(state=tk.NORMAL)
            self.btn_timer.config(state=tk.NORMAL)
            self.is_capturing = True

            self.frame_actual = None
            self.frame_lock = threading.Lock()
            self.thread = threading.Thread(target=self.capture_loop, daemon=True)
            self.thread.start()

            self.update_video()
        else:
            self.is_capturing = False
            self.cap.release()
            self.cap = None
            self.btn_camera.config(text="Abrir Cámara")
            self.btn_capture.config(state=tk.DISABLED)
            self.btn_timer.config(state=tk.DISABLED)
            self.video_label.config(image='', text="La cámara estará aquí")

    def capture_loop(self):
        while self.is_capturing:
            ret, frame = self.cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)

            if results.multi_hand_landmarks:
                # --- LÓGICA DE TRIGGER AUTÓNOMO (Puño Cerrado) ---
                if not self.is_counting_down:
                    self._check_trigger_gesture(results)

                for hand_landmarks in results.multi_hand_landmarks:
                    self.mp_draw.draw_landmarks(
                        frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                    )

            with self.frame_lock:
                self.frame_actual = frame

        self.cap and self.cap.release()

    def _check_trigger_gesture(self, results):
        """Detecta si el usuario cierra el puño para iniciar la captura."""
        if not results.multi_hand_landmarks:
            self.trigger_frames = 0
            return

        # Analizamos la primera mano detectada
        landmarks = results.multi_hand_landmarks[0]

        # Definimos 'puño cerrado' como: puntas de los dedos cerca de la muñeca
        # Distancia normalizada entre punta del dedo medio (12) y muñeca (0)
        wrist = landmarks.landmark[0]
        tips = [landmarks.landmark[8], landmarks.landmark[12], landmarks.landmark[16], landmarks.landmark[20]]

        is_closed = True
        for tip in tips:
            dist = np.sqrt((tip.x - wrist.x)**2 + (tip.y - wrist.y)**2)
            if dist > 0.15: # Umbral de puño cerrado
                is_closed = False
                break

        if is_closed:
            self.trigger_frames += 1
            if self.trigger_frames >= self.TRIGGER_THRESHOLD:
                self.trigger_active = True
                self.is_counting_down = True
                self.root.after(0, self.start_autonomous_countdown)
        else:
            self.trigger_frames = 0

    def start_autonomous_countdown(self):
        """Cuenta regresiva visual antes de guardar la muestra."""
        self.countdown_value = 3
        def count():
            if self.countdown_value > 0:
                print(f"Capturando en: {self.countdown_value}...")
                self.countdown_value -= 1
                self.root.after(1000, count)
            else:
                print("¡CAPTURANDO AHORA!")
                self.save_current_sample()
                self.is_counting_down = False
                self.trigger_frames = 0
        count()

    def start_timer_capture(self):
        """Inicia una cuenta regresiva de 5 segundos antes de capturar."""
        self.is_counting_down = True
        self.countdown_value = 5

        def count():
            if self.countdown_value > 0:
                print(f"Temporizador: {self.countdown_value} segundos para capturar...")
                self.countdown_value -= 1
                self.root.after(1000, count)
            else:
                print("¡TIEMPO AGOTADO - CAPTURANDO!")
                self.save_current_sample()
                self.is_counting_down = False

        count()

    def update_video(self):
        if not self.is_capturing:
            return

        with self.frame_lock:
            frame = self.frame_actual.copy() if self.frame_actual is not None else None

        if frame is not None:
            from PIL import Image, ImageTk
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk, text="")

        self.root.after(15, self.update_video)

    def save_current_sample(self):
        word = self.word_entry.get().strip()
        if not word:
            messagebox.showwarning("Atención", "Por favor ingresa una palabra para la seña.")
            return

        mode = self.capture_mode.get()

        if mode == "static":
            ret, frame = self.cap.read()
            if not ret:
                messagebox.showerror("Error", "No se pudo capturar la imagen.")
                return

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)

            if not results.multi_hand_landmarks:
                messagebox.showwarning("Atención", "No se detectó ninguna mano. Intenta de nuevo.")
                return

            try:
                # SOPORTE PARA DOS MANOS (ESTÁTICAS)
                if len(results.multi_hand_landmarks) == 2:
                    feature_vector = hand_features.build_two_hand_feature_vector(
                        results.multi_hand_landmarks,
                        multi_handedness=results.multi_handedness
                    )
                else:
                    landmarks = results.multi_hand_landmarks[0]
                    feature_vector = hand_features.build_feature_vector(landmarks)

                dataset_manager.save_sample(feature_vector, word, sample_type="static")

                self.sample_count += 1
                self.lbl_count.config(text=f"Muestras: {self.sample_count}")
                self.update_words_list()
            except Exception as e:
                messagebox.showerror("Error Crítico", f"Error al procesar landmarks: {str(e)}")

        else:
            def capture_worker():
                sequence = []
                num_frames = 20
                self.root.after(0, lambda: self.show_capture_progress(True))

                try:
                    for i in range(num_frames):
                        ret, frame = self.cap.read()
                        if not ret: break

                        frame = cv2.flip(frame, 1)
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        results = self.hands.process(rgb_frame)

                        if results.multi_hand_landmarks:
                            # SOPORTE PARA DOS MANOS (DINÁMICAS)
                            if len(results.multi_hand_landmarks) == 2:
                                features = hand_features.build_two_hand_feature_vector(
                                    results.multi_hand_landmarks,
                                    multi_handedness=results.multi_handedness
                                )
                            else:
                                landmarks = results.multi_hand_landmarks[0]
                                features = hand_features.build_feature_vector(landmarks)
                            sequence.append(features)
                        else:
                            if len(sequence) > 0:
                                sequence.append(sequence[-1])
                            else:
                                raise RuntimeError("No se detectó la mano al inicio de la secuencia.")

                        time.sleep(0.03)

                    if len(sequence) < num_frames:
                        raise RuntimeError("La secuencia fue interrumpida.")

                    dataset_manager.save_sample(sequence, word, sample_type="dynamic")
                    self.root.after(0, self._finalize_capture_success)

                except Exception as e:
                    self.root.after(0, lambda: self._finalize_capture_error(str(e)))
                finally:
                    self.root.after(0, lambda: self.show_capture_progress(False))

            threading.Thread(target=capture_worker, daemon=True).start()

    def run(self):
        self.root.bind('s', lambda event: self.save_current_sample())
        self.root.bind('S', lambda event: self.save_current_sample())
        self.root.mainloop()

if __name__ == "__main__":
    root = tk.Tk()
    app = CaptureGUI(root)
    app.run()
