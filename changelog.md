# Changelog — Traductor de señas personalizado

Fecha: 2026-09-28

Este changelog cubre dos archivos:

1. `realtime_translator.py`: versión **actual** comparada con la **anterior**.
2. `gui_captura.py`: cambios de esta sesión (captura dinámica con una sola mano).

---

## 1. `realtime_translator.py`

### Resumen

La versión anterior clasificaba casi todo por frame con el modelo estático, usaba un solo smoother compartido y detectaba movimiento con un umbral simple sobre la muñeca. La versión actual añade **filtros de precisión** para reducir falsos positivos:

- Clasificación estática solo con la mano quieta.
- Filtro por score de MediaPipe y conteo de manos estable.
- Zona muerta de movimiento para ignorar temblores.
- Un pipeline dinámico separado y más robusto.

La decisión de clase es directa: el modelo elige la clase más probable, sin correcciones externas.

### Nuevo

#### Estático más estricto

- **Solo clasifica con la mano quieta**: `STATIC_STILL_FRAMES = 4`. Evita leer poses "de paso" al levantar la mano.
- **Filtro de score de MediaPipe** (`HAND_SCORE_MIN = 0.40`): se descartan frames donde el tracker no está seguro de la mano.
- **Conteo de manos estable**: hay que sostener el mismo número de manos `HAND_COUNT_STABLE_FRAMES = 4` frames antes de cambiar entre modelo de 1 y 2 manos.
- **Orden estable de manos**: se ordenan por la x de la muñeca (izquierda → derecha).
- **Un smoother por modelo** (`"1h"` y `"2h"`). Al cambiar de modelo se resetea el otro para que los votos no se mezclen.
- **Etiquetas ignoradas** (`reposo`, `neutral`, `neutro`, `ninguna`, `nada`, `none`, `idle`): no se emiten y limpian los votos.
- **Verificación de dimensiones del modelo de 2 manos** (`n_features_in_`): si no coincide con las features generadas, avisa una sola vez y cae al modelo de 1 mano.

#### Movimiento con zona muerta

- Movimiento medido sobre el **centro de todas las muñecas visibles**, suavizado con EMA.
- **Zona muerta** `MOV_NOISE_FLOOR = 0.008`: los micro-temblores no cuentan. El EMA solo acumula el exceso sobre ese piso y decae rápido cuando no hay movimiento real.
- Si **cambia el número de manos** (entra o sale una), el salto artificial del centro no cuenta como movimiento.
- **Racha de movimiento**: la grabación dinámica solo arranca con `MOV_FRAMES_TO_START = 3` frames consecutivos de movimiento real.

#### Pipeline dinámico rehecho

- Separado en métodos (`_actualizar_dinamico`, `_confirmar_dinamico`, `_clasificar_secuencia`, `_emitir_dinamico`, `_reset_dinamico`).
- **Sin smoother**: confirmación directa con `DYN_CONF_MIN = 0.80`.
- **Secuencias mínimas**: menos de `MIN_DYN_FRAMES = 8` frames se descartan como ruido.
- **Tolerancia a pérdida de mano** (`LOST_FRAMES_TO_FINALIZE = 4`): si la mano sale de cámara mientras se graba, se espera unos frames por el parpadeo del tracker y luego se clasifica. Antes se descartaba todo.
- **Confirmación temprana** (`EARLY_CONFIRM`): puede confirmar la palabra mientras haces el gesto si el modelo es muy seguro (`EARLY_CONF_MIN = 0.90`) y coincide en `EARLY_HITS_REQUIRED = 2` evaluaciones consecutivas. **Está en `False` por defecto**.
- **Cooldowns** para que el estático no "adivine" tras un gesto:
  - `POST_DYN_COOLDOWN_OK = 18` frames tras dinámica confirmada.
  - `POST_DYN_COOLDOWN_FAIL = 8` frames tras dinámica fallida.
  - `STATIC_COOLDOWN = 12` frames tras detectar movimiento en modo auto.
- `MAX_DYN_SECONDS = 4.0` ahora es un parámetro (antes estaba fijo en el código).

#### Interfaz y depuración

- Nuevos argumentos de línea de comandos:
  - `--mode {auto,estatico,dinamico}`. Antes `main()` no pasaba el modo, así que siempre corría en `auto`.
  - `--debug`: imprime en consola las evaluaciones de la confirmación temprana.
- Overlay:
  - Línea inferior con número de manos, modelo en uso y `mov` con su umbral.
  - Contador de frames en "Capturando movimiento...".
- Al iniciar imprime si se cargó el modelo dinámico o el de dos manos.

### Cambiado

| Parámetro / comportamiento | Anterior | Actual |
|---|---|---|
| `MOV_THRESHOLD` | 0.05 (distancia cruda por frame) | 0.012 (sobre movimiento suavizado con zona muerta) |
| `FRAMES_QUIETO_PARA_FINALIZAR` | 10 | 5 |
| `confirmed_persistence` | 30 frames | 15 frames |
| Confianza al terminar gesto dinámico | Smoother (umbral 0.60 en modo dinámico) | `DYN_CONF_MIN = 0.80`, sin smoother |
| Modo `auto` con movimiento | Clasificaba estático en cada frame mientras había movimiento | Silencia el estático mientras hay movimiento, grabación o cooldown |
| Dos manos | Ramal aparte, antes de revisar el modo; usaba el smoother compartido | Solo en el flujo estático, respeta `--mode` y usa su propio smoother |
| Movimiento | Solo la muñeca de la primera mano | Centro de todas las muñecas, con EMA |
| Mano sale de cámara mientras graba | Se descartaba la grabación | Espera `LOST_FRAMES_TO_FINALIZE` frames y luego clasifica |
| Confianza mostrada de la palabra persistente | La del frame actual | La confianza con la que se confirmó |
| Archivos `meta` (`.json`) de modelos dinámico / 2 manos | Obligatorios si existía el modelo (fallaba si faltaban) | Opcionales |

### Retirado: reglas de dedos

Durante esta sesión se probó una capa de **reglas de dedos** (corregir la clase del modelo según qué dedos estaban extendidos o doblados). Se **quitó** porque solo había reglas para 2 palabras y no compensaba la complejidad. Se eliminó:

- `REGLAS_DEDOS`, la lectura opcional de `models/sign_rules.json` y el aviso de reglas sin clase.
- La medición del estado de cada dedo y el consenso de dedos para gestos dinámicos.
- El decodificador restringido (revisaba las 5 clases más probables). Ahora se usa `_decodificar`: clase más probable del modelo.
- Los parámetros `EXT_RATIO`, `CURL_RATIO` y `MIN_PROB_CORREGIDA`.
- En el overlay con `--debug`: el estado de los dedos y el texto "Corregido por reglas".

`models/sign_rules.json` ya no se lee. Si existe, se ignora.

### Ojo (pendientes y advertencias)

- `MOV_FRAMES_TO_STOP = 3` está declarado pero **no se usa** en el código actual. La parada del gesto se controla con `FRAMES_QUIETO_PARA_FINALIZAR`.
- Sin las reglas, si el modelo confunde dos señas parecidas no hay nada que lo corrija. La mejora estaría en el entrenamiento (más muestras, señas más distintas) o en ajustar `DYN_CONF_MIN` y el smoother.
- En dinámico con 2 manos en cámara, el traductor usa la mano **más a la izquierda** (orden por x), mientras que `gui_captura.py` captura con la primera mano que entrega MediaPipe. Con una sola mano en cámara coinciden, y la captura ahora bloquea el caso de 2 manos, así que el dataset dinámico queda consistente.

---

## 2. `gui_captura.py`

### Nuevo

- **Captura dinámica con una sola mano**: cada frame de la secuencia usa `build_feature_vector` con la primera mano detectada. Todos los vectores de la secuencia tienen el mismo tamaño y el modelo dinámico se entrena con datos homogéneos.
- **Aviso de 2 manos en dinámico**:
  - Antes de empezar: si ya hay 2 manos en cámara, muestra el aviso y no inicia la captura.
  - Durante la captura: si aparece una segunda mano, se cancela la secuencia completa (no se guarda nada) y se muestra el aviso. Se usa la excepción `TwoHandsDetected`.
- **Aviso visual en el video**: texto rojo "Modo dinamico: usa SOLO UNA mano" mientras haya 2 manos en modo dinámico.
- **Etiqueta** del radiobutton: "Dinámica (1 mano)".
- **Guard de cámara**: si se pulsa guardar sin cámara abierta, avisa "Abre la cámara primero" en lugar de fallar.

### Corregido

- **Hilos**: la captura dinámica leía la cámara y llamaba a `hands.process` desde un hilo aparte, a la vez que el hilo de video. Ahora solo `capture_loop` toca MediaPipe. Guarda el último resultado en `last_results` (protegido con `frame_lock`) y el worker de captura lo lee de ahí.
  - Efecto secundario: si la cámara va a menos de ~33 fps, la secuencia puede repetir algún frame.
- **`NameError` en el mensaje de error**: el `lambda` del `except Exception as e` usaba `e` después de que Python la elimina al salir del bloque. Ahora se guarda `msg = str(e)` antes.
- **Modo leído desde otro hilo**: el modo se copia a `self._mode` (variable normal) con un `trace` sobre el `StringVar`, para no leer Tkinter desde el hilo de la cámara.

### Sin cambios

- Modo estático: sigue soportando 1 o 2 manos.
- Trigger por puño cerrado, temporizador de 5 s, lista de palabras y contador de muestras.

---

## 3. Referencia de parámetros de configuración

Todos los valores son los de la versión actual. Los "ajustables" están en `CustomSignTranslator.__init__` bajo el bloque `PARÁMETROS AJUSTABLES`. Las duraciones en segundos son aproximadas y suponen ~30 fps.

### 3.1 `realtime_translator.py`: argumentos de línea de comandos

| Argumento | Por defecto | Qué hace |
|---|---|---|
| `--camera` | `None` | Índice de la cámara. Con `None`, `camera_utils.open_camera` elige una disponible. |
| `--models-dir` | `./models` | Carpeta con los modelos (`.pkl`), etiquetas y metadatos (`.json`). |
| `--mode` | `auto` | `auto`: híbrido estático + dinámico. `estatico`: ignora todo lo dinámico. `dinamico`: ignora las predicciones estáticas. |
| `--debug` | apagado | Imprime en consola las evaluaciones de la confirmación temprana (`[DIN-temprano]`). Solo tiene efecto si `EARLY_CONFIRM` está activo. |

### 3.2 `realtime_translator.py`: argumentos del constructor

| Parámetro | Por defecto | Qué hace |
|---|---|---|
| `models_dir` | `./models` | Carpeta de modelos (igual que `--models-dir`). |
| `max_hands` | `2` | Máximo de manos que detecta MediaPipe. Con `1` nunca se usará el modelo de 2 manos. |
| `rotate_invariant` | `True` | Se pasa a `hand_features` para que las features no dependan de la rotación de la mano. Debe coincidir con cómo se entrenó el modelo. |
| `confidence_threshold` | `0.75` | Umbral de confianza de los `PredictionSmoother` (uno por modelo estático). La lógica de votación está en `smoothing.py`. |
| `mode` | `auto` | Igual que `--mode`. |
| `debug` | `False` | Igual que `--debug`. |

### 3.3 `realtime_translator.py`: MediaPipe

| Parámetro | Valor | Qué hace |
|---|---|---|
| `min_detection_confidence` | `0.70` | Confianza mínima para detectar una mano nueva. Más alto = menos manos fantasma, pero más frames sin detección. |
| `min_tracking_confidence` | `0.60` | Confianza mínima para seguir una mano ya detectada. Más bajo = el tracker la mantiene más tiempo; más alto = la vuelve a detectar más seguido. |
| `static_image_mode` | `False` | Modo video con tracking (fijo, no configurable). |

### 3.4 Movimiento

| Parámetro | Valor | Qué hace | Cuándo ajustarlo |
|---|---|---|---|
| `MOV_THRESHOLD` | `0.012` | Umbral sobre el movimiento suavizado (EMA, después de la zona muerta) para considerar que hay movimiento. En régimen estable equivale a un desplazamiento de ~0.02 por frame (`0.012 + 0.008`). También define "quieto" para el estático: `mov < MOV_THRESHOLD × 0.6`. | Si las dinámicas no se activan, **bájalo**. Si se activan solas con la mano quieta, **súbelo**. |
| `MOV_NOISE_FLOOR` | `0.008` | Zona muerta: desplazamientos por frame menores a esto se tratan como temblor y no cuentan. | Súbelo si con la mano "quieta" igual se activa el modo dinámico. |
| `MOV_FRAMES_TO_START` | `3` | Frames consecutivos con movimiento real antes de arrancar la grabación dinámica (~0.1 s). | Súbelo si la mano entrando en cámara dispara gestos falsos. Bájalo si se pierde el inicio de gestos rápidos. |
| `MOV_FRAMES_TO_STOP` | `3` | **Declarado pero no se usa** en el código actual. La parada la controla `FRAMES_QUIETO_PARA_FINALIZAR`. | No tiene efecto. |

Valores fijos en el código, no expuestos como parámetro:

- El EMA pondera `0.6 × valor anterior + 0.4 × movimiento efectivo`. Cuando no hay movimiento decae ×0.6 por frame.
- El movimiento se calcula sobre el centro de todas las muñecas visibles. Si cambia el número de manos, el EMA y la racha se reinician.

### 3.5 Estático

| Parámetro | Valor | Qué hace | Cuándo ajustarlo |
|---|---|---|---|
| `STATIC_STILL_FRAMES` | `4` | Frames quietos seguidos antes de clasificar una seña estática. | Súbelo si lee poses de paso. Bájalo si tarda demasiado en reaccionar. |
| `HAND_SCORE_MIN` | `0.40` | Score mínimo de MediaPipe por mano para clasificar estático. | Súbelo si clasifica manos mal detectadas. |
| `HAND_COUNT_STABLE_FRAMES` | `4` | Frames con el mismo número de manos antes de cambiar entre modelo de 1 y de 2 manos. | Súbelo si el modelo salta entre 1h y 2h por parpadeos del tracker. |
| `STATIC_COOLDOWN` | `12` | Frames sin clasificar estático tras detectar movimiento (solo modo `auto`). | Súbelo si el estático "adivina" justo después de un gesto. |
| `IGNORE_LABELS` | `reposo, neutral, neutro, ninguna, nada, none, idle` | Clases que se reconocen pero nunca se emiten. Sirven para entrenar una clase de "no seña". Vale también para el modelo dinámico. | Añade los nombres de tus clases de reposo. |

### 3.6 Dinámico

| Parámetro | Valor | Qué hace | Cuándo ajustarlo |
|---|---|---|---|
| `FRAMES_QUIETO_PARA_FINALIZAR` | `5` | Frames quietos seguidos para dar por terminado el gesto (~0.17 s). | Súbelo si el gesto se corta a la mitad. Bájalo si tarda en responder al terminar. |
| `MIN_DYN_FRAMES` | `8` | Secuencias con menos frames se descartan como ruido. | Bájalo solo si tus gestos son muy cortos. |
| `DYN_CONF_MIN` | `0.80` | Confianza mínima para confirmar un gesto al terminar. | Bájalo si casi nunca confirma. Súbelo si confirma gestos equivocados. |
| `MAX_DYN_SECONDS` | `4.0` | Duración máxima de una grabación antes de descartarla (evita bloqueos). | Súbelo para gestos largos. |
| `LOST_FRAMES_TO_FINALIZE` | `4` | Frames sin mano antes de cerrar el gesto. Cubre el parpadeo del tracker en gestos rápidos. | Súbelo si los gestos rápidos se cortan al perder la mano un instante. |
| `POST_DYN_COOLDOWN_OK` | `18` | Frames sin estático tras una dinámica confirmada. | Súbelo si tras un gesto el estático emite una palabra sobrante. |
| `POST_DYN_COOLDOWN_FAIL` | `8` | Frames sin estático tras una dinámica descartada. | Igual que el anterior. |
| `confirmed_persistence` | `15` | Frames que la palabra confirmada se mantiene en pantalla (~0.5 s). | Súbelo si desaparece demasiado rápido. |

Valor fijo en el código: el buffer del gesto guarda como máximo **60** frames (si se pasa, se descartan los más viejos).

### 3.7 Confirmación temprana (dinámico)

Confirma la palabra **mientras haces el gesto**, sin esperar a que pares.

| Parámetro | Valor | Qué hace |
|---|---|---|
| `EARLY_CONFIRM` | `False` | Interruptor general. **Desactivada por defecto.** Con `False` solo se confirma al terminar el gesto. |
| `EARLY_MIN_FRAMES` | `12` | Frames mínimos grabados antes de evaluar por primera vez. |
| `EARLY_EVAL_EVERY` | `3` | Se evalúa cada N frames de movimiento. |
| `EARLY_CONF_MIN` | `0.90` | Confianza mínima de cada evaluación. Es más exigente que `DYN_CONF_MIN` a propósito, para evitar disparos falsos. |
| `EARLY_HITS_REQUIRED` | `2` | Evaluaciones consecutivas que deben dar la misma clase para confirmar. |

### 3.8 Archivos que lee el traductor (dentro de `models_dir`)

| Archivo | Obligatorio | Uso |
|---|---|---|
| `custom_sign_model.pkl`, `custom_sign_labels.pkl`, `custom_sign_meta.json` | Sí | Modelo estático de 1 mano. |
| `custom_sign_model_dinamico.pkl`, `custom_sign_labels_dinamico.pkl` (+ `custom_sign_meta_dinamico.json`) | No | Modelo dinámico. El `.json` es opcional. |
| `custom_sign_model_two_hands.pkl`, `custom_sign_labels_two_hands.pkl` (+ `custom_sign_meta_two_hands.json`) | No | Modelo estático de 2 manos. El `.json` es opcional. |

### 3.9 `gui_captura.py`

| Parámetro | Valor | Qué hace | Dónde |
|---|---|---|---|
| `max_num_hands` | `2` | MediaPipe detecta hasta 2 manos. Se necesita en 2 para poder capturar estático de 2 manos y avisar en dinámico. | `Hands(...)` |
| `min_detection_confidence` | `0.7` | Confianza mínima para detectar una mano. | `Hands(...)` |
| `min_tracking_confidence` | `0.5` | Confianza mínima para seguirla. | `Hands(...)` |
| `TRIGGER_THRESHOLD` | `15` | Frames con el puño cerrado para activar la captura autónoma (~0.5 s). | `__init__` |
| Umbral de puño cerrado | `0.15` | Un puño está cerrado si las puntas de índice, medio, anular y meñique (landmarks 8, 12, 16, 20) están a menos de 0.15 de la muñeca (distancia 2D normalizada). Fijo en el código. | `_check_trigger_gesture` |
| Cuenta regresiva autónoma | `3 s` | Tiempo entre el puño cerrado y el guardado. | `start_autonomous_countdown` |
| Temporizador | `5 s` | Cuenta regresiva del botón "Temporizador (5s)". | `start_timer_capture` |
| `num_frames` (dinámico) | `20` | Frames por secuencia dinámica. | `capture_worker` |
| `time.sleep(0.03)` (dinámico) | `0.03 s` | Espera entre frames de la secuencia (~0.6 s en total). | `capture_worker` |
| Refresco de video | `15 ms` | Intervalo con que se actualiza la imagen en la ventana. | `update_video` |
| Ventana | `1100x700` | Tamaño de la ventana en modo independiente. | `__init__` |

### 3.10 Guía rápida: síntoma → ajuste

| Síntoma | Ajuste sugerido |
|---|---|
| El modo dinámico se activa con la mano quieta | Subir `MOV_NOISE_FLOOR` o `MOV_THRESHOLD`; subir `MOV_FRAMES_TO_START` |
| Los gestos dinámicos no se detectan | Bajar `MOV_THRESHOLD`; bajar `MOV_FRAMES_TO_START` |
| El gesto se corta a la mitad | Subir `FRAMES_QUIETO_PARA_FINALIZAR` y `LOST_FRAMES_TO_FINALIZE` |
| Confirma gestos equivocados | Subir `DYN_CONF_MIN` |
| Casi nunca confirma un gesto | Bajar `DYN_CONF_MIN`; capturar más muestras de esa seña |
| El estático lee poses de paso | Subir `STATIC_STILL_FRAMES` y `STATIC_COOLDOWN` |
| Salta entre modelo de 1 y 2 manos | Subir `HAND_COUNT_STABLE_FRAMES` |
| La palabra desaparece muy rápido | Subir `confirmed_persistence` |

### 4 `menu_universal.py`

### Cambiado

#### 1. `init_tab_traducir`: contenedor de tamaño fijo

Se agregó `pack_propagate(False)` a `video_display_frame` para que el contenedor no cambie de tamaño según la imagen.

```python
# Área de Video Central
self.video_display_frame = tk.Frame(frame, bg="#2D3436")
self.video_display_frame.pack(fill=tk.BOTH, expand=True)
self.video_display_frame.pack_propagate(False)   # <-- nuevo

self.translator_video_label = tk.Label(
    self.video_display_frame,
    text="Presione 'Iniciar Traducción en Vivo' para abrir la cámara",
    font=("Segoe UI", 14),
    bg="#2D3436",
    fg="#DFE6E9"
)
self.translator_video_label.pack(fill=tk.BOTH, expand=True)
```

#### 2. `_update_translation_ui_frame`: escalado al encuadre

Ahora cada frame se escala al espacio disponible manteniendo la proporción (modo "contain"). Usa `INTER_AREA` al reducir e `INTER_LINEAR` al ampliar. El refresco pasó de 16 ms a 33 ms (~30 FPS), porque la cámara no entrega más de eso.

```python
def _update_translation_ui_frame(self):
    if not self.is_translating:
        return

    with self.translation_lock:
        frame = self.latest_translator_frame.copy() if self.latest_translator_frame is not None else None

    if frame is not None:
        box_w = self.video_display_frame.winfo_width()
        box_h = self.video_display_frame.winfo_height()

        if box_w > 10 and box_h > 10:
            h, w = frame.shape[:2]
            scale = min(box_w / w, box_h / h)          # "contain": cabe completo, sin deformar
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            if (new_w, new_h) != (w, h):
                interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                frame = cv2.resize(frame, (new_w, new_h), interpolation=interp)

        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        imgtk = ImageTk.PhotoImage(image=img)
        self.translator_video_label.imgtk = imgtk
        self.translator_video_label.config(image=imgtk, text="")

    self.root.after(33, self._update_translation_ui_frame)   # ~30 FPS
```