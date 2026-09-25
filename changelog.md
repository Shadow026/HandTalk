# 📝 Changelog — HandTalk

Este archivo registra los cambios, mejoras y correcciones implementadas en el proyecto.

## [2026-09-25] - Soporte Multimanual y Optimización de Captura

### 🚀 Nuevas Funcionalidades
- **Soporte para Señas a Dos Manos**:
    - Implementación de extracción de características polimórfica en `hand_features.py` y `realtime_translator.py` para soportar vectores de una y dos manos.
    - Creación de modelos independientes para señas de dos manos (`custom_sign_model_two_hands.pkl`).
    - Actualización de la GUI de captura para permitir el registro de muestras con ambas manos.
- **Gestión de Dataset**:
    - Implementación de funciones para renombrar y eliminar palabras/señas del dataset (`dataset_manager.py`).
    - Integración de botones de gestión en la pestaña de Entrenamiento con diálogos de confirmación y avisos de re-entrenamiento.
- **Sistema de Captura Autónoma**:
    - **Trigger por Gesto**: Implementación de activación automática mediante la detección de "puño cerrado" para permitir la captura sin asistencia externa.
    - **Temporizador de Captura**: Adición de un botón de cuenta regresiva (5s) para facilitar la posición de las manos antes de la toma de muestra.
- **Mejoras de UI/UX**:
    - Ajuste de resolución de ventana (1024x680) y límites mínimos para evitar desbordamientos en pantallas de 1366x768px.
    - Integración de funciones de "Renombrar" y "Eliminar" palabras directamente desde la pestaña de Entrenamiento.

### 🐛 Correcciones de Errores
- **Estabilización de Inferencia Dinámica**:
    - Solución al problema del "parpadeo" mediante la implementación de un sistema de histéresis (persistencia de confirmación).
    - Optimización de los umbrales de movimiento (`MOV_THRESHOLD`) y quietud (`FRAMES_QUIETO_PARA_FINALIZAR`) para reducir falsos negativos.
- **Corrección de Entrenamiento (NumPy)**:
    - Solucionado el error de `inhomogeneous shape` al entrenar datasets mixtos (1 y 2 manos) mediante la separación de muestras por dimensionalidad en `train_classifier.py` y `dataset_manager.py`.
- **Estabilidad de la GUI**:
    - Corrección de `NameError: name 'np' is not defined` en el hilo de captura.
    - Actualización de `max_num_hands` a 2 en el traductor para habilitar la visualización de landmarks en ambas manos.

---

## [2026-09-21] - Integración de Ramas y Estabilización Final

### 🚀 Nuevas Funcionalidades
- **Menú Universal Unificado**: Implementación de `inicio/menu_universal.py` como punto de entrada central, integrando las pestañas de Inicio, Captura, Entrenamiento, Paquetes y Traducción en una sola interfaz profesional.
- **Sistema de Importación/Exportación de Datasets**:
    - Creación de `inicio/pack_manager.py` para empaquetar datasets y modelos en archivos `.zip`.
    - Implementación de manifiestos JSON para validar compatibilidad de features.
    - Sistema de resolución de conflictos (Fusionar, Reemplazar u Omitir) al importar paquetes.
- **Soporte para Señas Dinámicas**:
    - Implementación de `inicio/temporal_pooling.py` para procesar secuencias temporales de landmarks.
    - Actualización de `inicio/gui_captura.py` con modo de captura dinámica (secuencias de frames).
    - Entrenamiento dual en `inicio/train_classifier.py` para modelos estáticos y dinámicos (`_dinamico.pkl`).
    - Lógica de segmentación en `inicio/realtime_translator.py` basada en el movimiento de la muñeca para disparar la inferencia dinámica.
- **Salida de Voz (TTS)**:
    - Integración de `inicio/tts_output.py` para emitir audio de las señas confirmadas mediante un hilo de trabajo desacoplado para evitar congelamientos de la UI.
- **Visor Web Seguro**:
    - Sincronización total entre el `SessionManager` del servidor y el generador de QR.
    - Implementación de acceso directo mediante tokens efímeros en la URL del QR.
    - Refuerzo de seguridad con Rate Limiting y cabeceras CSP.

### 🐛 Correcciones de Errores
- **Sincronización de PIN**: Solucionando el error donde el visor web rechazaba el PIN debido a la generación independiente en `qr_generator.py`.
- **Errores de Sintaxis y Módulos**: Corrección de literales de cadena no terminados en el traductor y resolución de `ModuleNotFoundError` para `temporal_pooling` y `qr_generator`.
- **Estabilidad de Entrenamiento**: Solucionando el error de ambigüedad de NumPy (`truth value of an array`) en el entrenamiento de modelos dinámicos.
- **Gestión de Recursos**: Implementación del método `cleanup()` en `CaptureGUI` para liberar la cámara al cambiar de pestaña en el menú universal.
- **Dependencias**: Corrección de `NameError` por falta de importación de `Optional` en el módulo de generación de QR.

---
