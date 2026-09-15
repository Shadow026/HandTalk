# 📜 Changelog - HandTalk

Este documento registra los cambios, mejoras y correcciones aplicadas al sistema de reconocimiento de lenguaje de señas, detallando las modificaciones a nivel de código.

## 2026-09-14

### 🛠️ Mejoras en `realtime_translator.py`
**Corrección del sistema de cierre de aplicación**

#### ❌ Antes (Cierre dependiente de tecla)
El programa solo podía cerrarse si el usuario presionaba la tecla 'Q'. Si se cerraba la ventana con la 'X', el proceso seguía corriendo en segundo plano.
```python
# Lógica anterior
cv2.imshow("Traductor de Senas Personalizado", frame)
key = cv2.waitKey(1) & 0xFF
if key in (ord("q"), ord("Q")):
    break
```

#### ✅ Después (Cierre basado en estado de ventana)
Se implementó la detección de la propiedad de visibilidad de la ventana.
```python
# Definición de ventana normalizada
cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL)

# ... dentro del bucle ...
cv2.imshow(NOMBRE_VENTANA, frame)
key = cv2.waitKey(1) & 0xFF

# El fix: Detectar si la ventana fue cerrada mediante la 'X'
if cv2.getWindowProperty(NOMBRE_VENTANA, cv2.WND_PROP_VISIBLE) < 1:
    print("[OK] Ventana cerrada por el usuario.")
    break
```
- **Resultado**: Salida inmediata y limpia del proceso al cerrar la interfaz gráfica.

---

### 🛠️ Mejoras en `gui_captura.py`
**Optimización del renderizado de video (Eliminación de parpadeos)**

#### ❌ Antes (Procesamiento y UI en el mismo hilo)
La captura de frames y la actualización del widget de Tkinter ocurrían en el mismo hilo secundario, causando bloqueos en la UI y parpadeos constantes.
```python
def video_loop(self):
    while self.is_capturing:
        ret, frame = self.cap.read()
        # ... procesamiento de MediaPipe ...
        
        # ERROR: Actualizar Tkinter desde un hilo que no es el principal
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.config(image=imgtk, text="")
```

#### ✅ Después (Arquitectura Desacoplada con Lock)
Se separó la responsabilidad de captura y renderizado en dos flujos distintos coordinados por un cerrojo (`Lock`).

**1. Hilo de Captura (Procesamiento Pesado):**
```python
def capture_loop(self):
    while self.is_capturing:
        ret, frame = self.cap.read()
        # ... procesamiento de MediaPipe ...
        with self.frame_lock: # Escritura segura
            self.frame_actual = frame
```

**2. Hilo de Interfaz (Renderizado Fluido):**
```python
def update_video(self):
    with self.frame_lock: # Lectura segura
        frame = self.frame_actual.copy() if self.frame_actual is not None else None
    
    if frame is not None:
        # ... conversión a PhotoImage ...
        self.video_label.config(image=imgtk, text="")
    
    # Programación asíncrona en el hilo principal de Tkinter
    self.root.after(15, self.update_video)
```
- **Resultado**: Se eliminó el parpadeo visual y se optimizó el uso de CPU al desacoplar el procesamiento de la tasa de refresco de la interfaz.

---