#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
menu_universal.py
Menú Universal de HandTalk — Centro de Control Unificado

Unifica en una sola aplicación moderna:
- Pestaña 1: Inicio / Bienvenida, diagnóstico del sistema y guía de 3 pasos.
- Pestaña 2: Captura de señas personalizadas (embebida directamente).
- Pestaña 3: Gestión de vocabulario y entrenamiento asíncrono del modelo IA.
- Pestaña 4: Traducción en tiempo real unificada con el Visor Web (FastAPI/QR/PIN)
             y salidas desacopladas (TTS y Cámara Virtual).

Responsable de Integración: Francisco (Arquitecto) y equipo HandTalk.
"""

import asyncio
import io
import json
import logging
import os
import queue
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageTk

# Ajustar rutas de módulos
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Módulos del proyecto
import camera_utils
import dataset_manager
import hand_features
import qr_generator
import realtime_translator
import smoothing
import train_classifier
import web_server
from gui_captura import CaptureGUI

logger = logging.getLogger("HandTalk.MenuUniversal")


class UniversalMenuApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HandTalk — Traductor de Señas Universal")
        self.root.geometry("1120x720")
        self.root.minsize(1000, 680)

        # Paleta de colores profesional y moderna
        self.c_bg = "#F4F6F9"           # Fondo principal claro
        self.c_sidebar = "#1E1E2E"      # Barra lateral oscura moderna
        self.c_sidebar_hover = "#2E3047"
        self.c_sidebar_active = "#4834D4"
        self.c_card_bg = "#FFFFFF"      # Tarjetas blancas
        self.c_text_primary = "#2D3436"
        self.c_text_secondary = "#636E72"
        self.c_accent = "#6C5CE7"       # Púrpura acento
        self.c_success = "#2ECC71"      # Verde éxito
        self.c_warning = "#F39C12"      # Naranja advertencia
        self.c_danger = "#E74C3C"       # Rojo alerta

        self.root.configure(bg=self.c_bg)

        # Configuración de estilos ttk
        self.setup_ttk_styles()

        # Variables de estado global
        self.selected_camera_id: Optional[int] = None
        self.active_tab_name: str = "inicio"
        self.tab_buttons = {}
        self.tab_frames = {}

        # Estado de traducción en vivo (Pestaña 4)
        self.is_translating: bool = False
        self.translator_cap = None
        self.translator_instance = None
        self.translation_thread: Optional[threading.Thread] = None
        self.translation_lock = threading.Lock()
        self.latest_translator_frame = None
        self.history_words = []
        self.tts_enabled = tk.BooleanVar(value=False)
        self.vcam_enabled = tk.BooleanVar(value=False)
        self.vcam_manager = None

        # Instancia de gui_captura (Pestaña 2)
        self.capture_gui_instance: Optional[CaptureGUI] = None

        # Construir estructura visual
        self.create_layout()

        # Centrar ventana
        self.center_window()

        # Manejar cierre seguro
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

        # Mostrar pestaña de inicio por defecto
        self.switch_tab("inicio")

    def setup_ttk_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground="#FFFFFF", background="#E2E8F0")
        style.configure("Horizontal.TProgressbar", background=self.c_accent, troughcolor="#E2E8F0")

    def center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # =========================================================================
    # LAYOUT GENERAL: SIDEBAR Y CONTENEDOR DINÁMICO
    # =========================================================================

    def create_layout(self):
        # 1. SIDEBAR LATERAL (Izquierda)
        self.sidebar = tk.Frame(self.root, bg=self.c_sidebar, width=240)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Encabezado del Sidebar (Logo y Marca)
        header_box = tk.Frame(self.sidebar, bg="#181825", height=100)
        header_box.pack(fill=tk.X, side=tk.TOP)
        header_box.pack_propagate(False)

        lbl_logo = tk.Label(
            header_box,
            text="HandTalk",
            font=("Segoe UI", 18, "bold"),
            bg="#181825",
            fg="#FFFFFF"
        )
        lbl_logo.pack(pady=(22, 2))

        lbl_sublogo = tk.Label(
            header_box,
            text="Traductor IA Personalizado",
            font=("Segoe UI", 9),
            bg="#181825",
            fg="#A5ADCB"
        )
        lbl_sublogo.pack()

        # Contenedor de Botones de Navegación
        nav_box = tk.Frame(self.sidebar, bg=self.c_sidebar)
        nav_box.pack(fill=tk.BOTH, expand=True, pady=15, padx=10)

        tabs_info = [
            ("inicio", "Inicio", "Panel general y diagnóstico"),
            ("capturar", "Capturar Señas", "Grabación de gestos"),
            ("entrenar", "Entrenar Modelo", "Ajuste del clasificador"),
            ("traducir", "Traducir y Visor", "Inferencia en vivo y QR"),
        ]

        for tab_id, label_text, desc_text in tabs_info:
            btn = self.create_nav_button(nav_box, tab_id, label_text, desc_text)
            self.tab_buttons[tab_id] = btn

        # Pie del Sidebar (Selector de Cámara y Salir)
        footer_box = tk.Frame(self.sidebar, bg="#181825", height=120)
        footer_box.pack(fill=tk.X, side=tk.BOTTOM)
        footer_box.pack_propagate(False)

        tk.Label(
            footer_box,
            text="Cámara de Entrada:",
            font=("Segoe UI", 8),
            bg="#181825",
            fg="#A5ADCB"
        ).pack(anchor=tk.W, padx=15, pady=(8, 2))

        # Selector de cámara
        self.camera_var = tk.StringVar(value="Cámara 0 (Predeterminada)")
        cam_combo = ttk.Combobox(
            footer_box,
            textvariable=self.camera_var,
            values=["Cámara 0 (Predeterminada)", "Cámara 1", "Cámara 2"],
            state="readonly",
            font=("Segoe UI", 9)
        )
        cam_combo.pack(fill=tk.X, padx=15, pady=(0, 8))
        cam_combo.bind("<<ComboboxSelected>>", self.on_camera_selected)

        # Botón Salir
        btn_exit = tk.Label(
            footer_box,
            text="Salir de HandTalk",
            font=("Segoe UI", 9, "bold"),
            bg="#181825",
            fg="#E74C3C",
            cursor="hand2"
        )
        btn_exit.pack(anchor=tk.W, padx=15, pady=4)
        btn_exit.bind("<Button-1>", lambda e: self.on_close_window())
        btn_exit.bind("<Enter>", lambda e: btn_exit.config(fg="#C0392B"))
        btn_exit.bind("<Leave>", lambda e: btn_exit.config(fg="#E74C3C"))

        # 2. CONTENEDOR DINÁMICO (Derecha)
        self.content_container = tk.Frame(self.root, bg=self.c_bg)
        self.content_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Inicializar vistas (Frames)
        self.init_tab_inicio()
        self.init_tab_capturar()
        self.init_tab_entrenar()
        self.init_tab_traducir()

    def create_nav_button(self, parent, tab_id: str, title: str, desc: str):
        card = tk.Frame(parent, bg=self.c_sidebar, cursor="hand2", padx=10, pady=10)
        card.pack(fill=tk.X, pady=5)

        lbl_title = tk.Label(
            card,
            text=title,
            font=("Segoe UI", 11, "bold"),
            bg=self.c_sidebar,
            fg="#CAD3F5",
            anchor="w"
        )
        lbl_title.pack(fill=tk.X)

        lbl_desc = tk.Label(
            card,
            text=desc,
            font=("Segoe UI", 8),
            bg=self.c_sidebar,
            fg="#8087A2",
            anchor="w"
        )
        lbl_desc.pack(fill=tk.X)

        widgets = [card, lbl_title, lbl_desc]

        def on_enter(e):
            if self.active_tab_name != tab_id:
                for w in widgets:
                    w.config(bg=self.c_sidebar_hover)

        def on_leave(e):
            if self.active_tab_name != tab_id:
                for w in widgets:
                    w.config(bg=self.c_sidebar)

        def on_click(e):
            self.switch_tab(tab_id)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)

        card.title_label = lbl_title
        card.desc_label = lbl_desc
        card.widgets = widgets
        return card

    def on_camera_selected(self, event=None):
        val = self.camera_var.get()
        if "1" in val:
            self.selected_camera_id = 1
        elif "2" in val:
            self.selected_camera_id = 2
        else:
            self.selected_camera_id = 0
        logger.info("Cámara seleccionada: %s", self.selected_camera_id)
        if self.capture_gui_instance:
            self.capture_gui_instance.camera_id = self.selected_camera_id

    # =========================================================================
    # GESTOR DE CICLO DE VIDA DE PESTAÑAS (on_enter / on_leave)
    # =========================================================================

    def switch_tab(self, new_tab: str):
        if self.active_tab_name == new_tab and self.tab_frames.get(new_tab, None) is not None and self.tab_frames[new_tab].winfo_ismapped():
            return

        old_tab = self.active_tab_name

        # 1. Llamar hook on_leave de la pestaña que sale
        if old_tab == "capturar" and self.capture_gui_instance:
            self.capture_gui_instance.cleanup()

        if old_tab == "traducir" and self.is_translating:
            self.stop_live_translation()

        # 2. Ocultar todas las pestañas
        for f in self.tab_frames.values():
            f.pack_forget()

        # 3. Actualizar estilo visual del Sidebar
        for t_id, btn in self.tab_buttons.items():
            if t_id == new_tab:
                for w in btn.widgets:
                    w.config(bg=self.c_sidebar_active)
                btn.title_label.config(fg="#FFFFFF")
                btn.desc_label.config(fg="#E0E7FF")
            else:
                for w in btn.widgets:
                    w.config(bg=self.c_sidebar)
                btn.title_label.config(fg="#CAD3F5")
                btn.desc_label.config(fg="#8087A2")

        # 4. Mostrar pestaña nueva
        self.active_tab_name = new_tab
        target_frame = self.tab_frames.get(new_tab)
        if target_frame:
            target_frame.pack(fill=tk.BOTH, expand=True)

        # 5. Llamar hook on_enter de la pestaña que entra
        if new_tab == "inicio":
            self.refresh_tab_inicio_data()
        elif new_tab == "capturar":
            if self.capture_gui_instance:
                self.capture_gui_instance.update_words_list()
        elif new_tab == "entrenar":
            self.refresh_tab_entrenar_data()
        elif new_tab == "traducir":
            self.refresh_tab_traducir_status()

    # =========================================================================
    # PESTAÑA 1: INICIO Y DIAGNÓSTICO
    # =========================================================================

    def init_tab_inicio(self):
        frame = tk.Frame(self.content_container, bg=self.c_bg, padx=30, pady=25)
        self.tab_frames["inicio"] = frame

        # Banner de Bienvenida
        banner = tk.Frame(frame, bg=self.c_card_bg, padx=25, pady=20, relief=tk.FLAT)
        banner.pack(fill=tk.X, pady=(0, 20))

        tk.Label(
            banner,
            text="Bienvenido a HandTalk",
            font=("Segoe UI", 20, "bold"),
            bg=self.c_card_bg,
            fg=self.c_accent
        ).pack(anchor=tk.W)

        tk.Label(
            banner,
            text="Sistema Inteligente de Reconocimiento y Traducción de Señas Personalizadas con IA",
            font=("Segoe UI", 11),
            bg=self.c_card_bg,
            fg=self.c_text_secondary
        ).pack(anchor=tk.W, pady=(4, 0))

        # Tarjetas de Estado del Sistema (3 Columnas)
        cards_frame = tk.Frame(frame, bg=self.c_bg)
        cards_frame.pack(fill=tk.X, pady=(0, 25))
        cards_frame.columnconfigure(0, weight=1)
        cards_frame.columnconfigure(1, weight=1)
        cards_frame.columnconfigure(2, weight=1)

        # Tarjeta 1: Dataset
        self.card_dataset = self.create_status_card(
            cards_frame, col=0, title="Dataset Personal",
            val_text="Cargando...", sub_text="Muestras recolectadas"
        )

        # Tarjeta 2: Modelo IA
        self.card_model = self.create_status_card(
            cards_frame, col=1, title="Modelo Clasificador",
            val_text="Verificando...", sub_text="Estado del clasificador"
        )

        # Tarjeta 3: Red y Visor Web
        self.card_network = self.create_status_card(
            cards_frame, col=2, title="Servidor y Red",
            val_text="Detectando IP...", sub_text="Puerto 8000"
        )

        # Sección: Guía Rápida de 3 Pasos
        steps_card = tk.Frame(frame, bg=self.c_card_bg, padx=25, pady=20)
        steps_card.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            steps_card,
            text="Flujo de Trabajo en 3 Pasos",
            font=("Segoe UI", 14, "bold"),
            bg=self.c_card_bg,
            fg=self.c_text_primary
        ).pack(anchor=tk.W, pady=(0, 15))

        steps = [
            ("1. Capturar Señas", "Graba de 20 a 30 muestras de cada gesto personalizado. Cada gesto es normalizado de forma invariante a luz y distancia."),
            ("2. Entrenar Modelo", "Entrena el clasificador con un solo clic. El entrenamiento tarda pocos segundos y genera métricas de validación."),
            ("3. Traducir y Compartir", "Inicia la traducción en vivo y proyecta subtítulos en tiempo real a smartphones mediante Código QR en la misma red Wi-Fi."),
        ]

        for num_title, desc in steps:
            s_box = tk.Frame(steps_card, bg=self.c_card_bg, pady=6)
            s_box.pack(fill=tk.X)
            tk.Label(
                s_box, text=num_title, font=("Segoe UI", 11, "bold"),
                bg=self.c_card_bg, fg=self.c_sidebar_active
            ).pack(anchor=tk.W)
            tk.Label(
                s_box, text=desc, font=("Segoe UI", 9),
                bg=self.c_card_bg, fg=self.c_text_secondary, wraplength=700, justify="left"
            ).pack(anchor=tk.W)

        # Botón de Acción Rápida
        btn_start = tk.Button(
            steps_card,
            text="Comenzar Grabando Señas ->",
            font=("Segoe UI", 11, "bold"),
            bg=self.c_sidebar_active,
            fg="#FFFFFF",
            activebackground="#3724B0",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=18,
            pady=8,
            cursor="hand2",
            command=lambda: self.switch_tab("capturar")
        )
        btn_start.pack(anchor=tk.W, pady=(20, 0))

    def create_status_card(self, parent, col: int, title: str, val_text: str, sub_text: str):
        card = tk.Frame(parent, bg=self.c_card_bg, padx=15, pady=15)
        card.grid(row=0, column=col, sticky="nsew", padx=8)

        tk.Label(card, text=title, font=("Segoe UI", 10, "bold"), bg=self.c_card_bg, fg=self.c_text_secondary).pack(anchor=tk.W)
        lbl_val = tk.Label(card, text=val_text, font=("Segoe UI", 13, "bold"), bg=self.c_card_bg, fg=self.c_text_primary)
        lbl_val.pack(anchor=tk.W, pady=(6, 2))
        lbl_sub = tk.Label(card, text=sub_text, font=("Segoe UI", 8), bg=self.c_card_bg, fg="#A0AEC0")
        lbl_sub.pack(anchor=tk.W)

        card.lbl_val = lbl_val
        card.lbl_sub = lbl_sub
        return card

    def refresh_tab_inicio_data(self):
        # 1. Datos del dataset
        try:
            words = dataset_manager.get_existing_words()
            total_samples = sum(dataset_manager.count_samples_for_word(w) for w in words)
            if words:
                self.card_dataset.lbl_val.config(text=f"{len(words)} señas ({total_samples} muestras)", fg=self.c_accent)
                self.card_dataset.lbl_sub.config(text=", ".join(words[:4]) + ("..." if len(words) > 4 else ""))
            else:
                self.card_dataset.lbl_val.config(text="Sin señas", fg=self.c_warning)
                self.card_dataset.lbl_sub.config(text="Captura al menos 2 palabras")
        except Exception:
            self.card_dataset.lbl_val.config(text="Error de lectura", fg=self.c_danger)

        # 2. Datos del modelo
        models_dir = os.path.join(PROJECT_ROOT, "models")
        model_file = os.path.join(models_dir, "custom_sign_model.pkl")
        meta_file = os.path.join(models_dir, "custom_sign_meta.json")

        if os.path.exists(model_file) and os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                words_trained = meta.get("words", [])
                self.card_model.lbl_val.config(text="Entrenado y Listo [OK]", fg=self.c_success)
                self.card_model.lbl_sub.config(text=f"{len(words_trained)} señas activas ({meta.get('model_type', 'RF')})")
            except Exception:
                self.card_model.lbl_val.config(text="Modelo disponible", fg=self.c_success)
                self.card_model.lbl_sub.config(text="Listo para traducir")
        else:
            self.card_model.lbl_val.config(text="No entrenado [Aviso]", fg=self.c_warning)
            self.card_model.lbl_sub.config(text="Entrena en la Pestaña 3")

        # 3. Datos de red
        ip = qr_generator.obtener_ip_local()
        self.card_network.lbl_val.config(text=f"IP: {ip}", fg=self.c_text_primary)
        self.card_network.lbl_sub.config(text=f"Puerto {qr_generator.PUERTO} | Visor Web")

    # =========================================================================
    # PESTAÑA 2: CAPTURA DE SEÑAS EMBEBIDA
    # =========================================================================

    def init_tab_capturar(self):
        frame = tk.Frame(self.content_container, bg=self.c_bg)
        self.tab_frames["capturar"] = frame

        # Instanciar CaptureGUI dentro de este frame contenedor
        self.capture_gui_instance = CaptureGUI(
            root=self.root,
            parent_frame=frame,
            camera_id=self.selected_camera_id
        )

    # =========================================================================
    # PESTAÑA 3: GESTIÓN Y ENTRENAMIENTO
    # =========================================================================

    def init_tab_entrenar(self):
        frame = tk.Frame(self.content_container, bg=self.c_bg, padx=30, pady=25)
        self.tab_frames["entrenar"] = frame

        # Título
        lbl_title = tk.Label(
            frame,
            text="Entrenamiento del Modelo IA de Señas",
            font=("Segoe UI", 18, "bold"),
            bg=self.c_bg,
            fg=self.c_text_primary
        )
        lbl_title.pack(anchor=tk.W, pady=(0, 15))

        # Contenedor Horizontal (Columna Izquierda: Opciones y Dataset / Columna Derecha: Consola)
        content_box = tk.Frame(frame, bg=self.c_bg)
        content_box.pack(fill=tk.BOTH, expand=True)
        content_box.columnconfigure(0, weight=1)
        content_box.columnconfigure(1, weight=2)

        # --- Columna Izquierda: Vocabulario y Opciones ---
        left_col = tk.Frame(content_box, bg=self.c_card_bg, padx=20, pady=20)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

        tk.Label(
            left_col,
            text="Vocabulario para Entrenar:",
            font=("Segoe UI", 12, "bold"),
            bg=self.c_card_bg,
            fg=self.c_text_primary
        ).pack(anchor=tk.W, pady=(0, 8))

        self.tree_words = ttk.Treeview(left_col, columns=("Palabra", "Muestras"), show="headings", height=8)
        self.tree_words.heading("Palabra", text="Palabra")
        self.tree_words.heading("Muestras", text="Muestras")
        self.tree_words.column("Palabra", width=120)
        self.tree_words.column("Muestras", width=80, anchor="center")
        self.tree_words.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # Estado de validación
        self.lbl_train_status = tk.Label(
            left_col,
            text="Verificando dataset...",
            font=("Segoe UI", 9),
            bg=self.c_card_bg,
            fg=self.c_text_secondary
        )
        self.lbl_train_status.pack(anchor=tk.W, pady=(0, 15))

        # Opciones de Entrenamiento
        tk.Label(
            left_col,
            text="Configuración del Modelo:",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_card_bg,
            fg=self.c_text_primary
        ).pack(anchor=tk.W, pady=(0, 4))

        opt_box = tk.Frame(left_col, bg=self.c_card_bg)
        opt_box.pack(fill=tk.X, pady=(0, 15))

        tk.Label(opt_box, text="Clasificador:", font=("Segoe UI", 9), bg=self.c_card_bg).grid(row=0, column=0, sticky="w", pady=3)
        self.model_type_var = tk.StringVar(value="random_forest")
        cb_model = ttk.Combobox(
            opt_box, textvariable=self.model_type_var,
            values=["random_forest", "mlp"], state="readonly", width=14
        )
        cb_model.grid(row=0, column=1, padx=8, pady=3)

        tk.Label(opt_box, text="Aumentación:", font=("Segoe UI", 9), bg=self.c_card_bg).grid(row=1, column=0, sticky="w", pady=3)
        self.augment_var = tk.StringVar(value="20")
        cb_aug = ttk.Combobox(
            opt_box, textvariable=self.augment_var,
            values=["10", "20", "30"], state="readonly", width=14
        )
        cb_aug.grid(row=1, column=1, padx=8, pady=3)

        # Botón de Entrenamiento
        self.btn_entrenar = tk.Button(
            left_col,
            text="Entrenar Modelo Ahora",
            font=("Segoe UI", 11, "bold"),
            bg=self.c_sidebar_active,
            fg="#FFFFFF",
            activebackground="#3724B0",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=15,
            pady=10,
            cursor="hand2",
            command=self.start_training_thread
        )
        self.btn_entrenar.pack(fill=tk.X, pady=(10, 0))

        # --- Columna Derecha: Consola Interactiva de Salida ---
        right_col = tk.Frame(content_box, bg=self.c_card_bg, padx=20, pady=20)
        right_col.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            right_col,
            text="Progreso y Métricas de Entrenamiento:",
            font=("Segoe UI", 12, "bold"),
            bg=self.c_card_bg,
            fg=self.c_text_primary
        ).pack(anchor=tk.W, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(right_col, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        self.train_console = scrolledtext.ScrolledText(
            right_col,
            bg="#1E1E2E",
            fg="#A6ADC8",
            insertbackground="#FFFFFF",
            font=("Consolas", 9),
            height=15
        )
        self.train_console.pack(fill=tk.BOTH, expand=True)

    def refresh_tab_entrenar_data(self):
        # Limpiar treeview
        for item in self.tree_words.get_children():
            self.tree_words.delete(item)

        words = dataset_manager.get_existing_words()
        for w in words:
            count = dataset_manager.count_samples_for_word(w)
            self.tree_words.insert("", tk.END, values=(w, count))

        if len(words) < 2:
            self.lbl_train_status.config(
                text=f"Aviso: Se requieren al menos 2 palabras (actuales: {len(words)})",
                fg=self.c_danger
            )
            self.btn_entrenar.config(state=tk.DISABLED, bg="#A0AEC0")
        else:
            self.lbl_train_status.config(
                text=f"Listo: {len(words)} palabras preparadas para procesar.",
                fg=self.c_success
            )
            self.btn_entrenar.config(state=tk.NORMAL, bg=self.c_sidebar_active)

    def start_training_thread(self):
        self.btn_entrenar.config(state=tk.DISABLED, text="Entrenando...")
        self.progress_bar.start(10)
        self.train_console.delete("1.0", tk.END)
        self.train_console.insert(tk.END, "Iniciando proceso de entrenamiento...\n")

        thread = threading.Thread(target=self._run_training_worker, daemon=True)
        thread.start()

    def _run_training_worker(self):
        log_queue = queue.Queue()

        class StdoutRedirector:
            def __init__(self, q):
                self.q = q
            def write(self, text):
                self.q.put(text)
            def flush(self):
                pass

        old_stdout = sys.stdout
        sys.stdout = StdoutRedirector(log_queue)

        def poll_queue():
            try:
                while True:
                    msg = log_queue.get_nowait()
                    self.train_console.insert(tk.END, msg)
                    self.train_console.see(tk.END)
            except queue.Empty:
                pass
            if training_alive:
                self.root.after(100, poll_queue)

        training_alive = True
        self.root.after(100, poll_queue)

        mtype = self.model_type_var.get()
        try:
            aug = int(self.augment_var.get())
        except ValueError:
            aug = 20

        success = False
        error_msg = ""
        try:
            models_dir = os.path.join(PROJECT_ROOT, "models")
            dataset_dir = os.path.join(PROJECT_ROOT, "custom_dataset")
            train_classifier.train(
                dataset_dir=dataset_dir,
                model_type=mtype,
                augment_factor=aug,
                models_dir=models_dir
            )
            success = True
        except Exception as e:
            error_msg = str(e)
        finally:
            sys.stdout = old_stdout
            training_alive = False

        def finish():
            poll_queue()
            self.progress_bar.stop()
            self.btn_entrenar.config(state=tk.NORMAL, text="Entrenar Modelo Ahora")
            if success:
                self.train_console.insert(tk.END, "\n[OK] ¡Entrenamiento completado exitosamente!\n")
                messagebox.showinfo("Éxito", "El modelo ha sido entrenado y guardado correctamente.")
                self.refresh_tab_inicio_data()
            else:
                self.train_console.insert(tk.END, f"\n[ERROR] Falló el entrenamiento: {error_msg}\n")
                messagebox.showerror("Error", f"Error en el entrenamiento: {error_msg}")

        self.root.after(200, finish)

    # =========================================================================
    # PESTAÑA 4: TRADUCTOR Y VISOR UNIFICADO
    # =========================================================================

    def init_tab_traducir(self):
        frame = tk.Frame(self.content_container, bg=self.c_bg, padx=25, pady=20)
        self.tab_frames["traducir"] = frame

        # Barra Superior de Estado y Controles
        top_bar = tk.Frame(frame, bg=self.c_card_bg, padx=15, pady=12)
        top_bar.pack(fill=tk.X, pady=(0, 15))

        # Botón Iniciar/Detener Traducción
        self.btn_toggle_translate = tk.Button(
            top_bar,
            text="Iniciar Traducción en Vivo",
            font=("Segoe UI", 11, "bold"),
            bg=self.c_success,
            fg="#FFFFFF",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self.toggle_live_translation
        )
        self.btn_toggle_translate.pack(side=tk.LEFT, padx=(0, 15))

        # Botón Visor Web (DESHABILITADO hasta que la traducción esté activa)
        self.btn_visor_web = tk.Button(
            top_bar,
            text="Visor Web (QR / Móvil)",
            font=("Segoe UI", 11, "bold"),
            bg="#A0AEC0",
            fg="#FFFFFF",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            state=tk.DISABLED,
            cursor="hand2",
            command=self.open_visor_modal
        )
        self.btn_visor_web.pack(side=tk.LEFT, padx=(0, 15))

        # Toggles de Salidas Complementarias
        self.chk_tts = tk.Checkbutton(
            top_bar,
            text="Voz (TTS)",
            variable=self.tts_enabled,
            font=("Segoe UI", 9),
            bg=self.c_card_bg
        )
        self.chk_tts.pack(side=tk.LEFT, padx=10)

        self.chk_vcam = tk.Checkbutton(
            top_bar,
            text="Cámara Virtual",
            variable=self.vcam_enabled,
            font=("Segoe UI", 9),
            bg=self.c_card_bg
        )
        self.chk_vcam.pack(side=tk.LEFT, padx=10)

        # Indicador de Estado del Servidor
        self.lbl_server_status = tk.Label(
            top_bar,
            text="Servidor: En espera",
            font=("Segoe UI", 9),
            bg=self.c_card_bg,
            fg=self.c_text_secondary
        )
        self.lbl_server_status.pack(side=tk.RIGHT, padx=10)

        # Área de Video Central
        self.video_display_frame = tk.Frame(frame, bg="#2D3436")
        self.video_display_frame.pack(fill=tk.BOTH, expand=True)

        self.translator_video_label = tk.Label(
            self.video_display_frame,
            text="Presione 'Iniciar Traducción en Vivo' para abrir la cámara",
            font=("Segoe UI", 14),
            bg="#2D3436",
            fg="#DFE6E9"
        )
        self.translator_video_label.pack(fill=tk.BOTH, expand=True)

        # Barra Inferior: Historial de Traducción Confirmada
        bottom_bar = tk.Frame(frame, bg=self.c_card_bg, padx=15, pady=10)
        bottom_bar.pack(fill=tk.X, pady=(15, 0))

        tk.Label(
            bottom_bar,
            text="Historial en vivo:",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_card_bg,
            fg=self.c_accent
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_history = tk.Label(
            bottom_bar,
            text="(Las señas confirmadas aparecerán aquí)",
            font=("Segoe UI", 11),
            bg=self.c_card_bg,
            fg=self.c_text_primary
        )
        self.lbl_history.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_clear = tk.Button(
            bottom_bar,
            text="Limpiar",
            font=("Segoe UI", 8),
            bg="#EDF2F7",
            relief=tk.FLAT,
            command=self.clear_translation_history
        )
        btn_clear.pack(side=tk.RIGHT)

    def refresh_tab_traducir_status(self):
        models_dir = os.path.join(PROJECT_ROOT, "models")
        model_file = os.path.join(models_dir, "custom_sign_model.pkl")
        if not os.path.exists(model_file):
            self.translator_video_label.config(
                text="Aviso: No hay un modelo entrenado.\nVe a la Pestaña 3 ('Entrenar Modelo') antes de traducir."
            )
            self.btn_toggle_translate.config(state=tk.DISABLED, bg="#A0AEC0")
        else:
            if not self.is_translating:
                self.translator_video_label.config(
                    text="Presione 'Iniciar Traducción en Vivo' para comenzar"
                )
                self.btn_toggle_translate.config(state=tk.NORMAL, bg=self.c_success)

    def clear_translation_history(self):
        self.history_words.clear()
        self.lbl_history.config(text="(Historial limpio)")

    def toggle_live_translation(self):
        if not self.is_translating:
            self.start_live_translation()
        else:
            self.stop_live_translation()

    def start_live_translation(self):
        models_dir = os.path.join(PROJECT_ROOT, "models")
        try:
            self.translator_instance = realtime_translator.CustomSignTranslator(models_dir=models_dir)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo inicializar el traductor: {e}")
            return

        self.translator_cap, _ = camera_utils.open_camera(self.selected_camera_id)
        if self.translator_cap is None:
            messagebox.showerror("Error", "No se pudo abrir la cámara web.")
            return

        # Inicializar Cámara Virtual opcionalmente
        if self.vcam_enabled.get():
            try:
                from virtual_cam import VirtualCamManager
                self.vcam_manager = VirtualCamManager(width=640, height=480, fps=30)
            except Exception:
                self.vcam_manager = None

        self.is_translating = True
        self.btn_toggle_translate.config(text="Detener Traducción", bg=self.c_danger)

        # HABILITAR EL BOTÓN DEL VISOR WEB AHORA QUE LA TRADUCCIÓN ESTÁ ACTIVA
        self.btn_visor_web.config(state=tk.NORMAL, bg=self.c_sidebar_active)

        # Iniciar hilo de captura y traducción
        self.translation_thread = threading.Thread(target=self._live_translation_loop, daemon=True)
        self.translation_thread.start()

        # Iniciar refresco de video en Tkinter
        self._update_translation_ui_frame()

    def stop_live_translation(self):
        self.is_translating = False
        if self.translator_cap is not None:
            try:
                self.translator_cap.release()
            except Exception:
                pass
            self.translator_cap = None

        self.btn_toggle_translate.config(text="Iniciar Traducción en Vivo", bg=self.c_success)

        # DESHABILITAR EL BOTÓN DEL VISOR WEB CUANDO SE DETIENE LA TRADUCCIÓN
        self.btn_visor_web.config(state=tk.DISABLED, bg="#A0AEC0")

        self.translator_video_label.config(image="", text="Traducción detenida")

    def _live_translation_loop(self):
        while self.is_translating and self.translator_cap is not None:
            ret, frame = self.translator_cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            frame = cv2.flip(frame, 1)

            # Inferencia con IA
            label, confidence, results, confirmed = self.translator_instance.predict(frame)
            display_frame = self.translator_instance.draw_overlay(frame.copy(), label, confidence, results, confirmed)

            # 1. Alimentar frame al visor web
            web_server.update_remote_frame(display_frame)

            # 2. Si se confirmó una palabra:
            if confirmed:
                self.on_word_confirmed_event(confirmed, confidence)

            # 3. Enviar a cámara virtual si está activa
            if self.vcam_manager and self.vcam_manager.is_active:
                try:
                    self.vcam_manager.send_frame(display_frame)
                except Exception:
                    pass

            with self.translation_lock:
                self.latest_translator_frame = display_frame

            time.sleep(0.015)

    def on_word_confirmed_event(self, word: str, confidence: float):
        # 1. Emitir a clientes WebSocket del Visor Web
        web_server.broadcast_translation_sync(word, confidence)

        # 2. Actualizar interfaz local
        self.root.after(0, lambda: self._update_history_ui(word))

        # 3. Texto a Voz si está activado
        if self.tts_enabled.get():
            threading.Thread(target=self._speak_word, args=(word,), daemon=True).start()

    def _update_history_ui(self, word: str):
        self.history_words.append(word)
        if len(self.history_words) > 8:
            self.history_words.pop(0)
        self.lbl_history.config(text=" -> ".join(self.history_words))

    def _speak_word(self, word: str):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(word)
            engine.runAndWait()
        except Exception:
            pass

    def _update_translation_ui_frame(self):
        if not self.is_translating:
            return

        with self.translation_lock:
            frame = self.latest_translator_frame.copy() if self.latest_translator_frame is not None else None

        if frame is not None:
            # Escalar imagen para ajustarse
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
            imgtk = ImageTk.PhotoImage(image=img)
            self.translator_video_label.imgtk = imgtk
            self.translator_video_label.config(image=imgtk, text="")

        self.root.after(16, self._update_translation_ui_frame)

    # =========================================================================
    # VENTANA MODAL DEL VISOR WEB (QR, PIN Y ENLACE LOCAL)
    # =========================================================================

    def open_visor_modal(self):
        # 1. Iniciar servidor FastAPI en segundo plano si aún no corre
        try:
            web_server.start_server_background(host="0.0.0.0", port=8000)
            self.lbl_server_status.config(text="Servidor: En línea (8000) [Activo]", fg=self.c_success)
        except Exception as e:
            logger.warning("Aviso servidor web: %s", e)

        # 2. Obtener credenciales dinámicas
        info = qr_generator.generar_info_visor()

        # 3. Construir ventana Toplevel modal
        modal = tk.Toplevel(self.root)
        modal.title("Visor Web Remoto — HandTalk")
        modal.geometry("520x640")
        modal.resizable(False, False)
        modal.configure(bg=self.c_bg)
        modal.transient(self.root)
        modal.grab_set()

        # Centrar sobre la ventana principal
        modal.update_idletasks()
        mx = self.root.winfo_x() + (self.root.winfo_width() - 520) // 2
        my = self.root.winfo_y() + (self.root.winfo_height() - 640) // 2
        modal.geometry(f"+{mx}+{my}")

        # Contenedor interior blanco
        card = tk.Frame(modal, bg=self.c_card_bg, padx=25, pady=20)
        card.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(
            card,
            text="Conexión al Visor Remoto",
            font=("Segoe UI", 16, "bold"),
            bg=self.c_card_bg,
            fg=self.c_text_primary
        ).pack(pady=(0, 4))

        tk.Label(
            card,
            text="Escanea el código con tu celular (en la misma red Wi-Fi)",
            font=("Segoe UI", 9),
            bg=self.c_card_bg,
            fg=self.c_text_secondary
        ).pack(pady=(0, 15))

        # Imagen del Código QR
        qr_path = info["archivo_qr"]
        if os.path.exists(qr_path):
            try:
                pil_img = Image.open(qr_path).resize((220, 220), Image.Resampling.LANCZOS)
                qr_imgtk = ImageTk.PhotoImage(pil_img)
                lbl_qr = tk.Label(card, image=qr_imgtk, bg=self.c_card_bg)
                lbl_qr.image = qr_imgtk
                lbl_qr.pack(pady=(0, 15))
            except Exception as e:
                tk.Label(card, text=f"Error cargando QR: {e}", bg=self.c_card_bg, fg=self.c_danger).pack()
        else:
            tk.Label(card, text="Generando QR...", bg=self.c_card_bg).pack()

        # Enlace Local Directo (Clickeable)
        url_local = f"http://localhost:{info['puerto']}/"
        lbl_link = tk.Label(
            card,
            text=f"Abrir en navegador: {url_local}",
            font=("Segoe UI", 10, "underline"),
            bg=self.c_card_bg,
            fg=self.c_sidebar_active,
            cursor="hand2"
        )
        lbl_link.pack(pady=4)
        lbl_link.bind("<Button-1>", lambda e: webbrowser.open(url_local))

        # Tarjeta de PIN de Acceso
        pin_box = tk.Frame(card, bg="#F0F3F8", padx=15, pady=10, relief=tk.GROOVE)
        pin_box.pack(fill=tk.X, pady=12)

        tk.Label(
            pin_box,
            text="PIN DE SEGURIDAD (Login Manual):",
            font=("Segoe UI", 8, "bold"),
            bg="#F0F3F8",
            fg=self.c_text_secondary
        ).pack()

        pin_str = str(info.get("pin", "000000"))
        lbl_pin = tk.Label(
            pin_box,
            text=pin_str,
            font=("Consolas", 22, "bold"),
            bg="#F0F3F8",
            fg=self.c_text_primary
        )
        lbl_pin.pack(pady=2)

        def copy_pin():
            self.root.clipboard_clear()
            self.root.clipboard_append(pin_str)
            btn_copy.config(text="PIN Copiado")
            modal.after(1500, lambda: btn_copy.config(text="Copiar PIN"))

        btn_copy = tk.Button(
            pin_box,
            text="Copiar PIN",
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            relief=tk.FLAT,
            command=copy_pin
        )
        btn_copy.pack(pady=(4, 0))

        # Botón Cerrar
        btn_close = tk.Button(
            card,
            text="Cerrar Ventana",
            font=("Segoe UI", 10),
            bg="#EDF2F7",
            relief=tk.FLAT,
            padx=20,
            pady=6,
            command=modal.destroy
        )
        btn_close.pack(pady=(10, 0))

    # =========================================================================
    # CIERRE SEGURO DE LA APLICACIÓN
    # =========================================================================

    def on_close_window(self):
        if self.is_translating:
            self.stop_live_translation()
        if self.capture_gui_instance:
            self.capture_gui_instance.cleanup()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = UniversalMenuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
