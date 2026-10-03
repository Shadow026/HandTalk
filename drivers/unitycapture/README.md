# Unity Capture DirectShow Filter Driver

Este directorio contiene los binarios precompilados y scripts de registro del filtro DirectShow **Unity Capture** para Windows, utilizado por **HandTalk** para emitir video en tiempo real hacia aplicaciones de videollamada como Zoom, Google Meet y Microsoft Teams.

## Origen y Licencia
* **Proyecto Original:** [schellingb/UnityCapture](https://github.com/schellingb/UnityCapture)
* **Autor:** Bernhard Schelling
* **Licencia:** MIT / Unlicense (Dominio Público)
* **Arquitectura:** DirectShow Source Filter (COM Server)

## Contenido
* `UnityCaptureFilter64.dll`: Filtro DirectShow para aplicaciones de 64 bits (Zoom x64, Teams x64, Chrome, Edge).
* `UnityCaptureFilter32.dll`: Filtro DirectShow para aplicaciones heredadas de 32 bits.
* `Install.bat`: Script batch para registrar las DLLs (`regsvr32 /s`). Requiere ejecutarse como Administrador.
* `Uninstall.bat`: Script batch para desregistrar las DLLs del sistema.

## Uso en HandTalk
HandTalk utiliza la librería `pyvirtualcam` con el backend `unitycapture`:
```python
import pyvirtualcam

with pyvirtualcam.Camera(width=1280, height=720, fps=30, backend="unitycapture") as cam:
    cam.send(frame)
```
El dispositivo aparecerá en las aplicaciones de videollamada con el nombre: **"Unity Video Capture"**.
