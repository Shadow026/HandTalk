# 🖐️ Traductor de Señas Personalizado

Este proyecto implementa un sistema de reconocimiento de lenguaje de señas donde el usuario define sus propias palabras y gestos. El sistema utiliza landmarks de MediaPipe para garantizar una alta precisión independientemente de la iluminación o el fondo.

## ⚙️ Guía de Configuración del Entorno

Para evitar errores de compatibilidad (especialmente con MediaPipe), sigue estos pasos estrictamente.

### 1. Requisitos de Python
El proyecto es compatible con **Python 3.10, 3.11 y 3.12**. 
⚠️ **IMPORTANTE**: No utilices versiones experimentales como Python 3.13 o 3.14, ya que las librerías de visión artificial aún no son compatibles.

### 2. Instalación Paso a Paso (Windows)

Abre una terminal en la carpeta raíz del proyecto y ejecuta:

```powershell
# 1. Crear el entorno virtual
python -m venv venv

# 2. Activar el entorno virtual
.\\venv\\Scripts\\activate

# 3. Actualizar pip para evitar errores de instalación
python -m pip install --upgrade pip

# 4. Instalar las dependencias fijadas
pip install -r inicio/requirements.txt
```

---

## 🚀 Cómo usar el Sistema

El flujo de trabajo debe seguir este orden estrictamente:

### Paso 1: Capturar Señas
Ejecuta la interfaz de captura para grabar tus propias palabras.
```powershell
python inicio/gui_captura.py
```
*   Escribe la palabra que quieres asignar al gesto.
*   Abre la cámara.
*   Presiona la tecla **'S'** repetidamente mientras haces la seña (se recomiendan al menos 20-30 muestras por palabra).

### Paso 2: Entrenar el Modelo
Una vez capturadas las señas, entrena el clasificador.
```powershell
python inicio/train_classifier.py
```
*   El sistema procesará los vectores normalizados y creará los archivos del modelo en la carpeta `/models`.

### Paso 3: Traducir en Tiempo Real
Prueba el reconocimiento de tus señas en vivo.
```powershell
python inicio/realtime_translator.py
```

---

## 📂 Estructura de Carpetas
*   `inicio/`: Contiene todo el núcleo funcional del proyecto.
*   `custom_dataset/`: (Se crea automáticamente) Guarda los vectores de señas en formato JSON.
*   `models/`: (Se crea automáticamente) Almacena el modelo entrenado (`.pkl`).
*   `Documentacion/`: Planes de trabajo y guion técnico.
