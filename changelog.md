# Changelog Detallado - Proyecto HandTalk

Este documento detalla exhaustivamente todas las modificaciones técnicas implementadas en el proyecto en comparación con la rama `main`, describiendo el "qué", el "cómo" y el "por qué" de cada cambio.

---

## 🧠 1. Núcleo de Extracción de Características (`inicio/hand_features.py`)

### Implementación de Pooling Temporal
- **Cambio**: Se añadió la función `summarize_sequence(sequence)`.
- **Detalle Técnico**: 
    - Recibe una secuencia de vectores de landmarks (dimensiones `n_frames x n_features`).
    - Calcula la **Media** (`np.mean`) y la **Desviación Estándar** (`np.std`) a lo largo del eje temporal.
    - Concatena ambos resultados para generar un vector final de `2 * n_features`.
- **Propósito**: Convertir una señal temporal (movimiento) en una "firma" estática. Esto permite usar clasificadores eficientes como Random Forest en lugar de recurrir a redes neuronales complejas (RNN/LSTM), manteniendo la ligereza del sistema.

---

## 📂 2. Gestión de Datos (`inicio/dataset_manager.py`)

### Inteligencia de Dataset
- **Cambio**: Implementación de `get_available_types(dataset_dir)`.
- **Detalle Técnico**: Escanea todos los archivos `.json` del directorio de datos y extrae el campo `"type"`.
- **Propósito**: Automatizar el proceso de entrenamiento. El sistema ahora detecta si el usuario ha capturado señas estáticas, dinámicas o ambas, configurando el entrenamiento sin intervención manual.

### Soporte de Tipos de Muestra
- **Cambio**: Refactorización de `load_dataset` y `save_sample`.
- **Detalle Técnico**: Se añadió el parámetro `sample_type` para diferenciar el almacenamiento de un único vector (estático) frente a una lista de vectores (dinámico).

---

## 🖼️ 3. Interfaz de Captura (`inicio/gui_captura.py`)

### Evolución de la UI
- **Selector de Modo**: Se añadió un grupo de `Radiobuttons` para alternar entre "Estática" y "Dinámica".
- **Configuración de Ventana**: Se implementó un campo de entrada para definir la cantidad de frames que componen una seña dinámica (por defecto 20).

### Arquitectura de Hilos (Multithreading)
- **Loop de Captura**: El `capture_loop` ahora es el responsable único de la lectura de cámara y el procesamiento de MediaPipe.
- **Grabación Dinámica**: Cuando se activa el modo dinámico, el hilo de captura acumula vectores en un `buffer_dinamico` hasta alcanzar el objetivo de frames, guardándolos automáticamente al finalizar.
- **Sincronización**: Implementación de `threading.Lock()` para el acceso al frame actual y al vector de características, evitando crashes por acceso concurrente.
- **Comunicación Hilo $\rightarrow$ UI**: Implementación de una `queue.Queue` (`eventos_ui`). El hilo de cámara envía mensajes de "progreso" y "guardado", que el hilo principal de Tkinter procesa en `_procesar_eventos_ui` cada 15ms.

### Optimización de Recursos
- **Eliminación de Race Conditions**: `save_current_sample` ya no llama a `cap.read()`. En su lugar, toma el `ultimo_feature_vector` ya procesado por el hilo de fondo, evitando que dos hilos intenten leer el hardware de la cámara simultáneamente.

---

## 🎓 4. Entrenamiento de Modelos (`inicio/train_classifier.py`)

### Flujo de Entrenamiento Unificado
- **Detección Automática**: El script ahora decide qué modelos entrenar basándose en los tipos de datos encontrados mediante `get_available_types`.
- **Pipeline de Datos Dinámicos**:
    1. Carga secuencias $\rightarrow$ 2. Aplica `pool_sequence` $\rightarrow$ 3. Aplica aumentación sintética.
- **Aumentación Adaptativa**: Se reutiliza la lógica de `augment_static_sample` sobre los vectores resumidos (pooled), permitiendo generar muestras sintéticas para señas dinámicas y compensar la menor cantidad de muestras reales.

### Control de Modelos
- **Nuevos Argumentos**: `--solo-estatico` y `--solo-dinamico` permiten forzar la creación de un solo modelo aunque existan datos de ambos tipos.
- **Persistencia**: El modelo dinámico se guarda en archivos independientes (`custom_sign_model_dinamico.pkl`, etc.) para no interferir con el modelo estático.

---

## ⚡ 5. Traductor en Tiempo Real (`inicio/realtime_translator.py`)

### Motor de Inferencia Híbrido
- **Ventana Deslizante**: Implementación de un `deque` con `maxlen=ventana_dinamica` que almacena los landmarks de los frames más recientes.
- **Inferencia Dual**: En cada frame se calcula la predicción estática y la dinámica (vía pooling) simultáneamente.

### Sistema de Decisión y Movimiento
- **Detector de Muñeca (Wrist Tracker)**: Calcula la distancia euclidiana entre la posición actual y anterior de la muñeca.
- **Lógica de Prioridad**:
    - **Si hay movimiento**: Se resetea el suavizador estático y se prioriza el modelo dinámico. Se muestra la predicción "en vivo" aunque no esté confirmada para dar feedback inmediato.
    - **Si no hay movimiento**: Se utiliza el `PredictionSmoother` para confirmar la seña estática.

### Interfaz Visual (Overlay)
- **Feedback de Buffer**: Se añadió un indicador visual en la parte inferior del frame (`[dinamica] buffer: X/20`) para que el usuario sepa cuánto falta para que la seña dinámica sea procesada.
- **Codificación de Colores**: Verde para confirmaciones estáticas y azul para confirmaciones dinámicas.

---

## 🌐 6. Servidor Web y Visor Remoto (`web_server.py`)

### Optimización de Latencia (Crítico)
- **Sincronización de Stream**: Eliminación del `sleep` fijo en `generar_frames`. El stream ahora es "push", enviando el frame tan pronto como la IA termina de procesarlo.

### Integración de Funcionalidades Dinámicas
- **Broadcasting Unificado**: `_vision_pipeline_worker` ahora detecta cualquier confirmación (estática o dinámica) y la envía inmediatamente a través del WebSocket.
- **API de Información**: Extensión de `/api/info` para incluir `pretrained_words_dinamicas`, permitiendo que el cliente sepa qué señas con movimiento son capaces de reconocer.

---

## 🛠️ 7. Notas de Optimización Pendientes (Backlog)

*Se ha identificado que, aunque el sistema es funcional, la fluidez del movimiento en la versión web presenta caídas de rendimiento. Se han priorizado las siguientes líneas de mejora para futuras iteraciones:*

- **Downscaling de Inferencia**: Implementar redimensionamiento de frames (ej. $640 \times 360$) exclusivamente para el procesamiento de MediaPipe, reduciendo la carga de CPU sin afectar la resolución del stream.
- **Inferencia Saltada (Frame Skipping)**: Ejecutar la predicción de la IA cada $N$ frames en lugar de en cada uno, manteniendo la lectura de cámara a 60 FPS para evitar cuellos de botella.
- **Suavizado de Movimiento**: Implementar un promedio móvil en el detector de la muñeca para evitar saltos bruscos entre el modo estático y dinámico debido al ruido de detección.
- **Optimización de Stream Web**: Evaluar la reducción de resolución del stream MJPEG específicamente para clientes remotos para minimizar el buffering del navegador.
