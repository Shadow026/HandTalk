# Changelog - HandTalk

Registro cronológico y técnico de cambios, mejoras y correcciones aplicadas a la plataforma HandTalk.

---

## [2026-09-15] - Unificación en Menú Universal, Integración de Instaladores y Estabilización

### 1. Nuevo Menú Universal (`inicio/menu_universal.py`)
- **Interfaz Centralizada**: Se desarrolló una aplicación unificada en Tkinter con diseño moderno y navegación lateral (Sidebar) dividida en 4 módulos principales:
  - **Pestaña 1 - Inicio**: Diagnóstico en tiempo real del entorno (conteo de señas registradas, total de muestras en dataset, estado del modelo entrenado e IP local detectada para el visor web), junto con una guía de inicio rápido.
  - **Pestaña 2 - Captura**: Integración embebida del módulo de captura de datos con esqueleto MediaPipe en tiempo real y guardado de fotogramas.
  - **Pestaña 3 - Entrenar**: Panel de administración de vocabulario con conteo de muestras por seña, validación mínima de clases (requiere al menos 2 señas) y ejecución asíncrona del entrenamiento con barra de progreso y salida por consola en vivo sin bloquear la interfaz.
  - **Pestaña 4 - Traducir y Visor Web**: Inferencia en tiempo real utilizando el modelo entrenado con suavizado de predicciones, salidas configurables para Texto a Voz (TTS) y Cámara Virtual (`v4l2loopback`).
- **Activación Condicional del Visor Web**: El acceso al Visor Web permanece inactivo hasta que la traducción en vivo esté en ejecución. Al activarse, despliega una ventana modal con:
  - Código QR generado dinámicamente.
  - Enlace local clickeable (`http://localhost:8000/viewer`).
  - PIN de seguridad de 6 dígitos con botón para copiar al portapapeles.
- **Gestión del Ciclo de Vida del Hardware**:
  - Implementación de controladores `on_leave` y `on_enter` en el cambio de pestañas para liberar inmediatamente el dispositivo de captura (`cap.release()`), resolviendo conflictos de contención de cámara en OpenCV.

---

### 2. Desacoplamiento del Servidor Web (`web_server.py`)
- **Modo de Alimentación Externa**: Se incorporó la función `set_external_feed_mode(True)` para desvincular el servidor FastAPI/Uvicorn de la cámara física cuando se ejecuta desde el Menú Universal.
- **Sincronización de Flujos**:
  - `update_remote_frame(frame)`: Envío de frames procesados al endpoint `/stream` (MJPEG).
  - `broadcast_translation_sync(word, confidence)`: Emisión de predicciones confirmadas hacia clientes conectados mediante WebSockets.
  - `start_server_background(host, port)`: Inicialización limpia del servidor web en un hilo secundario asíncrono.

---

### 3. Modularización de la Captura de Datos (`inicio/gui_captura.py`)
- **Soporte para Embebido**: Se agregaron los parámetros `parent_frame` y `camera_id` en `CaptureGUI`, permitiendo ejecutar la interfaz como componente interno del Menú Universal o de forma independiente (`standalone`).
- **Limpieza de Recursos**: Se implementó el método `cleanup()` para detener el hilo de captura y liberar la cámara al alternar de módulo o cerrar la ventana.

---

### 4. Corrección de Errores (Bug Fixes)
- **Corrección de Inicialización de Traducción**:
  - Se resolvió la excepción `NameError: name 'realtime_translator' is not defined` en `inicio/menu_universal.py` mediante la importación explícita del módulo `realtime_translator`.
- **Limpieza de Widgets**:
  - Se eliminó la llamada duplicada `btn_copy.pack(pady=(4, 0))` en la ventana modal del Visor Web.

---

### 5. Profesionalización Visual y Eliminación de Emojis
- **Estandarización de Interfaz**: Se removieron todos los emojis decorativos en las vistas de la aplicación de escritorio (`inicio/menu_universal.py`, `inicio/gui_captura.py`) y en los registros de consola, adoptando indicadores textuales claros (`[OK]`, `[Aviso]`, `->`, `*`).
- **Interfaz Web (`login.html`)**: Se reemplazaron los emojis por iconos vectoriales SVG limpios para el isotipo y el indicador de seguridad de red local.

---

### 6. Actualización de Instaladores y Atajos del Sistema
- **Scripts de Instalación (`install.sh` y `install.ps1`)**:
  - Se añadió la creación del comando unificado `handtalk` en `create_cli_shortcuts()` para Linux y `handtalk.bat` para Windows.
  - Se integró la generación del lanzador de escritorio (`handtalk.desktop` / acceso directo).
  - Se actualizaron las funciones de desinstalación limpia (`remove_cli_shortcuts()`) y los resúmenes finales de instalación.
- **Configuración Local**:
  - Se generó el binario ejecutable `/home/nokia/.local/bin/handtalk`.
  - Se creó el archivo de escritorio `~/.local/share/applications/handtalk.desktop`.

---

### 7. Documentación
- **`README.md`**: Actualizado para documentar el comando principal `handtalk`, la arquitectura unificada y los atajos disponibles.
- **`STATUS.md`**: Se registró la culminación de la fase de integración del Menú Universal.