#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui_captura.py

Implementación de la interfaz de captura de señas personalizadas.
Cierra la brecha de la Tarea 1 de Francisco: conecta la captura
de datos con la normalización de hand_features.py.

NUEVO:
  - Selector Estática / Dinámica: la misma interfaz sirve para capturar
    ambos tipos de seña, sin necesidad de un script aparte. Internamente
    sigue guardando con dataset_manager.save_sample(..., sample_type=...)
    tal como ya estaba diseñado.
  - La captura dinámica (una secuencia de frames) ocurre DENTRO del hilo
    que ya lee la cámara (capture_loop), para no bloquear la interfaz
    mientras se graban los ~20 frames de la ventana.
  - save_current_sample ya NO vuelve a llamar self.cap.read(): reutiliza
    el último frame que el hilo de captura ya procesó, evitando que dos
    hilos lean la misma cámara al mismo tiempo (condición de carrera que
    tenía la versión anterior).

Flujo:
Cámara -> MediaPipe -> hand_features.build_feature_vector() -> dataset_manager.save_sample()
"""

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import mediapipe as mp
import threading
import queue

import camera_utils
import hand_features
import dataset_manager

VENTANA_DINAMICA_DEFAULT = 20


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

        # --- Estado compartido entre el hilo de cámara y el hilo principal ---
        self.frame_lock = threading.Lock()
        self.frame_actual = None
        self.ultimo_feature_vector = None  # se actualiza cada frame si hay mano detectada

        # --- Estado de captura DINÁMICA (secuencia de frames) ---
        self.tipo_seleccionado = tk.StringVar(value="static")
        self.capturando_dinamica = False
        self.buffer_dinamico = []
        self.ventana_dinamica_var = tk.StringVar(value=str(VENTANA_DINAMICA_DEFAULT))

        # Cola para que el hilo de cámara le avise al hilo principal (Tkinter)
        # cuando termina de guardar una muestra o hay progreso que mostrar,
        # sin llamar directamente a widgets desde otro hilo.
        self.eventos_ui = queue.Queue()

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

        # --- NUEVO: Selector de tipo de seña ---
        tk.Label(self.side_panel, text="Tipo de seña:", bg="#FFFFFF", fg="#636E72").pack(anchor=tk.W)
        frame_tipo = tk.Frame(self.side_panel, bg="#FFFFFF")
        frame_tipo.pack(fill=tk.X, pady=(5, 5))
        ttk.Radiobutton(frame_tipo, text="Estática", variable=self.tipo_seleccionado,
                        value="static", command=self._on_tipo_cambiado).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Radiobutton(frame_tipo, text="Dinámica", variable=self.tipo_seleccionado,
                        value="dynamic", command=self._on_tipo_cambiado).pack(side=tk.LEFT)

        # Cantidad de frames para dinámica (solo relevante en ese modo)
        self.frame_ventana = tk.Frame(self.side_panel, bg="#FFFFFF")
        self.frame_ventana.pack(fill=tk.X, pady=(5, 15))
        tk.Label(self.frame_ventana, text="Frames por secuencia:", bg="#FFFFFF",
                 fg="#636E72", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.entry_ventana = ttk.Entry(self.frame_ventana, textvariable=self.ventana_dinamica_var, width=5)
        self.entry_ventana.pack(side=tk.LEFT, padx=(5, 0))
        self._on_tipo_cambiado()  # oculta/muestra según el valor inicial

        # Botón Iniciar Cámara
        self.btn_camera = ttk.Button(self.side_panel, text="Abrir Cámara", command=self.toggle_camera)
        self.btn_camera.pack(fill=tk.X, pady=5)

        # Botón Capturar Muestra
        self.btn_capture = ttk.Button(self.side_panel, text="Guardar Muestra (S)",
                                       command=self.save_current_sample, state=tk.DISABLED)
        self.btn_capture.pack(fill=tk.X, pady=5)

        # Estado de grabación (progreso de la secuencia dinámica)
        self.lbl_estado_captura = tk.Label(self.side_panel, text="", font=("Segoe UI", 10),
                                            bg="#FFFFFF", fg="#E74C3C")
        self.lbl_estado_captura.pack(pady=(0, 10))

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

    def _on_tipo_cambiado(self):
        """Muestra el campo de 'frames por secuencia' solo en modo dinámico."""
        if self.tipo_seleccionado.get() == "dynamic":
            self.frame_ventana.pack(fill=tk.X, pady=(5, 15))
        else:
            self.frame_ventana.pack_forget()

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

            # El hilo secundario captura, procesa Y maneja la grabación
            # de secuencias dinámicas (nada de Tkinter dentro de este hilo).
            self.thread = threading.Thread(target=self.capture_loop, daemon=True)
            self.thread.start()

            # El hilo principal (Tkinter) es quien actualiza el Label y la UI
            self.update_video()
        else:
            self.is_capturing = False
            self.capturando_dinamica = False
            self.cap.release()
            self.cap = None
            self.btn_camera.config(text="Abrir Cámara")
            self.btn_capture.config(state=tk.DISABLED)
            self.video_label.config(image='', text="La cámara estará aquí")

    def capture_loop(self):
        """
        Corre en un hilo aparte: captura, procesa Y graba secuencias
        dinámicas cuando corresponde. Nunca toca widgets de Tkinter
        directamente -- para eso usa self.eventos_ui (thread-safe).
        """
        while self.is_capturing:
            ret, frame = self.cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)

            feature_vector = None
            if results.multi_hand_landmarks:
                landmarks = results.multi_hand_landmarks[0]
                self.mp_draw.draw_landmarks(frame, landmarks, self.mp_hands.HAND_CONNECTIONS)
                feature_vector = hand_features.build_feature_vector(landmarks)

            with self.frame_lock:
                self.frame_actual = frame
                self.ultimo_feature_vector = feature_vector

            # --- Grabación activa de una secuencia dinámica ---
            if self.capturando_dinamica:
                if feature_vector is not None:
                    self.buffer_dinamico.append(feature_vector)
                elif self.buffer_dinamico:
                    # Sin mano en este frame: repetir el último vector
                    # conocido para no perder toda la secuencia por un
                    # frame fallido puntual.
                    self.buffer_dinamico.append(self.buffer_dinamico[-1])

                objetivo = self._ventana_objetivo_segura()
                self.eventos_ui.put(("progreso", len(self.buffer_dinamico), objetivo))

                if len(self.buffer_dinamico) >= objetivo:
                    dataset_manager.save_sample(
                        self.buffer_dinamico, self.current_word, sample_type="dynamic"
                    )
                    self.eventos_ui.put(("guardado", self.current_word, "dynamic"))
                    self.capturando_dinamica = False
                    self.buffer_dinamico = []

        self.cap and self.cap.release()

    def _ventana_objetivo_segura(self):
        """Lee el tamaño de ventana configurado en la UI, con respaldo si el campo está vacío/inválido."""
        try:
            valor = int(self.ventana_dinamica_var.get())
            return max(5, valor)
        except (ValueError, tk.TclError):
            return VENTANA_DINAMICA_DEFAULT

    def update_video(self):
        """Corre en el hilo principal (Tkinter) vía root.after(). Aquí sí se
        puede tocar el widget de forma segura."""
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

        # Procesa cualquier evento que el hilo de cámara haya dejado en la cola
        self._procesar_eventos_ui()

        self.root.after(15, self.update_video)

    def _procesar_eventos_ui(self):
        """Drena la cola de eventos del hilo de cámara y actualiza la UI
        (esto SÍ corre en el hilo principal, por eso es seguro tocar widgets)."""
        while True:
            try:
                evento = self.eventos_ui.get_nowait()
            except queue.Empty:
                break

            tipo_evento = evento[0]
            if tipo_evento == "progreso":
                _, actual, objetivo = evento
                self.lbl_estado_captura.config(text=f"Grabando: {actual}/{objetivo}")
            elif tipo_evento == "guardado":
                _, palabra, sample_type = evento
                self.sample_count += 1
                self.lbl_estado_captura.config(text="✓ Secuencia guardada")
                self.lbl_count.config(text=f"Muestras: {self.sample_count}")
                self.update_words_list()

    def save_current_sample(self):
        word = self.word_entry.get().strip()
        if not word:
            messagebox.showwarning("Atención", "Por favor ingresa una palabra para la seña.")
            return

        if self.cap is None:
            messagebox.showwarning("Atención", "Primero abre la cámara.")
            return

        self.current_word = word
        tipo = self.tipo_seleccionado.get()

        if tipo == "dynamic":
            if self.capturando_dinamica:
                messagebox.showinfo("En progreso", "Ya se está grabando una secuencia, espera a que termine.")
                return
            # Solo activa la bandera: capture_loop (en su propio hilo) se
            # encarga de acumular los frames y guardar al completar la ventana.
            self.buffer_dinamico = []
            self.capturando_dinamica = True
            self.lbl_estado_captura.config(text="Preparando grabación...")
            return

        # --- Modo estático: reutiliza el último frame ya procesado por
        # capture_loop, en vez de volver a leer la cámara (evita condición
        # de carrera con el hilo que ya la está leyendo constantemente). ---
        with self.frame_lock:
            feature_vector = self.ultimo_feature_vector

        if feature_vector is None:
            messagebox.showwarning("Atención", "No se detectó ninguna mano. Intenta de nuevo.")
            return

        try:
            dataset_manager.save_sample(feature_vector, word, sample_type="static")
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