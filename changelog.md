# Changelog — HandTalk

Todos los cambios notables del proyecto se documentan en este archivo.
Formato inspirado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

> **Nota sobre las fuentes de este changelog:** las entradas marcadas
> **(verificado)** salen directamente del trabajo hecho en esta sesión —
> archivos y librerías exactas, ya probadas. Las entradas marcadas
> **(según STATUS.md)** son un resumen de lo que reportó el resto del
> equipo en `STATUS.md`; no tengo el código de esos archivos a la vista,
> así que la descripción de QUÉ hace cada cambio es un resumen, no una
> lectura línea por línea — pero las librerías y versiones de la tabla
> final ya están confirmadas contra el `requirements.txt` real del repo.

---

## [Fase 3] — 2026-09-25/26 — Integración final y mejoras avanzadas

### Added
- `inicio/menu_universal.py` — menú centralizado que integra Bienvenida, Captura, Entrenamiento, Paquetes y Traducción. *(según STATUS.md)*
- `inicio/pack_manager.py` — exportación/importación de datasets y modelos como `.zip`, con resolución de conflictos. *(según STATUS.md)*
- `inicio/temporal_pooling.py` — segmentación de movimiento y *temporal pooling* para reconocer señas dinámicas. *(según STATUS.md)*
- `inicio/tts_output.py` — módulo de salida de voz (TTS), suscrito al evento `on_translation_confirmed` vía `register_callback()`. **(verificado)**
  - Librería: `pyttsx3` (offline, motor por defecto).
  - Librería opcional: `edge-tts` + `playsound` (motor alternativo online, mejor calidad de voz).
  - Activar/desactivar en caliente con la tecla **T**, o `--tts` / `--tts-engine` / `--tts-rate` por línea de comandos.
  - Habla en un hilo de fondo con cola (`queue.Queue` + `threading.Thread`) para no bloquear el video; incluye *cooldown* de 2.5s para no repetir la misma palabra en bucle mientras la seña se mantiene quieta.
- `inicio/sketch_generator.py` — generador de bocetos (puntos y líneas) de cada seña a partir del dataset normalizado, más rotación manual persistente por palabra (`sketches/_rotations.json`). **(verificado)**
  - Librería: `Pillow` (`PIL.Image`, `PIL.ImageDraw`).
  - Soporta señas de una mano, dos manos, y señas dinámicas (usa el frame de en medio de la secuencia).
- `inicio/diccionario_gui.py` — pantalla de catálogo (Tkinter): cuadrícula con scroll, boceto + nombre + conteo de muestras por palabra, botón "Actualizar", botones ⟲/⟳ por palabra para ajustar la rotación. **(verificado)**
  - Librería: `tkinter` (incluida en Python, no requiere instalación) + `Pillow` (`ImageTk`) para mostrar los PNG generados.

### Changed
- `inicio/realtime_translator.py`: **(verificado)**
  - Se agregó el patrón publicador/suscriptor real: `register_callback()` / `unregister_callback()` / `_emit_confirmed()`, siguiendo el contrato de `EVENTOS.md`. Antes el evento `on_translation_confirmed` solo estaba especificado, no implementado — ahora cualquier módulo de salida (voz, visor web, cámara virtual) puede suscribirse.
  - Nuevos flags de CLI: `--print-events` (suscriptor de ejemplo que imprime en consola), `--tts`, `--tts-engine`, `--tts-rate`.
  - `run_webcam()` ahora acepta un módulo `tts` opcional: dibuja su estado en pantalla y agrega la tecla **T** para activar/desactivarlo sin cerrar la app.
  - Payload del evento: `word` (str), `confidence` (float), `timestamp` (ISO 8601 UTC) — exactamente como define `EVENTOS.md`.
- `inicio/realtime_translator.py` — reemplazo del `demo_loop` del visor web por el pipeline de inferencia real integrado con el motor de traducción. *(según STATUS.md)*
- `inicio/realtime_translator.py` / `inicio/gui_captura.py` — soporte de señas dinámicas vía Temporal Pooling; solución al "parpadeo" de traducciones mediante histéresis de confirmación y ajuste de umbrales de movimiento. *(según STATUS.md)*
- `inicio/hand_features.py` — extracción de *features* polimórfica para soportar señas de una y dos manos. *(según STATUS.md)*
- `inicio/train_classifier.py` — entrenamiento dual (modelos estáticos y dinámicos simultáneos). *(según STATUS.md)*
- `inicio/dataset_manager.py` — funciones para renombrar y eliminar palabras del dataset, con aviso de re-entrenamiento en la UI. *(según STATUS.md)*
- `inicio/gui_captura.py` — captura autónoma y asistida: trigger por gesto (puño cerrado) y temporizador de cuenta regresiva (5s). *(según STATUS.md)*
- Servidor del visor web — sincronización total de credenciales (PIN/Token) entre backend y frontend. *(según STATUS.md)*

### Fixed
- `inicio/realtime_translator.py` — corregido el cierre forzado de la aplicación al cerrar la ventana con la "X". *(según STATUS.md)*
- `inicio/tts_output.py` — corregido un bug conocido de `pyttsx3` en Windows (driver SAPI5): reutilizar un solo motor (`engine`) para varias palabras se queda mudo después de la primera llamada a `runAndWait()`, sin lanzar ningún error. Ahora se crea un motor nuevo por cada palabra. **(verificado)**
- `inicio/sketch_generator.py` — corregido un bug de Pillow donde dedos muy doblados (ej. un puño cerrado) dejaban un hueco visible en el boceto incluso con `joint="curve"`; se resolvió extendiendo la base de cada dedo hacia adentro de la palma (solapamiento) en vez de líneas/polígonos ajustados exactamente al punto. **(verificado)**
- `inicio/train_classifier.py` — corregido error de dimensionalidad (`inhomogeneous shape`) al entrenar con datasets mixtos (estáticos + dinámicos). *(según STATUS.md)*

### Security
- Autenticación por PIN/QR, Rate Limiting (`slowapi`), sanitización contra XSS y cabeceras de seguridad (CSP) en el visor web. *(según STATUS.md)*

---

## [Fase 2] — Visor Web (finalizada)

### Added
- Servidor backend con **FastAPI** — streaming de video vía MJPEG. *(según STATUS.md)*
- Comunicación en tiempo real vía **WebSocket** para el envío de traducciones. *(según STATUS.md)*
- Detector de IP local + generador de código QR para acceso simplificado desde celular. *(según STATUS.md)*
- `visor.html` — frontend para visualización de video y subtítulos en dispositivos móviles. *(según STATUS.md)*
- Integración de **`pyvirtualcam`** — emite video con subtítulos hacia apps de videollamada (Zoom, Meet, Teams), con soporte multiplataforma y degradación suave si no hay cámara virtual disponible. *(según STATUS.md)*

### Changed
- `inicio/gui_captura.py` — arquitectura de hilos desacoplados para eliminar parpadeos en la captura de video. *(según STATUS.md)*

---

## [Fase 1] — MVP Base

### Added
- `EVENTOS.md` — contrato de interfaz para el evento `on_translation_confirmed` (payload: `word`, `confidence`, `timestamp`), patrón publicador/suscriptor. *(Francisco)*
- `inicio/gui_captura.py` — nueva interfaz de captura de señas conectada a `hand_features.build_feature_vector()`. *(Herber, trabajo conjunto con Francisco)*

### Validated
- Flujo completo Captura → Entrenamiento → Traducción, de punta a punta.

---

## [Infraestructura inicial]

### Added
- `requirements.txt` — versiones estables de **MediaPipe** (`==0.10.14`) y **OpenCV** (`opencv-python>=4.8.0`), más `scikit-learn`, `joblib` y `numpy` para el clasificador. *(según STATUS.md)*
- `README.md` — guía de instalación y uso.
- `install.sh` / `install.ps1` — instaladores automatizados con atajos de terminal.
- `.gitignore` — optimizado (excluye `custom_dataset/`, `models/`, entornos virtuales, etc.).

### Changed
- Limpieza de archivos obsoletos y datasets externos del proyecto.

---

## Librerías de terceros usadas en el proyecto (confirmado contra `requirements.txt`)

| Librería | Versión | Uso |
|---|---|---|
| `opencv-python` | >=4.8.0 | Captura y procesamiento de video |
| `mediapipe` | ==0.10.14 | Detección de landmarks de mano |
| `scikit-learn` | >=1.3.0 | Clasificador de landmarks (Random Forest / MLP) |
| `joblib` | >=1.3.0 | Guardar/cargar el modelo entrenado |
| `numpy` | >=1.24.0 | Cálculo numérico (features, normalización) |
| `Pillow` | >=10.0.0 | Bocetos (`sketch_generator.py`), miniaturas en Tkinter, y renderizado de QR |
| `fastapi` | >=0.110.0 | Servidor del visor web |
| `uvicorn[standard]` | >=0.28.0 | Servidor ASGI para correr FastAPI |
| `slowapi` | >=0.1.9 | Rate limiting del visor web |
| `qrcode[pil]` | >=7.4.2 | Generación del código QR de acceso |
| `pydantic` | >=2.6.0 | Validación de datos (modelos de FastAPI) |
| `pyvirtualcam` | >=0.11.0 | Cámara virtual para videollamadas |
| `pyttsx3` | >=2.90 | TTS offline (motor por defecto) |
| `edge-tts` | >=0.10.0 | TTS online alternativo (mejor calidad de voz) |
| `playsound` | ==1.2.2 | Reproduce el audio generado por `edge-tts` en `tts_output.py` |
| `tkinter` | — (incluida en Python) | GUI de captura y del diccionario |

### ✅ Resuelto: faltaba `playsound` en `requirements.txt`

`tts_output.py` usa `edge-tts` solo para **generar** el audio (guarda un `.mp3`
temporal); para **reproducirlo** llama a `from playsound import playsound`, y esa
librería no estaba en el `requirements.txt` original. Sin ella, elegir
`--tts-engine edge-tts` fallaba con `ImportError` al intentar reproducir el
audio (la generación en sí funcionaba bien). Ya se agregó `playsound==1.2.2`
al `requirements.txt` (versión fija a propósito: la 1.3.0 tiene errores de
instalación conocidos en Windows). Si el equipo solo usa el motor `pyttsx3`
(el que viene por defecto) no la necesita, pero no estorba tenerla.
