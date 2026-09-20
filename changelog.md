# 📑 (Changelog Detallado)


##  Funcionamiento Actual: El Enfoque Híbrido

Para integrar las señas dinámicas sin romper la funcionalidad anterior (main/estático), se implementó una arquitectura de **Coexistencia No Conflictiva**.

### ¿Cómo funciona ahora? (Sintesis)
El sistema opera bajo una lógica de **exclusión mutua** para garantizar que la alta precisión de las señas estáticas no se vea comprometida por el ruido del movimiento:

1. **Detección de Estado**: El sistema mide la velocidad de la muñeca.
2. **Si hay Movimiento $\rightarrow$ Modo Dinámico (Plus)**: 
   - Se activa un buffer temporal que graba la secuencia del gesto.
   - **Protección del Modelo Estático**: El modelo estático se **pausa** y se resetea su contador de confirmación. Esto evita que el sistema confirme erróneamente una seña fija mientras el usuario simplemente está moviendo la mano para hacer un gesto.
   - Al detenerse la mano, se resume la secuencia mediante **Pooling Temporal** y se predice el gesto.
3. **Si hay Quietud $\rightarrow$ Modo Estático (Prioritario)**: 
   - Se activa el modelo de posturas fijas, que es la herramienta más precisa del sistema.
   - Se utiliza el `PredictionSmoother` para asegurar que la seña sea estable antes de confirmarla.

**Resultado:** El trabajo anterior del `main` (estático) permanece intacto y se vuelve más robusto, ya que ahora tiene un "filtro" que le indica cuándo NO debe intentar predecir.

---

## 🚀 Optimización de Rendimiento en Movimiento

Uno de los mayores desafíos fue evitar que la tasa de frames (FPS) cayera drásticamente al activar el modelo dinámico. Se aplicaron tres estrategias de optimización:

### 1. Throttle de Inferencia Dinámica (`CADA_N_FRAMES_PREVIEW`)
Correr el modelo dinámico en cada frame es costoso. Para solucionar esto, el sistema implementó un "estrangulamiento" (throttle) de la predicción:
- **Lógica**: El sistema solo calcula la predicción del preview cada $N$ frames (por defecto cada 2).
- **Impacto**: Reduce a la mitad la carga computacional del modelo dinámico sin que el usuario note saltos en el texto de la pantalla.

### 2. Downscaling de Imagen
Para aliviar la carga de MediaPipe y el clasificador, se implementó la reducción de resolución antes del procesamiento:
- **Código**: `cv2.resize(frame, (int(w * scale), int(h * scale)))`.
- **Impacto**: Al procesar imágenes de 480px en lugar de 1080p o 720p, la latencia de inferencia disminuye drásticamente, manteniendo los FPS estables incluso durante el movimiento.

### 3. Buffer de Seguridad y Limpieza
Para evitar que el buffer dinámico crezca indefinidamente y consuma memoria o cause lentitud:
- **Lógica**: Si la mano queda quieta por un tiempo prolongado (`FRAMES_SIN_MOVIMIENTO_PARA_LIMPIAR`), el buffer se vacía automáticamente.
- **Impacto**: Asegura que cada nuevo gesto comience desde cero y que la memoria se libere rápidamente.



## Módulo de Captura (`gui_captura.py`)

#### A. Selector de tipo de seña

Se amplió la interfaz de captura para permitir seleccionar entre **señas estáticas y dinámicas** mediante nuevos `Radiobutton`.

```python
self.tipo_seleccionado = tk.StringVar(value="static")

ttk.Radiobutton(
    frame_tipo,
    text="Estática",
    variable=self.tipo_seleccionado,
    value="static",
    command=self._on_tipo_cambiado
)

ttk.Radiobutton(
    frame_tipo,
    text="Dinámica",
    variable=self.tipo_seleccionado,
    value="dynamic",
    command=self._on_tipo_cambiado
)
```

La selección determina el tipo de muestra que será almacenada en el dataset.

#### B. Configuración de secuencias dinámicas

Se agregó la posibilidad de configurar la cantidad de frames que conforman una muestra dinámica.

```python
VENTANA_DINAMICA_DEFAULT = 20

self.ventana_dinamica_var = tk.StringVar(
    value=str(VENTANA_DINAMICA_DEFAULT)
)
```

El campo **"Frames por secuencia"** solamente se muestra cuando está seleccionado el modo dinámico.

#### C. Captura de secuencias

A diferencia de las señas estáticas, donde se almacena un único vector de características, las señas dinámicas almacenan una secuencia completa:

```python
self.buffer_dinamico = []

if self.capturando_dinamica:
    if feature_vector is not None:
        self.buffer_dinamico.append(feature_vector)
```

Cuando el buffer alcanza la cantidad de frames configurada, la secuencia se guarda mediante:

```python
dataset_manager.save_sample(
    self.buffer_dinamico,
    self.current_word,
    sample_type="dynamic"
)
```

Esto permite que el mismo sistema de captura genere datasets compatibles tanto con el entrenamiento estático como con el entrenamiento dinámico.

#### D. Sincronización segura entre cámara e interfaz

Se implementó una `Queue` para comunicar el hilo de captura con el hilo principal de Tkinter:

```python
self.eventos_ui = queue.Queue()
```

El hilo de cámara envía eventos de progreso:

```python
self.eventos_ui.put(
    ("progreso", len(self.buffer_dinamico), objetivo)
)
```

Mientras que el hilo principal procesa estos eventos y actualiza los widgets de la interfaz.

Esta modificación evita que el hilo de captura manipule directamente elementos de Tkinter y reduce el riesgo de condiciones de carrera durante la captura.

#### E. Reutilización del frame procesado

La captura de muestras estáticas dejó de realizar una segunda llamada a `self.cap.read()`.

Ahora se reutiliza el último vector de características generado por el hilo de cámara:

```python
with self.frame_lock:
    feature_vector = self.ultimo_feature_vector
```

Esto evita que dos hilos intenten leer simultáneamente desde la misma cámara.

#### F. Manejo de frames sin detección de mano

Durante la captura dinámica, si MediaPipe no detecta la mano en un frame puntual, se reutiliza el último vector disponible:

```python
elif self.buffer_dinamico:
    self.buffer_dinamico.append(
        self.buffer_dinamico[-1]
    )
```

Esto permite mantener la longitud de la secuencia y evitar que un fallo puntual de detección invalide toda la muestra dinámica.


## Pipeline de Entrenamiento (`train_classifier.py`)

#### A. Incorporación del entrenamiento de señas dinámicas

El pipeline de entrenamiento fue ampliado para soportar un segundo modelo especializado en **señas dinámicas**, manteniendo separado el modelo utilizado para las señas estáticas.

Anteriormente, el entrenamiento estaba orientado únicamente a muestras estáticas. Ahora el sistema identifica automáticamente qué tipos de muestras existen en el dataset y decide qué modelos deben entrenarse.

```python
tipos_disponibles = dataset_manager.get_available_types(dataset_dir)

entrenar_estatico = (
    "static" in tipos_disponibles
    and not solo_dinamico
)

entrenar_dinamico = (
    "dynamic" in tipos_disponibles
    and not solo_estatico
)
```

Esto permite que una misma ejecución pueda generar:

```text
Modelo estático
    ↓
custom_sign_model.pkl

Modelo dinámico
    ↓
custom_sign_model_dinamico.pkl
```

Los dos modelos mantienen sus propios codificadores de etiquetas y metadatos.

---

#### B. Nuevo entrenamiento específico para secuencias dinámicas

Se agregó la función:

```python
def train_dynamic(
    dataset_dir,
    model_type="random_forest",
    augment_factor=20,
    test_size=0.2,
    models_dir=MODELS_DIR
):
```

Esta función carga exclusivamente las muestras almacenadas como `dynamic`:

```python
secuencias, etiquetas = dataset_manager.load_dataset(
    dataset_dir,
    sample_type="dynamic"
)
```

De esta manera, las secuencias dinámicas no se mezclan directamente con los vectores utilizados por el modelo estático.

---

#### C. Validación de clases dinámicas

Antes de iniciar el entrenamiento se comprueba que existan al menos dos señas dinámicas diferentes:

```python
palabras = sorted(set(etiquetas))

if len(palabras) < 2:
    print(
        "\n[AVISO] Se necesitan al menos 2 señas "
        "dinámicas distintas para entrenar."
    )
    return None, None
```

Esto evita intentar entrenar un clasificador multiclase con una única categoría.

---

#### D. Aplicación de Temporal Pooling

Las muestras dinámicas están compuestas por una secuencia de vectores de características. Para poder utilizar el mismo tipo de clasificadores clásicos que en el modelo estático, cada secuencia se transforma en un único vector mediante `pool_sequence()`.

```python
for secuencia, etiqueta in zip(secuencias, etiquetas):
    vector_pooled = pool_sequence(secuencia)

    X.append(vector_pooled)
    y_labels.append(etiqueta)
```

El proceso genera un descriptor temporal compuesto por:

```text
Promedio de la secuencia
        +
Desviación estándar
        +
Delta entre inicio y final
```

Conceptualmente:

$$
V_{pooled}
=
[
mean(S),
std(S),
v_{final}-v_{inicio}
]
$$

Esto permite conservar información relacionada con el movimiento sin necesidad de utilizar una red recurrente.

---

#### E. Aumentación de datos para muestras dinámicas

Después del `Temporal Pooling`, cada secuencia se convierte en un vector plano. Esto permite reutilizar la función de aumentación que ya existía para las muestras estáticas:

```python
for variante in dataset_manager.augment_static_sample(
    vector_pooled,
    augment_factor,
    noise_std=0.01,
    scale_range=0.05
):
    X.append(variante)
    y_labels.append(etiqueta)
```

Por lo tanto, una secuencia dinámica real puede producir múltiples variantes sintéticas para aumentar el conjunto de entrenamiento.

El enfoque evita duplicar la lógica de aumentación y permite compensar la menor cantidad de muestras reales que normalmente se obtienen al capturar secuencias dinámicas.

---

#### F. Conversión de las secuencias a matrices de entrenamiento

Después del pooling y la aumentación, los datos se convierten en una matriz NumPy:

```python
X = np.array(X, dtype=np.float32)
```

El resultado tiene la estructura:

```text
Secuencia dinámica
        ↓
Temporal Pooling
        ↓
Vector descriptor
        ↓
Aumentación
        ↓
Matriz X
        ↓
Clasificador
```

Las etiquetas son transformadas mediante `LabelEncoder`:

```python
encoder = LabelEncoder()
y = encoder.fit_transform(y_labels)
```

---

#### G. Entrenamiento con Random Forest o MLP

El modelo dinámico utiliza la misma fábrica de clasificadores que el modelo estático:

```python
clf = _crear_clasificador(model_type)
```

Por lo tanto, el usuario puede seleccionar entre:

```text
Random Forest
MLP
```

El modelo seleccionado se entrena sobre los vectores obtenidos mediante Temporal Pooling:

```python
clf.fit(X_train, y_train)
```

Esto permite mantener una arquitectura de entrenamiento relativamente ligera sin requerir una red neuronal especializada en procesamiento de secuencias.

---

#### H. Validación del modelo dinámico

El entrenamiento dinámico incorpora validación cruzada de 5 particiones:

```python
scores = cross_val_score(
    clf,
    X_train,
    y_train,
    cv=5
)

print(
    f"Precisión validación cruzada (5-fold): "
    f"{scores.mean()*100:.2f}% "
    f"(+/- {scores.std()*100:.2f}%)"
)
```

También se genera un reporte de clasificación sobre el conjunto de prueba:

```python
y_pred = clf.predict(X_test)

print(
    classification_report(
        y_test,
        y_pred,
        target_names=encoder.classes_
    )
)
```

Y se incorpora una matriz de confusión para analizar los errores entre las diferentes señas dinámicas:

```python
print("Matriz de confusión:")
print(confusion_matrix(y_test, y_pred))
```

---

#### I. Archivos independientes para el modelo dinámico

Para evitar sobrescribir los archivos utilizados por el modelo estático, el entrenamiento dinámico genera sus propios archivos:

```python
model_path = os.path.join(
    models_dir,
    "custom_sign_model_dinamico.pkl"
)

encoder_path = os.path.join(
    models_dir,
    "custom_sign_labels_dinamico.pkl"
)

meta_path = os.path.join(
    models_dir,
    "custom_sign_meta_dinamico.json"
)
```

La estructura resultante es:

```text
models/
├── custom_sign_model.pkl
├── custom_sign_labels.pkl
├── custom_sign_meta.json
│
├── custom_sign_model_dinamico.pkl
├── custom_sign_labels_dinamico.pkl
└── custom_sign_meta_dinamico.json
```

Esto permite que ambos modelos puedan cargarse simultáneamente durante la inferencia híbrida.

---

#### J. Metadatos específicos del modelo dinámico

El archivo JSON generado para el modelo dinámico registra información adicional sobre el procesamiento temporal:

```python
json.dump({
    "model_type": model_type,
    "feature_length": int(X.shape[1]),
    "words": list(encoder.classes_),
    "tipo": "dynamic",
    "pooling": "mean+std+delta",
}, f, ensure_ascii=False, indent=2)
```

El campo:

```text
"tipo": "dynamic"
```

identifica el modelo como clasificador de señas dinámicas, mientras que:

```text
"pooling": "mean+std+delta"
```

documenta el método utilizado para transformar las secuencias antes del entrenamiento.

---

#### K. Entrenamiento selectivo mediante argumentos

Se agregaron opciones para controlar qué modelos se entrenan desde la línea de comandos:

```python
parser.add_argument(
    "--solo-estatico",
    action="store_true",
    help="Entrena solo el modelo estático, aunque haya dinámicas"
)

parser.add_argument(
    "--solo-dinamico",
    action="store_true",
    help="Entrena solo el modelo dinámico, aunque haya estáticas"
)
```

Esto permite tres escenarios principales:

```text
Entrenamiento normal
        ↓
Detecta automáticamente static + dynamic
        ↓
Entrena los modelos disponibles
```

```text
--solo-estatico
        ↓
Ignora muestras dinámicas
        ↓
Entrena únicamente el modelo estático
```

```text
--solo-dinamico
        ↓
Ignora muestras estáticas
        ↓
Entrena únicamente el modelo dinámico
```

Ejemplos:

```bash
python train_classifier.py
```

Entrena automáticamente los modelos disponibles.

```bash
python train_classifier.py --solo-estatico
```

Entrena solamente el modelo estático.

```bash
python train_classifier.py --solo-dinamico
```

Entrena solamente el modelo dinámico.

---

#### L. Separación de los pipelines estático y dinámico

La modificación mantiene independientes los dos flujos de entrenamiento:

```text
                    DATASET
                       │
              ┌────────┴────────┐
              │                 │
           STATIC             DYNAMIC
              │                 │
      Vector individual    Secuencia de vectores
              │                 │
              │          Temporal Pooling
              │                 │
              │          Vector descriptor
              │                 │
              └────────┬────────┘
                       │
                Clasificadores
                       │
              ┌────────┴────────┐
              │                 │
        Modelo estático   Modelo dinámico
```

Esta separación evita mezclar vectores de distinta estructura y permite que cada modelo sea especializado para el tipo de seña que debe reconocer.

## Nuevo Módulo de Procesamiento Temporal (`temporal_pooling.py`)

Se incorporó un nuevo módulo encargado de transformar las secuencias de frames obtenidas durante la captura de una seña dinámica en un **vector de características de tamaño fijo**.

El objetivo principal es permitir que las señas dinámicas puedan utilizar los mismos tipos de clasificadores clásicos empleados para las señas estáticas, como `RandomForest` o `MLP`, sin requerir una arquitectura recurrente como LSTM o GRU.

---

#### A. Conversión de secuencias a vectores de tamaño fijo

Se agregó la función:

```python id="kq4z4j"
def pool_sequence(secuencia):
```

La función recibe una secuencia con la estructura:

```text
(n_frames, n_features)
```

donde cada fila representa las características de la mano detectadas en un frame.

Por ejemplo:

```text
Frame 1 → [f1, f2, f3, ...]
Frame 2 → [f1, f2, f3, ...]
Frame 3 → [f1, f2, f3, ...]
...
Frame N → [f1, f2, f3, ...]
```

La secuencia completa se transforma posteriormente en un único vector:

```text
Secuencia de frames
        ↓
Temporal Pooling
        ↓
Vector de tamaño fijo
```

---

#### B. Promedio temporal

La primera característica calculada corresponde al promedio de cada feature a través de todos los frames:

```python id="8klm3e"
promedio = secuencia.mean(axis=0)
```

Esto representa una aproximación de la **postura media** mantenida durante el gesto.

---

#### C. Desviación estándar temporal

La segunda característica corresponde a la desviación estándar:

```python id="0j9xzw"
desviacion = secuencia.std(axis=0)
```

Esta información permite representar cuánto varió cada característica durante la ejecución de la seña.

En otras palabras, aporta información sobre la **magnitud de la variación o movimiento** presente en la secuencia.

---

#### D. Dirección neta del movimiento

La tercera parte del descriptor se obtiene calculando la diferencia entre el último y el primer frame:

```python id="v0f9xk"
delta_inicio_fin = secuencia[-1] - secuencia[0]
```

Esto permite conservar información sobre el **cambio neto producido durante el gesto**, incluyendo la dirección de desplazamiento de las características entre el inicio y el final de la secuencia.

---

#### E. Construcción del vector descriptor

Los tres componentes se concatenan en un único vector:

```python id="a8h4qy"
return np.concatenate([
    promedio,
    desviacion,
    delta_inicio_fin
]).astype(np.float32)
```

Por lo tanto, el descriptor final puede representarse como:

$$
V_{pooled}
=
[
mean(S),
std(S),
v_{final}-v_{inicio}
]
$$

Si un frame contiene `N` características, el vector resultante contiene:

$$
3N
$$

características.

Ejemplo:

```text
Feature por frame: 63
            ↓
Promedio:       63
Desviación:     63
Delta:          63
            ↓
Vector final:  189 características
```

---

#### F. Validación de la estructura de entrada

Se agregó una validación para garantizar que la secuencia recibida tenga dos dimensiones:

```python id="d8f0ks"
if secuencia.ndim != 2:
    raise ValueError(
        f"Se esperaba una secuencia 2D "
        f"(frames, features), "
        f"se recibió forma {secuencia.shape}"
    )
```

Esto permite detectar errores en los datos antes de ejecutar los cálculos de pooling.

---

#### G. Compatibilidad con diferentes cantidades de frames

Una de las características importantes del módulo es que no requiere que todas las secuencias tengan exactamente la misma cantidad de frames.

La función calcula las estadísticas directamente sobre la dimensión temporal:

```text
Secuencia A → 15 frames
Secuencia B → 20 frames
Secuencia C → 27 frames
Secuencia D → 35 frames

        ↓

Todas pueden convertirse en

        ↓

Un vector de 3 × n_features
```

Esto simplifica el procesamiento de las señas dinámicas y evita tener que utilizar padding únicamente para igualar la duración de las secuencias.

---

#### H. Función auxiliar para calcular el tamaño del vector

Se agregó la función:

```python id="u9u4jd"
def longitud_vector_pooled(n_features_por_frame):
    return n_features_por_frame * 3
```

Esta función permite conocer de forma directa el tamaño esperado del descriptor generado por `pool_sequence()`.

Por ejemplo:

```python id="4w2c5s"
longitud_vector_pooled(63)
```

produce:

```text
189
```

Esta información resulta útil para documentar o validar el tamaño esperado de los vectores almacenados en los metadatos del modelo.

---

#### I. Uso compartido entre entrenamiento e inferencia

El módulo está diseñado para ser utilizado tanto durante el **entrenamiento** como durante la **predicción en tiempo real**.

El flujo es:

```text
                  SECUENCIA DINÁMICA
                         │
              ┌──────────┴──────────┐
              │                     │
        Entrenamiento           Inferencia
              │                     │
              └──────────┬──────────┘
                         │
                   pool_sequence()
                         │
                         ▼
                Vector pooled
                         │
                         ▼
                  Clasificador
```

Esto garantiza que el modelo reciba durante la inferencia el mismo tipo de representación que recibió durante el entrenamiento.

La misma función debe mantenerse compartida entre ambos procesos para evitar diferencias entre el formato utilizado para entrenar el modelo y el formato utilizado para realizar predicciones en tiempo real.

---

#### J. Nuevo archivo del sistema

Se incorpora:

```text id="3t1vfr"
temporal_pooling.py
```

Este módulo centraliza el procesamiento matemático de las secuencias dinámicas y evita colocar la lógica de pooling directamente dentro de `train_classifier.py` o `realtime_translator.py`.

La arquitectura resultante queda:

```text
gui_captura.py
      │
      │ captura secuencias
      ▼
dataset_manager.py
      │
      ▼
train_classifier.py
      │
      ├── static → modelo estático
      │
      └── dynamic
             │
             ▼
      temporal_pooling.py
             │
             ▼
      vector mean + std + delta
             │
             ▼
      modelo dinámico
```

Durante la inferencia se reutiliza el mismo módulo:

```text
realtime_translator.py
          │
          │ secuencia dinámica
          ▼
temporal_pooling.py
          │
          ▼
vector pooled
          │
          ▼
modelo dinámico
```
## `realtime_translator.py` — Incorporación del reconocimiento dinámico

Este archivo reemplaza y unifica la lógica de los traductores anteriores, incorporando por primera vez el procesamiento de **señas dinámicas** dentro del traductor en tiempo real.

La parte dinámica permite detectar el movimiento de la mano, segmentar automáticamente el gesto, almacenar la secuencia real de frames, aplicar `temporal_pooling` y realizar una predicción utilizando el modelo dinámico entrenado.

### 1. Carga opcional del modelo dinámico

Se agregó soporte para cargar un modelo independiente para las señas dinámicas:

```python
self.modelo_dinamico = None
self.encoder_dinamico = None
self.meta_dinamico = None
self.confidence_threshold_dinamico = confidence_threshold_dinamico
```

El modelo dinámico utiliza archivos independientes del modelo estático:

```python
model_path = os.path.join(
    models_dir,
    "custom_sign_model_dinamico.pkl"
)

encoder_path = os.path.join(
    models_dir,
    "custom_sign_labels_dinamico.pkl"
)

meta_path = os.path.join(
    models_dir,
    "custom_sign_meta_dinamico.json"
)
```

La carga se realiza mediante `_cargar_modelo_dinamico()`:

```python
def _cargar_modelo_dinamico(self, models_dir):
    model_path = os.path.join(
        models_dir,
        "custom_sign_model_dinamico.pkl"
    )
    encoder_path = os.path.join(
        models_dir,
        "custom_sign_labels_dinamico.pkl"
    )
    meta_path = os.path.join(
        models_dir,
        "custom_sign_meta_dinamico.json"
    )

    if not all(os.path.exists(p) for p in (
        model_path,
        encoder_path,
        meta_path
    )):
        print("[AVISO] Modelo dinamico no encontrado. Solo senas estaticas.")
        return

    self.modelo_dinamico = joblib.load(model_path)
    self.encoder_dinamico = joblib.load(encoder_path)

    with open(meta_path, "r", encoding="utf-8") as f:
        self.meta_dinamico = json.load(f)
```

Esto permite que el traductor continúe funcionando aunque todavía no exista un modelo dinámico entrenado.

---

### 2. Buffer para almacenar la secuencia dinámica

Se incorporó un `deque` para almacenar los vectores de características correspondientes al gesto:

```python
self.buffer_dinamico = deque(maxlen=MAX_FRAMES_GESTO)
```

Se definió un límite de seguridad:

```python
MAX_FRAMES_GESTO = 45
```

Este valor **no representa una ventana fija de reconocimiento**. El tamaño real de la secuencia depende del inicio y final del movimiento.

El `maxlen` solamente evita que el buffer crezca indefinidamente si por algún problema el detector de movimiento permanece activo.

---

### 3. Detección de movimiento mediante la posición de la muñeca

Se agregó un detector específico para determinar cuándo comienza y termina una seña dinámica.

A diferencia de las características utilizadas por el modelo estático, el movimiento se calcula utilizando directamente la posición de la muñeca:

```python
def _medir_movimiento(self, results):
    if not results.multi_hand_landmarks:
        self.wrist_anterior = None
        return False, 0.0

    wrist_lm = results.multi_hand_landmarks[0].landmark[0]
    wrist_actual = (wrist_lm.x, wrist_lm.y)

    if self.wrist_anterior is None:
        self.wrist_anterior = wrist_actual
        return False, 0.0

    dx = wrist_actual[0] - self.wrist_anterior[0]
    dy = wrist_actual[1] - self.wrist_anterior[1]

    mov = (dx * dx + dy * dy) ** 0.5

    self.wrist_anterior = wrist_actual

    return mov > self.umbral_movimiento, mov
```

El umbral puede configurarse mediante:

```python
self.umbral_movimiento = umbral_movimiento
```

y desde la línea de comandos:

```bash
python realtime_translator.py --umbral-movimiento 0.015
```

Esto permite controlar la sensibilidad del detector.

---

### 4. Segmentación automática del gesto dinámico

Una de las principales incorporaciones fue sustituir una ventana fija de frames por una **segmentación basada en eventos de movimiento**.

Se agregaron los siguientes estados:

```python
self.grabando_gesto = False
self.frames_quieto_en_gesto = 0
```

La segmentación funciona de la siguiente manera:

1. Se detecta movimiento.
2. Se inicia un nuevo gesto.
3. Los vectores de características se almacenan en `buffer_dinamico`.
4. Cuando el movimiento desaparece, comienza un período de espera.
5. Si la mano permanece quieta durante varios frames, el gesto finaliza.
6. Se procesa la secuencia completa mediante `pool_sequence()`.

La lógica principal se encuentra en:

```python
def _procesar_segmentacion(self, feature_vector, en_movimiento):
    if self.modelo_dinamico is None:
        return None, 0.0, None, 0.0

    if en_movimiento:
        self.frames_quieto_en_gesto = 0

        if not self.grabando_gesto:
            self.buffer_dinamico.clear()
            self.grabando_gesto = True

        self.buffer_dinamico.append(feature_vector)

        return self._preview_en_vivo()

    if self.grabando_gesto:
        self.frames_quieto_en_gesto += 1

        if self.frames_quieto_en_gesto >= self.frames_quieto_para_finalizar:
            resultado = self._finalizar_gesto()

            self.grabando_gesto = False
            self.frames_quieto_en_gesto = 0

            return resultado

        self.buffer_dinamico.append(feature_vector)

        return self._preview_en_vivo()

    return None, 0.0, None, 0.0
```

Se utiliza:

```python
FRAMES_QUIETO_PARA_FINALIZAR = 4
```

para permitir pequeñas pausas durante un mismo gesto antes de finalizarlo.

---

### 5. Finalización automática cuando se pierde la mano

También se contempló el caso en que MediaPipe deja de detectar la mano.

En lugar de mantener indefinidamente el gesto abierto, la pérdida de la mano se considera el final inmediato de la secuencia:

```python
if not results.multi_hand_landmarks:
    ...

    if self.grabando_gesto:
        resultado_dinamico = self._finalizar_gesto()
        self.grabando_gesto = False
        self.frames_quieto_en_gesto = 0
```

Esto permite finalizar una secuencia incluso cuando la mano desaparece del área de detección.

---

### 6. Predicción dinámica durante el gesto

Se agregó `_preview_en_vivo()` para mostrar una estimación mientras el usuario todavía está realizando el movimiento.

Antes de realizar una predicción se exige un mínimo de frames:

```python
MINIMO_FRAMES_PARA_PREDECIR = 5
```

Cuando existe suficiente información, se aplica el mismo `pool_sequence()` utilizado durante el entrenamiento:

```python
vector_pooled = pool_sequence(
    list(self.buffer_dinamico)
)
```

Posteriormente se utiliza el modelo dinámico:

```python
probs = self.modelo_dinamico.predict_proba(
    [vector_pooled]
)[0]

best_idx = probs.argmax()

label_din = self.encoder_dinamico.inverse_transform(
    [best_idx]
)[0]

conf_din = float(probs[best_idx])
```

El resultado del preview se almacena para poder reutilizarlo entre frames:

```python
self._ultimo_dinamico = resultado
```

---

### 7. Reducción de llamadas al modelo durante el preview

Para evitar ejecutar `predict_proba()` innecesariamente en cada frame, se incorporó un pequeño control de frecuencia:

```python
CADA_N_FRAMES_PREVIEW = 2
```

y:

```python
if self._frame_idx % CADA_N_FRAMES_PREVIEW != 0:
    return self._ultimo_dinamico
```

De esta forma, el preview dinámico se actualiza cada cierto número de frames mientras el gesto continúa.

La predicción definitiva no utiliza este throttle, ya que se realiza cuando termina el gesto.

---

### 8. Predicción definitiva utilizando la secuencia completa

La predicción final se concentra en `_finalizar_gesto()`:

```python
def _finalizar_gesto(self):
    if (
        self.modelo_dinamico is None
        or len(self.buffer_dinamico) < MINIMO_FRAMES_PARA_PREDECIR
    ):
        self.buffer_dinamico.clear()
        self._ultimo_dinamico = (
            None, 0.0, None, 0.0
        )
        return None, 0.0, None, 0.0

    vector_pooled = pool_sequence(
        list(self.buffer_dinamico)
    )

    self.buffer_dinamico.clear()
```

La característica importante es que ya no se utiliza una ventana fija de tamaño determinado para todos los gestos.

La secuencia puede contener diferente cantidad de frames y posteriormente se transforma a un vector de tamaño fijo mediante `pool_sequence()`.

---

### 9. Aplicación de `temporal_pooling` durante la inferencia

El sistema dinámico reutiliza el mismo procesamiento temporal utilizado durante el entrenamiento:

```python
vector_pooled = pool_sequence(
    list(self.buffer_dinamico)
)
```

Esto genera el descriptor:

```text
secuencia de frames
        ↓
temporal_pooling
        ↓
mean + std + delta
        ↓
vector de tamaño fijo
        ↓
modelo dinámico
        ↓
seña reconocida
```

Esto mantiene consistente el formato de entrada entre entrenamiento e inferencia.

---

### 10. Margen mínimo entre las dos predicciones principales

Además del umbral de confianza, se agregó una condición adicional para evitar confirmar predicciones ambiguas.

Primero se ordenan las probabilidades:

```python
ordenados = sorted(probs, reverse=True)

margen = (
    ordenados[0] - ordenados[1]
    if len(ordenados) > 1
    else ordenados[0]
)
```

Después se comprueban dos condiciones:

```python
confirma = (
    conf_din >= self.confidence_threshold_dinamico
    and
    margen >= self.margen_confianza
)
```

El margen predeterminado es:

```python
MARGEN_CONFIANZA_MINIMO = 0.12
```

Por lo tanto, una predicción dinámica no se confirma únicamente porque la primera clase supere el umbral de confianza; también debe existir una diferencia suficiente respecto a la segunda opción.

---

### 11. Diferenciación entre preview y confirmación

El sistema distingue entre:

* **Predicción de referencia:** resultado mostrado mientras el gesto todavía está en ejecución.
* **Confirmación:** resultado obtenido cuando el gesto termina y supera las condiciones de confianza.

Cuando no existe suficiente seguridad:

```python
resultado = (
    None,
    0.0,
    label_din,
    conf_din
)
```

De esta manera, el sistema puede mostrar qué seña considera más probable sin agregarla inmediatamente al historial como una predicción confirmada.

Cuando se cumplen las condiciones:

```python
self.history.append(label_din)

resultado = (
    label_din,
    conf_din,
    label_din,
    conf_din
)
```

---

### 12. Modos de ejecución para probar el modelo dinámico

Se agregó un modo específico para ejecutar únicamente el sistema dinámico:

```python
MODOS_VALIDOS = (
    "ambos",
    "estatico",
    "dinamico"
)
```

El modo dinámico puede ejecutarse mediante:

```bash
python realtime_translator.py --modo dinamico
```

En este modo:

```python
if self.modo == "dinamico":
    resultado_dinamico = self._procesar_segmentacion(
        features,
        en_movimiento
    )

    return (
        None,
        0.0,
        results,
        None,
        resultado_dinamico,
        en_movimiento or self.grabando_gesto
    )
```

Esto permite evaluar el reconocimiento dinámico de manera independiente del clasificador estático.

---

### 13. Integración del sistema dinámico dentro de `predict()`

La función `predict()` fue ampliada para devolver también información relacionada con la seña dinámica:

```python
return (
    label,
    confidence,
    results,
    confirmed,
    resultado_dinamico,
    en_movimiento
)
```

El nuevo flujo dinámico es:

```text
Frame de cámara
      ↓
MediaPipe
      ↓
Landmarks
      ↓
Vector de características
      ↓
Detector de movimiento
      ↓
¿Movimiento?
   ┌──┴──┐
   │     │
  Sí    No
   │     │
   ↓     ↓
Iniciar  Esperar
buffer   finalización
   │     │
   └──┬──┘
      ↓
Fin del gesto
      ↓
pool_sequence()
      ↓
Modelo dinámico
      ↓
Confianza + margen
      ↓
Confirmación
```

---

### 14. Estado visual del reconocimiento dinámico

`draw_overlay()` también fue ampliado para representar el estado de la seña dinámica.

Mientras existe movimiento:

```python
cv2.putText(
    frame,
    f"{label_dinamico_en_vivo} "
    f"({conf_din_vivo*100:.0f}%)",
    (30, 60),
    cv2.FONT_HERSHEY_SIMPLEX,
    1.3,
    (255, 140, 0),
    2
)
```

Si todavía no existe una predicción:

```python
cv2.putText(
    frame,
    "Moviendo... (analizando)",
    (30, 60),
    cv2.FONT_HERSHEY_SIMPLEX,
    1.1,
    (255, 140, 0),
    2
)
```

Además, se muestra el estado del buffer:

```python
progreso = len(self.buffer_dinamico)

estado = (
    "grabando"
    if self.grabando_gesto
    else "en espera"
)

cv2.putText(
    frame,
    f"[dinamica] {estado}: {progreso} frames",
    (30, h - 20),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.6,
    (200, 150, 0),
    2
)
```

Esto permite observar durante la ejecución si el sistema está esperando un gesto, grabándolo o procesándolo.

---

### 15. Parámetros configurables desde consola

Se agregaron parámetros para controlar el comportamiento del reconocimiento dinámico:

```python
parser.add_argument(
    "--umbral-movimiento",
    type=float,
    default=0.015,
    help="Sensibilidad del detector de movimiento"
)

parser.add_argument(
    "--modo",
    choices=MODOS_VALIDOS,
    default="ambos"
)

parser.add_argument(
    "--frames-quieto",
    type=int,
    default=FRAMES_QUIETO_PARA_FINALIZAR,
    help="Cuantos frames quieto seguidos = el gesto terminó"
)

parser.add_argument(
    "--margen-confianza",
    type=float,
    default=MARGEN_CONFIANZA_MINIMO,
    help="Diferencia mínima entre la 1ra y 2da opción para confirmar"
)
```

Esto permite ajustar la sensibilidad del sistema sin modificar directamente el código fuente.

---

### 16. Resultado de la incorporación dinámica

Con estos cambios, `realtime_translator.py` pasó de ser únicamente un traductor basado en posturas individuales a incorporar un flujo específico para **señas dinámicas basadas en movimiento**.

El nuevo flujo dinámico implementado en este archivo es:

```text
Detección de mano
       ↓
Posición de muñeca
       ↓
Detector de movimiento
       ↓
Inicio del gesto
       ↓
Buffer dinámico
       ↓
Detección de finalización
       ↓
Secuencia completa
       ↓
pool_sequence()
       ↓
Modelo dinámico
       ↓
Confianza + margen
       ↓
Confirmación de la seña
```

La principal diferencia respecto al reconocimiento estático es que el modelo dinámico no clasifica únicamente una postura individual, sino que utiliza una **secuencia de frames correspondiente al evento de movimiento**, que posteriormente es convertida mediante `temporal_pooling` en un vector de tamaño fijo para el clasificador.


## `webs_server.py` — Incorporación del reconocimiento dinámico


* Integración del reconocimiento de **señas dinámicas** dentro del servidor web y visor remoto.
* Soporte simultáneo para:

  * Señas estáticas.
  * Señas dinámicas basadas en movimiento.
* Integración del nuevo retorno de `CustomSignTranslator.predict()`, que ahora proporciona **6 valores**:

  * Etiqueta reconocida.
  * Confianza.
  * Resultados de MediaPipe.
  * Confirmación de seña estática.
  * Resultado de la seña dinámica.
  * Estado de movimiento.
* Incorporación de `meta_dinamico` para obtener y mostrar las palabras disponibles en el modelo dinámico.
* El endpoint `/api/info` ahora informa las señas reconocibles tanto del modelo estático como del dinámico.

###  Modificado

* Actualizado `_vision_pipeline_worker()` para procesar el resultado del modelo dinámico.
* Se añadió el desempaquetado de:

  * `confirmado_dinamico`
  * `confianza_dinamico`
  * `label_vivo`
  * `conf_vivo`
* El servidor ahora unifica las confirmaciones estáticas y dinámicas antes de enviarlas al visor remoto.
* Las señas dinámicas **confirmadas** ahora son transmitidas mediante WebSocket, al igual que las señas estáticas.
* `VirtualCamManager` también recibe las confirmaciones de señas dinámicas.
* El overlay de la cámara recibe información adicional sobre el movimiento para representar correctamente el estado del reconocimiento.

###  Lógica de confirmación

El servidor ya no depende únicamente de una seña estática para generar una traducción.

Ahora una traducción puede ser confirmada mediante:

```text
Seña estática confirmada
        │
        ├──► Traducción
        │
Seña dinámica confirmada
        │
        └──► Traducción
```

Cuando cualquiera de los dos modelos confirma una seña, el servidor:

1. Obtiene la palabra reconocida.
2. Obtiene su nivel de confianza.
3. Sanitiza la palabra.
4. Envía la traducción a los clientes WebSocket.
5. Notifica a la cámara virtual cuando está activa.

###  WebSocket

* El canal `/ws/translations` ahora puede recibir traducciones provenientes tanto del reconocimiento estático como del dinámico.
* Se mantiene la misma estructura de mensaje para ambos tipos de señas, evitando cambios adicionales en el visor remoto.

###  API

El endpoint `/api/info` fue ampliado para distinguir entre:

```json
{
  "pretrained_words": [],
  "pretrained_words_dinamicas": []
}
```

Esto permite al cliente conocer qué señas estáticas y dinámicas están disponibles en el servidor.

###  Pipeline de visión

* El pipeline continúa ejecutándose en un hilo independiente.
* El procesamiento de cámara, inferencia, overlay, transmisión MJPEG y cámara virtual se mantienen funcionando de forma conjunta.
* La integración dinámica no elimina ni reemplaza el reconocimiento estático, sino que permite utilizar ambos modos simultáneamente.

###  Correcciones

* Corregido el desempaquetado del resultado de `CustomSignTranslator.predict()` después de la incorporación del modelo dinámico.
* Corregido el flujo de notificación para que las señas dinámicas confirmadas no queden únicamente como información de previsualización.
* Evitada la transmisión de resultados dinámicos que todavía no hayan sido confirmados por el modelo.

###  Compatibilidad

El servidor utiliza:

```python
modo="ambos"
```

permitiendo trabajar simultáneamente con reconocimiento **estático + dinámico**.

La integración conserva las medidas existentes de autenticación, sanitización, rate limiting, control de sesiones y seguridad del WebSocket.
