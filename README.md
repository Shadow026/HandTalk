# 🖐️ Traductor de Señas Personalizado

Este proyecto implementa un sistema de reconocimiento de lenguaje de señas donde el usuario define sus propias palabras y gestos. El sistema utiliza landmarks de MediaPipe para garantizar una alta precisión independientemente de la iluminación o el fondo.

## ⚡ Instalación Rápida y Automática (Recomendado)

HandTalk incluye instaladores automatizados con menús interactivos que detectan versiones compatibles de Python (3.10, 3.11, 3.12), configuran el entorno virtual `venv`, instalan dependencias y crean atajos globales en tu terminal.

### 🐧 En GNU/Linux (Bash)
Ejecuta en la terminal desde la carpeta raíz del proyecto:
```bash
chmod +x install.sh
./install.sh
```

### 🪟 En Microsoft Windows (PowerShell)
Abre PowerShell en la carpeta raíz del proyecto y ejecuta:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
*(O si ya estás dentro de una sesión de PowerShell)*:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\install.ps1
```

> **Atajos de Terminal Generados:**
> Tras la instalación, podrás usar los siguientes comandos desde cualquier terminal sin necesidad de activar manualmente el `venv`:
> - `handtalk-captura` ➔ Abre la interfaz gráfica para recolectar señas.
> - `handtalk-entrenar` ➔ Entrena el modelo clasificador.
> - `handtalk-traducir` ➔ Inicia la traducción en tiempo real con cámara.

### 🔄 Actualización de Dependencias
Si en el futuro se agregan nuevas librerías al archivo `inicio/requirements.txt`, no es necesario reinstalar todo el entorno desde cero ni perder tus configuraciones. Solo debes ejecutar nuevamente el instalador (`./install.sh` o `.\install.ps1`) y seleccionar:
- **`[2] Actualizar Dependencias`**: Detecta automáticamente tu entorno virtual existente e instala únicamente los paquetes nuevos o pendientes dentro del `venv`, ejecutando además una prueba de integridad de módulos sin alterar tus atajos ni tus modelos entrenados.

> ⚠️ **Importante**: Por seguridad, esta opción valida que el entorno virtual y los atajos de terminal hayan sido creados previamente mediante la opción `[1]`.

---

## ⚙️ Guía de Configuración Manual del Entorno

Si prefieres configurar el entorno manualmente:

### 1. Requisitos de Python
El proyecto requiere **Python 3.10, 3.11 o 3.12**.
⚠️ **IMPORTANTE**: No utilices versiones como Python 3.13 o 3.14, ya que MediaPipe 0.10.14 no posee soporte para estas versiones.

### 2. Instalación Manual Paso a Paso (Windows / Linux)

Abre una terminal en la carpeta raíz del proyecto y ejecuta:

```bash
# 1. Crear el entorno virtual (usando Python 3.10-3.12)
python3.11 -m venv venv   # En Linux
py -3.11 -m venv venv     # En Windows

# 2. Activar el entorno virtual
source venv/bin/activate       # En Linux
.\venv\Scripts\Activate.ps1    # En Windows

# 3. Actualizar pip
pip install --upgrade pip setuptools wheel

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
