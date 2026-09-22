# 📝 Changelog — HandTalk

Este archivo registra los cambios, mejoras y correcciones implementadas en el proyecto.

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
- **Sincronización de PIN**: Solucionado el error donde el visor web rechazaba el PIN debido a la generación independiente en `qr_generator.py`.
- **Errores de Sintaxis y Módulos**: Corrección de literales de cadena no terminados en el traductor y resolución de `ModuleNotFoundError` para `temporal_pooling` y `qr_generator`.
- **Estabilidad de Entrenamiento**: Solucionado el error de ambigüedad de NumPy (`truth value of an array`) en el entrenamiento de modelos dinámicos.
- **Gestión de Recursos**: Implementación del método `cleanup()` en `CaptureGUI` para liberar la cámara al cambiar de pestaña en el menú universal.
- **Dependencias**: Corrección de `NameError` por falta de importación de `Optional` en el módulo de generación de QR.

---
