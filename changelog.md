# Changelog - HandTalk

Registro cronológico y técnico de cambios, mejoras y correcciones aplicadas a la plataforma HandTalk.

---

## [2026-09-17] - Cámara Virtual Interna, Estandarización 16:9 HD y Zona Segura para Videollamadas

### 1. Módulo de Cámara Virtual Desacoplada (`inicio/virtual_cam.py`)
- **Arquitectura Asíncrona No Bloqueante**: Se implementó la clase `VirtualCamManager` con un hilo en segundo plano (`HandTalk-VirtualCamWorker`) y buffer atómico protegido por cerrojo (`threading.Lock`), desacoplando el despacho de video de la inferencia de MediaPipe para evitar pérdidas de FPS.
- **Estandarización a 16:9 HD (1280×720 a 30 FPS)**: Se configuró la resolución nativa de transmisión en formato panorámico estándar, alineada con la captura de `camera_utils.py` y las plataformas de videoconferencia (Microsoft Teams, Google Meet, Zoom).
- **Recorte Central Inteligente (`_fit_frame_to_target`)**: Escalado adaptativo que preserva la relación de aspecto 16:9 sin deformar la anatomía de las manos o el rostro cuando la cámara física entrega formatos distintos (ej. 4:3 640×480).
- **Zona Segura para Videollamadas (*Safe Area*)**:
  - Se implementó un margen de seguridad inferior de ~95 píxeles (`safe_margin_bottom = max(85, int(h * 0.13))`), resolviendo el problema de recorte y ocultamiento provocado por la barra de participantes y controles de Microsoft Teams y Google Meet.
  - Se añadió la opción de ubicación `banner_position='top'` para situar los subtítulos en la parte superior flotante.
- **Rediseño del Banner de Confirmación**:
  - Incorporación de un badge de estado superior en verde esmeralda brillante (`✓ CONFIRMADO (XX%)`) con porcentaje de certeza del modelo.
  - Palabra confirmada en tipografía de alto contraste (blanco con sombra negra) sobre panel translúcido oscuro con borde acento morado/cian.
  - Temporizador de persistencia de 3.8 segundos con atenuación progresiva (*fade-out*) en los últimos 0.7 segundos.
- **Compensación de Espejo (*Mirror Flip*)**: Soporte configurable para invertir el cuadro antes del subtitulado, evitando que el usuario vea su propio texto invertido en aplicaciones con vista previa reflejada.
- **Tolerancia a Fallos (*Graceful Degradation*)**: Manejo de excepciones ante ausencia de drivers o librerías externas, permitiendo que HandTalk continúe funcionando normalmente en modo local y visor web sin colapsar.

---

### 2. Contrato de Eventos Desacoplado (`inicio/realtime_translator.py`)
- **Soporte Formal de Callbacks**: Se incorporaron los métodos `register_callback(callback)` y `unregister_callback(callback)` según la especificación de `EVENTOS.md`.
- **Emisión en Tiempo Real**: Notificación automática con firma `(word, confidence, timestamp)` a todos los módulos suscriptores (Cámara Virtual, WebSockets, TTS) al confirmar una seña.

---

### 3. Integración en el Menú Universal (`inicio/menu_universal.py`)
- **Controles de Cámara Virtual en Pestaña 4 ("Traducir y Visor")**:
  - Switch de activación/desactivación de la Cámara Virtual con gestión de ciclo de vida completo (`start`, `stop`, `on_translation_confirmed`).
  - Checkbox **"Espejo Zoom"**: Compensación de reflejo horizontal.
  - Checkbox **"Video Limpio (Sin Puntos)"**: Permite ocultar el esqueleto óseo de MediaPipe en reuniones formales y transmitir únicamente la imagen con subtítulos.
  - Checkbox **"Subtítulos Arriba"**: Alterna la posición del banner a la zona superior.
- **Liberación de Recursos**: Detención segura del dispositivo virtual al pausar la traducción o al cerrar la aplicación (`on_close_window`).

---

### 4. Automatización de Drivers en Autoinstaladores
- **GNU/Linux (`install.sh`)**:
  - Detección e instalación automática de cabeceras del kernel (`linux-headers-$(uname -r)` / `kernel-devel`) y paquetes `v4l2loopback-dkms` y `v4l2loopback-utils` para Debian/Ubuntu, Arch y Fedora.
  - Configuración persistente del módulo en `/etc/modprobe.d/v4l2loopback.conf` con `devices=1 video_nr=10 card_label="HandTalk Virtual Cam" exclusive_caps=1` (parámetro indispensable para reconocimiento en navegadores y Zoom).
  - Configuración de carga al inicio en `/etc/modules-load.d/v4l2loopback.conf`.
  - Inclusión automática del usuario en el grupo de sistema `video`.
  - Carga en caliente del módulo para uso inmediato sin reiniciar y validación de `/dev/video10`.
- **Windows (`install.ps1`)**:
  - Perfeccionamiento de la función `Test-VirtualCamDriver` para auditar el Registro DirectShow y DLLs de OBS Virtual Camera y Unity Capture.
  - Recomendación y comando asistido para aprovisionamiento desatendido vía `winget install --id OBSProject.OBSStudio --silent`.

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