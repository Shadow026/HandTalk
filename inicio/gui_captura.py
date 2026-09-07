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

import camera_utils
import hand_features
import dataset_manager

class CaptureGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Captura de Señas Personalizadas")
        self.root.geometry("1100x700")
        self.root.configure(bg="#F0F2F5")

        # Estado de la aplicación
        self.is_capturing = False
        self.current_word = ""
        self.sample_count = 0
        self.cap = None
        self.camera_id = None

        # MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils

        self.setup_ui()

    def setup_ui(self):
        # Panel Lateral (Controles)
        self.side_panel = tk.Frame(self.root, bg="#FFFFFF", width=300, padx=20, pady=20)
        self.side_panel.pack(side=tk.LEFT, fill=tk.Y)
        self.side_panel.pack_propagate(False)

        tk.Label(self.side_panel, text="Configuración de Captura", font=("Segoe UI", 14, "bold"),
                 bg="#FFFFFF", fg="#2D3436").pack(pady=(0, 20))

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
        self.main_panel = tk.Frame(self.root, bg="#F0F2F5")
        self.main_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.video_label = tk.Label(self.main_panel, text="La cámara estará aquí",
                                   bg="#D1D8E0", fg="#778CA3", font=("Segoe UI", 14))
        self.video_label.pack(fill=tk.BOTH, expand=True)

    def update_words_list(self):
        self.words_list.delete(0, tk.END)
        for word in dataset_manager.get_existing_words():
            count = dataset_manager.count_samples_for_word(word)
            self.words_list.insert(tk.END, f"{word} ({count})")

    def toggle_camera(self):
        if self.cap is None:
            self.cap, self.camera_id = camera_utils.open_camera()
            if self.cap is None:
                messagebox.showerror("Error", "No se pudo abrir la cámara.")
                return

            self.btn_camera.config(text="Cerrar Cámara")
            self.btn_capture.config(state=tk.NORMAL)
            self.is_capturing = True

            # Iniciar hilo de lectura de video
            self.thread = threading.Thread(target=self.video_loop, daemon=True)
            self.thread.start()
        else:
            self.is_capturing = False
            self.cap.release()
            self.cap = None
            self.btn_camera.config(text="Abrir Cámara")
            self.btn_capture.config(state=tk.DISABLED)
            self.video_label.config(image='', text="La cámara estará aquí")

    def video_loop(self):
        while self.is_capturing:
            ret, frame = self.cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)

            # Dibujar landmarks para feedback visual
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    self.mp_draw.draw_landmarks(
                        frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                    )

            # Convertir OpenCV frame a formato compatible con Tkinter
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            from PIL import Image, ImageTk
            img = Image.fromarray(img)
            imgtk = ImageTk.PhotoImage(image=img)

            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk, text="")

        cv2.destroyAllWindows()

    def save_current_sample(self):
        word = self.word_entry.get().strip()
        if not word:
            messagebox.showwarning("Atención", "Por favor ingresa una palabra para la seña.")
            return

        # Capturar frame actual
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

        # --- TAREA 1: CONEXIÓN CON hand_features.py ---
        # Usamos la función build_feature_vector para obtener la normalización canónica
        try:
            landmarks = results.multi_hand_landmarks[0]
            feature_vector = hand_features.build_feature_vector(landmarks)

            # Guardar usando dataset_manager
            dataset_manager.save_sample(feature_vector, word)

            self.sample_count += 1
            self.lbl_count.config(text=f"Muestras: {self.sample_count}")
            self.update_words_list()
        except Exception as e:
            messagebox.showerror("Error Crítico", f"Error al procesar landmarks: {str(e)}")

    def run(self):
        # Bind tecla 'S' para capturar rápidamente
        self.root.bind('s', lambda event: self.save_current_sample())
        self.root.bind('S', lambda event: self.save_current_sample())
        self.root.mainloop()

if __name__ == "__main__":
    root = tk.Tk()
    app = CaptureGUI(root)
    app.run()
