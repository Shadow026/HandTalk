# 📢 Especificación de Eventos de Traducción

Este documento define el "Contrato de Interfaz" para el sistema de traducción. El objetivo es desacoplar el motor de reconocimiento de las salidas (Voz, Visor Web, Cámara Virtual, etc.), permitiendo que el equipo trabaje en paralelo.

## 1. El Evento: `on_translation_confirmed`

El motor de traducción emitirá un evento cada vez que el sistema de suavizado temporal confirme que una seña ha sido detectada con consistencia.

### Estructura de Datos (Payload)

Cada vez que se dispare el evento, se enviará un objeto/argumentos con la siguiente estructura:

| Campo | Tipo | Descripción | Ejemplo |
| :--- | :--- | :--- | :--- |
| `word` | `String` | La palabra o etiqueta de la seña reconocida. | `"Hola"` |
| `confidence` | `Float` | Nivel de certeza del modelo (0.0 a 1.0). | `0.92` |
| `timestamp` | `String` | Marca de tiempo de la confirmación (Formato ISO 8601). | `"2026-09-06T15:30:01Z"` |

---

## 2. Patrón de Implementación (Publicador/Suscriptor)

Para evitar modificar el motor central cada vez que se agregue una funcionalidad, utilizaremos un sistema de **Callbacks**.

### Cómo funciona:
1.  **El Traductor (`realtime_translator.py`)** mantiene una lista de funciones suscriptoras.
2.  **Los Módulos de Salida** (Voz, Web, etc.) registran su función de respuesta al iniciar la aplicación.
3.  **Al confirmar una seña**, el traductor recorre la lista y ejecuta cada función enviando los datos del evento.

### Ejemplo de Integración para el Equipo

Si eres responsable de un módulo de salida, tu integración debe verse así:

```python
# 1. Define tu función de respuesta siguiendo la firma acordada
def mi_modulo_de_salida(word, confidence, timestamp):
    print(f"Evento recibido -> Palabra: {word}, Confianza: {confidence}")
    # Aquí va la lógica de tu módulo (ej. llamar a la API de Voz o enviar a WebSocket)

# 2. Regístrala en el motor de traducción al iniciar
# (El método register_callback será implementado en realtime_translator.py)
translator.register_callback(mi_modulo_de_salida)
```

---

## 3. Flujo de Datos

`Captura de Frame` $\rightarrow$ `Extracción de Landmarks` $\rightarrow$ `Clasificador` $\rightarrow$ `Suavizador Temporal` $\rightarrow$ **`DISPARO DE EVENTO`** $\rightarrow$ `[Voz, Web, Cámara Virtual, GUI]`

---

**Estado**: Definido y aprobado.
**Responsable**: Francisco (Arquitecto).
