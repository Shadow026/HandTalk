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
>
> ⚠️ **Nota importante para Windows:** Para utilizar los atajos después de la instalación, **no se puede hacer en la misma terminal donde se realizó la instalación**. Es necesario **abrir una nueva ventana de terminal de PowerShell (o CMD)** para que el sistema refresque las variables de entorno y reconozca la ruta del `PATH`.

### 🔄 Actualización de Dependencias
Si en el futuro se agregan nuevas librerías al archivo `inicio/requirements.txt`, no es necesario reinstalar todo el entorno desde cero ni perder tus configuraciones. Solo debes ejecutar nuevamente el instalador (`./install.sh` o `.\install.ps1`) y seleccionar:
- **`[2] Actualizar Dependencias`**: Detecta automáticamente tu entorno virtual existente e instala únicamente los paquetes nuevos o pendientes dentro del `venv`, ejecutando además una prueba de integridad de módulos sin alterar tus atajos ni tus modelos entrenados.

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

## 🌐 Visor Web (Traducción Remota)

HandTalk permite transmitir la traducción a cualquier dispositivo (celular, tablet) conectado a la misma red Wi-Fi.

### Cómo levantar el visor:
1. Ejecuta el servidor web:
   ```bash
   uvicorn web_server:app --host 0.0.0.0 --port 8000 --reload
   ```
2. Genera el código QR para acceso rápido:
   ```bash
   python qr_generator.py
   ```
3. Escanea el QR con tu celular para ver la traducción en vivo.

> **Si utilizaste la ultima version del instalador:**
> simplemente escribe en tu terminal: handtalk-visor
---



## 📂 Estructura de Carpetas
*   `inicio/`: Contiene todo el núcleo funcional del proyecto.
*   `custom_dataset/`: (Se crea automáticamente) Guarda los vectores de señas en formato JSON.
*   `models/`: (Se crea automáticamente) Almacena el modelo entrenado (`.pkl`).
*   `Documentacion/`: Planes de trabajo y guion técnico.
*   `web_server.py`, `visor.html`, `qr_generator.py`: Componentes del sistema de visualización remota.
*   `install.sh`, `install.ps1`: Scripts de instalación automatizada.

---

## 🛠️ Control de Calidad y Puntos de Mejora

Esta sección documenta el estado actual del sistema tras las pruebas generales, identificando comportamientos inesperados y recomendaciones técnicas para asegurar el correcto funcionamiento.

### 🐞 Incidentes Técnicos (Bugs)

| Módulo | Problema Detectado | Comportamiento Esperado | Estado |
| :--- | :--- | :--- | :--- |
| **`gui_captura.py`** | **Parpadeo de Imagen**: La transmisión de video de la cámara presenta saltos o parpadeos intermitentes durante la captura. | Un flujo de video fluido y estable para facilitar la recolección de muestras. | ⏳ Pendiente |
| **`web_server.py`** | **Imprecisión en Traducción Remota**: Las palabras enviadas al visor web a veces carecen de precisión en tiempo real. | Implementar un filtro de "palabra confirmada" o ajustar el porcentaje de confianza para coincidir con la precisión de la versión nativa. | ⏳ Pendiente |
| **`General / Cámara`** | **Conflicto de Recursos (Cámara)**: `realtime_translator.py` y `web_server.py` no pueden ejecutarse simultáneamente ni de forma secuencial inmediata. | **Propuesta Tentativa**: Integrar la ejecución del visor web directamente desde `realtime_translator.py` para gestionar un único hilo de cámara y evitar el bloqueo del recurso. | ⏳ Pendiente |

> **Nota sobre la Cámara**: Tras realizar pruebas de funcionamiento con dos hilos de cámara, se ha confirmado que `realtime_translator.py` y `web_server.py` no pueden ejecutarse al mismo tiempo ni de forma secuencial inmediata debido a que el handler de la cámara mantiene el recurso bloqueado. **Se plantea como propuesta tentativa integrar la ejecución del visor directamente desde el traductor en tiempo real para resolver este conflicto.**

### 🛠️ Hotfixes (Soluciones Rápidas)

Esta sección registra las correcciones aplicadas recientemente para mejorar la estabilidad del sistema:

*   **`realtime_translator.py` (Cierre de Ventana)**: Se ha solucionado el problema donde la aplicación no se cerraba al hacer clic en la 'X'.
    *   **El Problema**: OpenCV no notifica automáticamente el cierre de la ventana al hilo de Python, manteniendo el proceso activo en segundo plano.
    *   **La Solución**: Se implementó una verificación dual en el bucle principal:
        1.  `cv2.waitKey(1)`: Forza el procesamiento de eventos de la interfaz gráfica.
        2.  `cv2.getWindowProperty(..., cv2.WND_PROP_VISIBLE)`: Verifica si la ventana sigue siendo visible. Si el valor cae por debajo de 1, el programa reconoce el cierre y finaliza la ejecución limpiamente.

### 🚀 Análisis de Rendimiento y Latencia (Visor Web)

Se ha realizado un test exhaustivo del Visor Web para evaluar la fluidez de la transmisión en diferentes dispositivos. Los resultados indican que la latencia varía según los recursos de hardware del dispositivo receptor:

*   **Dispositivos con 8GB RAM (Ej. Smartphone)**: No se ha detectado latencia perceptible; la transmisión es fluida.
*   **Dispositivos con 4GB RAM (Ej. Laptop)**: Se ha detectado una latencia leve en algunos segmentos de la transmisión.

**Conclusión**: Si bien el rendimiento es más notable en dispositivos con menos RAM, esto ocurre solo en momentos aislados y no llega a comprometer la experiencia de usuario ni la funcionalidad del sistema.

### 🌐 Notas de Conectividad y Red (Importante)

Para evitar errores de conexión al utilizar el **Visor Web** con dispositivos externos (móviles, tablets), ten en cuenta lo siguiente:

*   **Configuración del Firewall**: Por defecto, Windows y otros sistemas operativos pueden bloquear el tráfico entrante en el puerto `8000`. Si el servidor `web_server.py` está activo pero el dispositivo externo no puede conectar:
    1.  Accede a la configuración de **Firewall de Windows**.
    2.  **Permisos de Aplicación**: Asegúrate de que el ejecutable de **Python** tenga marcadas las casillas de permitir comunicación en redes **Privadas** y **Públicas**.
    3.  Asegúrate de que ambos dispositivos estén conectados a la misma red Wi-Fi.
*   **Dirección IP**: Verifica que estés utilizando la IP privada de tu computadora (ej. `192.168.1.x`) y no `localhost` o `127.0.0.1` en el dispositivo externo.
