#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interfaz Grafica - Traductor de Lenguaje de Senias
Interfaz moderna y amigable para el sistema
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import sys
import os
import threading
import io

# Forzar UTF-8 en Windows para evitar errores charmap
# Solo si stdout existe y tiene buffer (no aplica en .exe empaquetado)
try:
    if sys.stdout is not None and hasattr(sys.stdout, 'buffer') and sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr is not None and hasattr(sys.stderr, 'buffer') and sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass  # Ignorar errores en entorno empaquetado

class TranslatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Traductor de Lenguaje de Senias")
        self.root.geometry("900x650")
        self.root.resizable(False, False)
        
        # Obtener ruta absoluta del directorio actual
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.script_dir)
        
        # Configurar estilos
        self.setup_styles()
        
        # Crear interfaz
        self.create_header()
        self.create_main_content()
        self.create_footer()
        
        # Centrar ventana
        self.center_window()
        
        # Variable para procesos
        self.current_process = None
    
    def setup_styles(self):
        """Configurar estilos y colores"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colores Modernos y Vibrantes
        self.bg_color = "#F0F2F5"      # Fondo gris muy suave
        self.header_color = "#4834D4"  # Azul/Violeta vibrante
        self.card_bg = "#FFFFFF"       # Blanco puro
        self.text_primary = "#2D3436"  # Gris muy oscuro
        self.text_secondary = "#636E72"# Gris medio
        self.accent_color = "#6C5CE7"  # Acento principal
        
        self.root.configure(bg=self.bg_color)
    
    def center_window(self):
        """Centrar ventana en pantalla"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_header(self):
        """Crear encabezado moderno"""
        header = tk.Frame(self.root, bg=self.header_color, height=120)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        
        # Contenedor para centrar contenido
        content = tk.Frame(header, bg=self.header_color)
        content.pack(expand=True)
        
        # Titulo principal con icono
        title = tk.Label(
            content,
            text="👋 Traductor de Lenguaje de Señas",
            font=("Segoe UI", 24, "bold"),
            bg=self.header_color,
            fg="white"
        )
        title.pack(pady=(20, 5))
        
        # Subtitulo
        subtitle = tk.Label(
            content,
            text="Sistema Inteligente de Reconocimiento de Gestos con IA",
            font=("Segoe UI", 11),
            bg=self.header_color,
            fg="#DFE6E9"
        )
        subtitle.pack(pady=(0, 15))
    
    def create_main_content(self):
        """Crear contenido principal"""
        main_frame = tk.Frame(self.root, bg=self.bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        
        # Titulo de secciones
        section_title = tk.Label(
            main_frame,
            text="Panel de Control",
            font=("Segoe UI", 14, "bold"),
            bg=self.bg_color,
            fg=self.text_primary
        )
        section_title.pack(anchor=tk.W, pady=(0, 15))
        
        # Frame para botones en grid
        buttons_frame = tk.Frame(main_frame, bg=self.bg_color)
        buttons_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configurar columnas para que tengan el mismo ancho
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_columnconfigure(1, weight=1)
        
        # Opciones disponibles con nuevos iconos y colores
        options = [
            {
                "number": "1",
                "title": "Verificar Sistema",
                "description": "Comprobar instalación y dependencias",
                "command": self.check_system,
                "icon": "✅",
                "color": "#2ECC71" # Green
            },
            {
                "number": "2",
                "title": "Traductor de Dígitos",
                "description": "Detectar dígitos (0-9) en tiempo real",
                "command": self.translator_realtime,
                "icon": "🔢",
                "color": "#3498DB" # Blue
            },
            {
                "number": "3",
                "title": "Traductor de Letras",
                "description": "Detectar letras (A-Z) en tiempo real",
                "command": self.translator_unified,
                "icon": "🔤",
                "color": "#9B59B6" # Purple
            },
            {
                "number": "4",
                "title": "Entrenar Dígitos (0-9)",
                "description": "Entrenar modelo CNN de dígitos (10-15 min)",
                "command": self.train_model,
                "icon": "🧠",
                "color": "#E67E22" # Orange
            },
            {
                "number": "5",
                "title": "Entrenar Letras (A-Z)",
                "description": "Entrenar modelo CNN de letras (10-15 min)",
                "command": self.train_model_unified,
                "icon": "📚",
                "color": "#D35400" # Dark Orange
            },
            {
                "number": "6",
                "title": "Procesar Imagen",
                "description": "Clasificar dígito de una imagen",
                "command": self.process_image,
                "icon": "🖼️",
                "color": "#1ABC9C" # Turquoise
            },
            {
                "number": "7",
                "title": "Grabar Video",
                "description": "Grabar 10 segundos de detección",
                "command": self.record_video,
                "icon": "🎥",
                "color": "#E74C3C" # Red
            },
            {
                "number": "8",
                "title": "Información del Proyecto",
                "description": "Ver detalles técnicos del sistema",
                "command": self.show_info,
                "icon": "ℹ️",
                "color": "#95A5A6" # Gray
            }
        ]
        
        # Crear botones (2 columnas)
        for idx, option in enumerate(options):
            row = idx // 2
            col = idx % 2
            
            # Si es el ultimo elemento y es impar, centrarlo ocupando 2 columnas
            if idx == len(options) - 1 and len(options) % 2 != 0:
                self.create_option_button(buttons_frame, option, row, col, is_centered=True)
            else:
                self.create_option_button(buttons_frame, option, row, col)
    
    def create_option_button(self, parent, option, row, col, is_centered=False):
        """Crear tarjeta de opcion interactiva con color"""
        # Frame principal de la tarjeta (Card)
        card = tk.Frame(parent, bg=self.card_bg, cursor="hand2")
        
        # Color especifico de la tarjeta
        card_color = option.get("color", self.accent_color)
        
        if is_centered:
            # Centrado: ocupa 2 columnas, con margenes para no verse tan estirado
            card.grid(row=row, column=0, columnspan=2, padx=100, pady=10, sticky="nsew")
        else:
            card.grid(row=row, column=col, padx=15, pady=10, sticky="nsew")
        
        # Tira de color a la izquierda
        color_strip = tk.Frame(card, bg=card_color, width=6)
        color_strip.pack(side=tk.LEFT, fill=tk.Y)
        
        # Contenedor interno
        inner_content = tk.Frame(card, bg=self.card_bg)
        inner_content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configurar grid interno de la tarjeta
        inner_content.grid_columnconfigure(1, weight=1)
        
        # Icono/Emoji (Izquierda)
        icon_label = tk.Label(
            inner_content,
            text=option['icon'],
            font=("Segoe UI", 20),
            bg=self.card_bg,
            fg=card_color,
            width=4
        )
        icon_label.grid(row=0, column=0, rowspan=2, padx=(5, 15))
        
        # Titulo (Derecha Arriba)
        title_label = tk.Label(
            inner_content,
            text=option['title'],
            font=("Segoe UI", 12, "bold"),
            bg=self.card_bg,
            fg=self.text_primary,
            anchor="w"
        )
        title_label.grid(row=0, column=1, sticky="w")
        
        # Descripcion (Derecha Abajo)
        desc_label = tk.Label(
            inner_content,
            text=option['description'],
            font=("Segoe UI", 9),
            bg=self.card_bg,
            fg=self.text_secondary,
            anchor="w",
            wraplength=220,
            justify="left"
        )
        desc_label.grid(row=1, column=1, sticky="nw")
        
        # Eventos de Hover y Click
        widgets = [card, inner_content, icon_label, title_label, desc_label]
        
        def on_enter(e):
            # Color de fondo muy suave al hacer hover
            hover_bg = "#F8F9FA"
            for w in widgets:
                w.config(bg=hover_bg)
            # Resaltar titulo con el color de la tarjeta
            title_label.config(fg=card_color)
            
        def on_leave(e):
            for w in widgets:
                w.config(bg=self.card_bg)
            title_label.config(fg=self.text_primary)
            
        def on_click(e):
            # Efecto visual de click
            click_bg = "#E8E8E8"
            for w in widgets:
                w.config(bg=click_bg)
            self.root.update()
            self.root.after(100, lambda: on_enter(None)) # Restaurar color hover
            # Ejecutar comando
            option['command']()

        for w in widgets + [color_strip]:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)
    
    def on_button_hover(self, button, entering):
        """Efecto hover en botones (Legacy - No usado en nuevo diseno)"""
        pass
    
    def create_footer(self):
        """Crear pie de pagina minimalista"""
        footer = tk.Frame(self.root, bg="#DFE6E9", height=30)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        
        # Version e info
        info_text = tk.Label(
            footer,
            text="v2.0 | TensorFlow - MediaPipe - OpenCV",
            font=("Segoe UI", 8),
            bg="#DFE6E9",
            fg="#636E72"
        )
        info_text.pack(side=tk.LEFT, padx=20)
        
        # Boton Salir discreto
        exit_btn = tk.Label(
            footer,
            text="SALIR",
            font=("Segoe UI", 8, "bold"),
            bg="#DFE6E9",
            fg="#E74C3C",
            cursor="hand2"
        )
        exit_btn.pack(side=tk.RIGHT, padx=20)
        exit_btn.bind("<Button-1>", lambda e: self.root.quit())
        
        # Hover para salir
        def on_enter(e): exit_btn.config(fg="#C0392B")
        def on_leave(e): exit_btn.config(fg="#E74C3C")
        exit_btn.bind("<Enter>", on_enter)
        exit_btn.bind("<Leave>", on_leave)
    
    def execute_command_list(self, cmd_list, title, is_training=False):
        """Ejecutar comando como lista de argumentos usando threading"""
        try:
            # Mostrar dialogo de ejecucion
            progress_window = tk.Toplevel(self.root)
            progress_window.title(title)
            progress_window.geometry("600x300")
            progress_window.resizable(False, False)
            
            # Hacer ventana modal y siempre visible
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # Centrar ventana de progreso
            progress_window.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 300
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 150
            progress_window.geometry(f"+{x}+{y}")
            
            label = tk.Label(
                progress_window,
                text=title,
                font=("Arial", 12, "bold"),
                fg=self.header_color
            )
            label.pack(pady=20)
            
            text_widget = tk.Text(
                progress_window,
                height=12,
                width=70,
                font=("Courier", 9),
                bg="white",
                fg="#2c3e50"
            )
            text_widget.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
            text_widget.config(state=tk.DISABLED)
            
            # Scrollbar
            scrollbar = tk.Scrollbar(text_widget)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            text_widget.config(yscrollcommand=scrollbar.set)
            scrollbar.config(command=text_widget.yview)
            
            # Preparar el entorno
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            def run_command():
                """Ejecutar comando en thread separado"""
                try:
                    # Ejecutar comando desde el directorio correcto
                    process = subprocess.Popen(
                        cmd_list,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        shell=False,
                        cwd=self.script_dir,
                        env=env,
                        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
                    )
                    
                    # Asegurar que la consola quede detras del sistema
                    # Damos un pequeno tiempo para que la consola se cree y luego traemos la GUI al frente
                    self.root.after(500, lambda: self.root.lift())
                    self.root.after(600, lambda: self.root.focus_force())
                    
                    # Leer output linea por linea
                    for line in process.stdout:
                        text_widget.config(state=tk.NORMAL)
                        text_widget.insert(tk.END, line)
                        text_widget.see(tk.END)
                        text_widget.config(state=tk.DISABLED)
                        progress_window.update()
                    
                    # Esperar a que termine
                    process.wait()
                    
                    # Resultado final
                    text_widget.config(state=tk.NORMAL)
                    if process.returncode == 0:
                        text_widget.insert(tk.END, f"\n[OK] Completado exitosamente\n")
                        messagebox.showinfo("Exito", f"{title}\nCompletado exitosamente")
                    else:
                        text_widget.insert(tk.END, f"\n[AVISO] Proceso finalizado (Codigo: {process.returncode})\n")
                        messagebox.showinfo("Info", f"{title}\nProceso completado")
                    text_widget.config(state=tk.DISABLED)
                    
                except Exception as e:
                    text_widget.config(state=tk.NORMAL)
                    text_widget.insert(tk.END, f"\n[ERROR] {str(e)}\n")
                    text_widget.config(state=tk.DISABLED)
                    messagebox.showerror("Error", f"Error: {str(e)}")
            
            # Iniciar thread
            thread = threading.Thread(target=run_command, daemon=True)
            thread.start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error: {str(e)}")
    
    def check_system(self):
        """Verificar sistema"""
        venv_python = os.path.join(self.project_root, ".venv/Scripts/python.exe")
        
        if not os.path.exists(venv_python):
            messagebox.showerror("Error", f"Python no encontrado en:\n{venv_python}")
            return
        
        # Script de verificacion directamente en Python
        verify_script = '''
import sys
import os

print("=" * 50)
print("VERIFICACION DEL SISTEMA")
print("=" * 50)

# Version Python
print(f"Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

# Dependencias
packages = {
    'cv2': 'OpenCV',
    'mediapipe': 'MediaPipe',
    'numpy': 'NumPy',
    'tensorflow': 'TensorFlow',
    'sklearn': 'Scikit-learn',
    'PIL': 'Pillow'
}

print("\\nDependencias:")
for package, name in packages.items():
    try:
        __import__(package)
        print(f"[OK] {name}")
    except ImportError:
        print(f"[ERROR] {name}")

# Dataset
print("\\nDataset:")
dataset_path = r"''' + self.project_root + r'''/Sign-Language-Digits-Dataset/Dataset"
if os.path.exists(dataset_path):
    total = 0
    for i in range(10):
        digit_path = os.path.join(dataset_path, str(i))
        if os.path.exists(digit_path):
            count = len([f for f in os.listdir(digit_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
            total += count
    print(f"[OK] Dataset encontrado: {total} imagenes")
else:
    print("[ERROR] Dataset no encontrado")
    print(f"[DEBUG] Ruta buscada: {dataset_path}")

# Modelo
print("\\nModelo:")
model_path = r"''' + os.path.join(self.script_dir, 'models/sign_language_model.h5') + r'''"
if os.path.exists(model_path):
    size = os.path.getsize(model_path) / (1024 * 1024)
    print(f"[OK] Modelo encontrado ({size:.2f} MB)")
else:
    print("[WARNING] Modelo no encontrado")
    print(f"[DEBUG] Ruta buscada: {model_path}")

print("=" * 50)
print("[OK] Sistema listo para usar")
print("=" * 50)
'''
        
        # Escribir script temporal
        temp_script = os.path.join(self.script_dir, "temp_verify.py")
        with open(temp_script, "w", encoding="utf-8") as f:
            f.write(verify_script)
        
        cmd = [venv_python, temp_script]
        self.execute_command_list(cmd, "Verificando sistema...")
    
    def train_model(self):
        """Entrenar modelo de dígitos (0-9)"""
        response = messagebox.askyesno(
            "Entrenar Modelo de Dígitos",
            "Esto entrenara el modelo CNN para dígitos (0-9) y puede tomar 10-15 minutos.\n\n"
            "La interfaz permanecera responsiva mostrando el progreso.\n\n"
            "Continuar?"
        )
        
        if response:
            venv_python = os.path.join(self.project_root, ".venv/Scripts/python.exe")
            script = os.path.join(self.script_dir, "train_model.py")
            
            if not os.path.exists(venv_python):
                messagebox.showerror("Error", f"Python no encontrado en:\n{venv_python}")
                return
            
            if not os.path.exists(script):
                messagebox.showerror("Error", f"Script no encontrado en:\n{script}")
                return
            
            cmd = [venv_python, script]
            self.execute_command_list(cmd, "Entrenando modelo de dígitos...", is_training=True)
    
    def train_model_unified(self):
        """Entrenar modelo de letras (A-Z)"""
        response = messagebox.askyesno(
            "Entrenar Modelo de Letras",
            "Esto entrenara el modelo CNN para letras (A-Z) y puede tomar 10-15 minutos.\n\n"
            "La interfaz permanecera responsiva mostrando el progreso.\n\n"
            "Continuar?"
        )
        
        if response:
            venv_python = os.path.join(self.project_root, ".venv/Scripts/python.exe")
            script = os.path.join(self.script_dir, "train_model_letters.py")
            
            if not os.path.exists(venv_python):
                messagebox.showerror("Error", f"Python no encontrado en:\n{venv_python}")
                return
            
            if not os.path.exists(script):
                messagebox.showerror("Error", f"Script no encontrado en:\n{script}")
                return
            
            cmd = [venv_python, script]
            self.execute_command_list(cmd, "Entrenando modelo de letras...", is_training=True)
    
    def translator_realtime(self):
        """Traductor en tiempo real"""
        venv_python = os.path.join(self.project_root, ".venv/Scripts/python.exe")
        script = os.path.join(self.script_dir, "translator_realtime.py")
        
        if not os.path.exists(venv_python):
            messagebox.showerror("Error", f"Python no encontrado en:\n{venv_python}")
            return
        
        if not os.path.exists(script):
            messagebox.showerror("Error", f"Script no encontrado en:\n{script}")
            return
        
        cmd = [venv_python, script, "--mode", "webcam-gui", "--camera", "0"]
        messagebox.showinfo(
            "Traductor en Tiempo Real",
            "Se abrira una ventana con interfaz grafica.\n\n"
            "Caracteristicas:\n"
            "- Vista en vivo de la camara\n"
            "- Digito detectado en grande\n"
            "- Historial de traduccion\n"
            "- Cierra la ventana para salir"
        )
        self.execute_command_list(cmd, "Iniciando traductor...")
    
    def process_image(self):
        """Procesar imagen"""
        file_path = filedialog.askopenfilename(
            title="Seleccionar imagen",
            filetypes=[("Imagenes", "*.jpg *.jpeg *.png"), ("Todos", "*.*")]
        )
        
        if file_path:
            venv_python = os.path.join(self.project_root, ".venv/Scripts/python.exe")
            script = os.path.join(self.script_dir, "translator_realtime.py")
            
            if not os.path.exists(venv_python):
                messagebox.showerror("Error", f"Python no encontrado en:\n{venv_python}")
                return
            
            if not os.path.exists(script):
                messagebox.showerror("Error", f"Script no encontrado en:\n{script}")
                return
            
            cmd = [venv_python, script, "--mode", "image", "--image", file_path]
            self.execute_command_list(cmd, "Procesando imagen...")
    
    def record_video(self):
        """Grabar video"""
        response = messagebox.askyesno(
            "Grabar Video",
            "Se grabara 10 segundos de video con deteccion de manos.\n\n"
            "El archivo se guardara como: output_traduccion.avi\n\n"
            "Continuar?"
        )
        
        if response:
            venv_python = os.path.join(self.project_root, ".venv/Scripts/python.exe")
            script = os.path.join(self.script_dir, "translator_headless.py")
            
            if not os.path.exists(venv_python):
                messagebox.showerror("Error", f"Python no encontrado en:\n{venv_python}")
                return
            
            if not os.path.exists(script):
                messagebox.showerror("Error", f"Script no encontrado en:\n{script}")
                return
            
            cmd = [venv_python, script, "--mode", "video", "--duration", "10"]
            self.execute_command_list(cmd, "Grabando video...")
    
    def translator_unified(self):
        """Traductor de letras - A-Z"""
        venv_python = os.path.join(self.project_root, ".venv/Scripts/python.exe")
        script = os.path.join(self.script_dir, "translator_unified.py")
        
        if not os.path.exists(venv_python):
            messagebox.showerror("Error", f"Python no encontrado en:\n{venv_python}")
            return
        
        if not os.path.exists(script):
            messagebox.showerror("Error", f"Script no encontrado en:\n{script}")
            return
        
        cmd = [venv_python, script, "--mode", "webcam-gui", "--camera", "0"]
        messagebox.showinfo(
            "Traductor de Letras - A-Z",
            "Se abrira una ventana con interfaz grafica.\n\n"
            "Caracteristicas:\n"
            "- Vista en vivo de la camara\n"
            "- Letra detectada en grande\n"
            "- Historial de traduccion\n"
            "- Cierra la ventana para salir"
        )
        self.execute_command_list(cmd, "Iniciando traductor de letras...")
    
    def show_info(self):
        """Mostrar informacion del proyecto con diseño moderno"""
        info_window = tk.Toplevel(self.root)
        info_window.title("Información del Proyecto")
        info_window.geometry("700x600")
        info_window.configure(bg="#1a1a2e")
        info_window.resizable(False, False)
        
        # Hacer ventana modal
        info_window.transient(self.root)
        info_window.grab_set()
        
        # Centrar ventana
        info_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 350
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 300
        info_window.geometry(f"+{x}+{y}")
        
        # Header con gradiente simulado
        header_frame = tk.Frame(info_window, bg="#4834D4", height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="👋 Traductor de Lenguaje de Señas",
            font=("Segoe UI", 18, "bold"),
            bg="#4834D4",
            fg="white"
        )
        title_label.pack(pady=10)
        
        version_label = tk.Label(
            header_frame,
            text="Versión 2.0  •  Noviembre 2025",
            font=("Segoe UI", 10),
            bg="#4834D4",
            fg="#DFE6E9"
        )
        version_label.pack()
        
        # Canvas con scroll para el contenido
        container = tk.Frame(info_window, bg="#1a1a2e")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        canvas = tk.Canvas(container, bg="#1a1a2e", highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#1a1a2e")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Función para crear secciones
        def create_section(parent, title, items, icon="📌"):
            section = tk.Frame(parent, bg="#16213e", padx=15, pady=12)
            section.pack(fill=tk.X, pady=8)
            
            # Título de sección
            title_frame = tk.Frame(section, bg="#16213e")
            title_frame.pack(fill=tk.X, pady=(0, 8))
            
            tk.Label(
                title_frame,
                text=f"{icon} {title}",
                font=("Segoe UI", 12, "bold"),
                bg="#16213e",
                fg="#6C5CE7"
            ).pack(side=tk.LEFT)
            
            # Items
            for item in items:
                item_frame = tk.Frame(section, bg="#16213e")
                item_frame.pack(fill=tk.X, pady=2)
                
                if isinstance(item, tuple):
                    # Item con etiqueta y valor
                    tk.Label(
                        item_frame,
                        text=item[0],
                        font=("Segoe UI", 10),
                        bg="#16213e",
                        fg="#a0a0a0",
                        width=25,
                        anchor="w"
                    ).pack(side=tk.LEFT)
                    
                    tk.Label(
                        item_frame,
                        text=item[1],
                        font=("Segoe UI", 10, "bold"),
                        bg="#16213e",
                        fg="#00CEC9"
                    ).pack(side=tk.LEFT)
                else:
                    # Item simple con check
                    tk.Label(
                        item_frame,
                        text=f"  ✓  {item}",
                        font=("Segoe UI", 10),
                        bg="#16213e",
                        fg="#55efc4"
                    ).pack(side=tk.LEFT)
        
        # Descripción
        desc_frame = tk.Frame(scrollable_frame, bg="#0f3460", padx=15, pady=12)
        desc_frame.pack(fill=tk.X, pady=8)
        
        tk.Label(
            desc_frame,
            text="Sistema de IA para reconocimiento de dígitos (0-9) y letras (A-Z)\nen lenguaje de señas usando visión por computadora y redes neuronales.",
            font=("Segoe UI", 11),
            bg="#0f3460",
            fg="#DFE6E9",
            justify=tk.LEFT,
            wraplength=620
        ).pack(anchor="w")
        
        # Sección: Características
        create_section(scrollable_frame, "CARACTERÍSTICAS", [
            "Detección de manos en tiempo real (21 landmarks)",
            "Clasificación de dígitos 0-9 y letras A-Z",
            "Traducción en vivo desde webcam",
            "Procesamiento de imágenes individuales",
            "Grabación de video con detecciones",
            "Interfaz gráfica moderna y colorida"
        ], "⭐")
        
        # Sección: Arquitectura
        create_section(scrollable_frame, "ARQUITECTURA DEL MODELO", [
            ("Entrada:", "100×100 píxeles RGB"),
            ("Capas Conv:", "3 capas (32→64→128 filtros)"),
            ("Capas Densas:", "256→128 neuronas + Dropout"),
            ("Salida Dígitos:", "Softmax 10 clases"),
            ("Salida Letras:", "Softmax 26 clases"),
            ("Precisión:", "91.53% en datos de prueba")
        ], "🧠")
        
        # Sección: Tecnologías
        create_section(scrollable_frame, "TECNOLOGÍAS", [
            ("Python:", "3.9.0"),
            ("TensorFlow:", "2.13.0 + Keras"),
            ("MediaPipe:", "0.10.14"),
            ("OpenCV:", "4.8.0.74"),
            ("NumPy:", "1.24.3"),
            ("Scikit-learn:", "1.3.0")
        ], "🔧")
        
        # Sección: Dataset
        create_section(scrollable_frame, "DATASETS", [
            ("Dígitos:", "2,062 imágenes (0-9)"),
            ("Letras:", "ASL Alphabet (A-Z)"),
            ("Resolución:", "100×100 píxeles"),
            ("Formato:", "RGB (3 canales)")
        ], "📊")
        
        # Sección: Requisitos
        create_section(scrollable_frame, "REQUISITOS", [
            ("Sistema:", "Windows 10/11, Linux, macOS"),
            ("Python:", "3.9 (incluido en venv)"),
            ("Cámara:", "Webcam para tiempo real"),
            ("RAM:", "4 GB mínimo")
        ], "💻")
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # Footer con botón cerrar
        footer = tk.Frame(info_window, bg="#1a1a2e", height=50)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        
        close_btn = tk.Label(
            footer,
            text="CERRAR",
            font=("Segoe UI", 10, "bold"),
            bg="#e74c3c",
            fg="white",
            padx=30,
            pady=8,
            cursor="hand2"
        )
        close_btn.pack(pady=10)
        close_btn.bind("<Button-1>", lambda e: info_window.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#c0392b"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#e74c3c"))


def main():
    """Funcion principal"""
    root = tk.Tk()
    app = TranslatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
