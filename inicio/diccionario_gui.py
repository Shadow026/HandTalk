#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diccionario_gui.py

Pantalla tipo "diccionario": muestra en una cuadrícula el boceto de cada
palabra que el usuario ha creado en su dataset (ver sketch_generator.py y
PLAN_DE_TRABAJO_EQUIPO.md sección 4.1). Es el entregable de la Tarea 2 de
Herber: "una pantalla básica" con los bocetos visibles.

Esta es una implementación FUNCIONAL MÍNIMA pensada para poder mostrar el
resultado ya mismo. El diseño visual final (colores, tipografía, layout)
debe coordinarse con Wilfredo -- ver su documento, Tarea 2 -- antes de dar
esta pantalla por terminada; la lógica de "cargar palabras -> generar
bocetos -> mostrarlos en cuadrícula" ya no debería cambiar mucho aunque
cambie el estilo visual.

Uso:
    python diccionario_gui.py
    python diccionario_gui.py --dataset custom_dataset --columns 4
"""

import argparse
import os
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

import dataset_manager
import sketch_generator


class DictionaryScreen(tk.Tk):
    def __init__(self, dataset_dir=dataset_manager.DEFAULT_DATASET_DIR,
                 sketches_dir=sketch_generator.DEFAULT_SKETCH_DIR,
                 columns=3, thumb_size=180):
        super().__init__()
        self.dataset_dir = dataset_dir
        self.sketches_dir = sketches_dir
        self.columns = columns
        self.thumb_size = thumb_size

        self.title("Diccionario de señas")
        self.geometry("900x650")

        self._build_layout()
        self._photo_refs = []  # evita que el garbage collector borre las imagenes
        self.refresh()

    # ------------------------------------------------------------------
    def _build_layout(self):
        top_bar = ttk.Frame(self, padding=10)
        top_bar.pack(fill="x")

        ttk.Label(top_bar, text="Diccionario de señas", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(top_bar, text="Actualizar", command=self.refresh).pack(side="right")

        self.status_label = ttk.Label(top_bar, text="")
        self.status_label.pack(side="right", padx=10)

        # Area con scroll para la cuadricula de palabras
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, borderwidth=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.grid_frame = ttk.Frame(canvas)

        self.grid_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    def refresh(self):
        """Regenera los bocetos (por si hay palabras/muestras nuevas) y redibuja la cuadricula."""
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self._photo_refs.clear()

        words = dataset_manager.get_existing_words(self.dataset_dir)

        if not words:
            ttk.Label(
                self.grid_frame,
                text="Todavia no hay palabras capturadas en el dataset.\n"
                     "Usa gui_captura.py para crear tu primera seña.",
                padding=30,
            ).grid(row=0, column=0)
            self.status_label.config(text="0 palabras")
            return

        sketches = sketch_generator.generate_all_sketches(
            self.dataset_dir, self.sketches_dir, size=self.thumb_size
        )

        for idx, word in enumerate(words):
            row, col = divmod(idx, self.columns)
            self._add_word_card(row, col, word, sketches.get(word))

        self.status_label.config(text=f"{len(words)} palabra(s)")

    def _add_word_card(self, row, col, word, sketch_path):
        card = ttk.Frame(self.grid_frame, padding=10, relief="groove")
        card.grid(row=row, column=col, padx=10, pady=10)

        if sketch_path and os.path.exists(sketch_path):
            pil_img = Image.open(sketch_path)
            photo = ImageTk.PhotoImage(pil_img)
            self._photo_refs.append(photo)  # referencia viva, si no Tkinter la descarta
            ttk.Label(card, image=photo).pack()
        else:
            ttk.Label(card, text="(sin boceto)", width=20, anchor="center").pack(
                pady=self.thumb_size // 2
            )

        n_muestras = dataset_manager.count_samples_for_word(word, self.dataset_dir)
        ttk.Label(card, text=f"{word}  ({n_muestras} muestras)", font=("Segoe UI", 11, "bold")).pack(pady=(6, 0))


def main():
    parser = argparse.ArgumentParser(description="Pantalla de diccionario de señas")
    parser.add_argument("--dataset", default=dataset_manager.DEFAULT_DATASET_DIR)
    parser.add_argument("--sketches", default=sketch_generator.DEFAULT_SKETCH_DIR)
    parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args()

    app = DictionaryScreen(dataset_dir=args.dataset, sketches_dir=args.sketches, columns=args.columns)
    app.mainloop()


if __name__ == "__main__":
    main()
