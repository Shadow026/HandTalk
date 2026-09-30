# Compilación de MakeSign (Windows)

Este documento explica cómo generar el ejecutable de MakeSign con PyInstaller.
El punto de entrada de la aplicación es `inicio/menu_universal.py`.

## Requisitos

- Windows con PowerShell
- Entorno virtual con las dependencias del proyecto instaladas:
  ```powershell
  pip install -r inicio/requirements.txt
  pip install pyinstaller
  ```
- Ejecutar todo desde la raíz del proyecto (`HandTalk/`)

## Cómo compilar

```powershell
.\build.ps1
```

El script pregunta el modo de compilación:

```
¿Compilar en (L)impio o para (P)ruebas? [L/P]
```

Si PowerShell bloquea la ejecución del script, usar una sola vez:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

## Modos de compilación

| Modo | Qué hace | Cuándo usarlo |
|------|----------|---------------|
| **L** (Limpio) | Compila y copia solo la carpeta `assets` junto al `.exe` (necesaria para el icono de la ventana). | Compilación base sin datos pesados. |
| **P** (Pruebas) | Compila y luego copia `models`, `custom_dataset`, `sketches` y `assets` junto al `.exe`. | Probar cambiando modelos o dataset sin recompilar. |

## Qué hace `build.ps1`

1. Pide el modo (L o P) y valida la respuesta.
2. Ejecuta PyInstaller con estas opciones:
   - `--onedir --console`: genera una carpeta con el `.exe` y muestra la consola.
   - `--name MakeSign --icon assets/makesign.ico`: nombre e icono del ejecutable.
   - `--paths=. --paths=inicio`: permite encontrar los módulos del proyecto.
   - `--add-data` para `login.html`, `visor.html` e `index.html`: `web_server.py` los busca dentro de `_internal`.
   - `--collect-all mediapipe`: incluye los archivos `.tflite` y binarios de MediaPipe.
   - `--collect-submodules uvicorn` y `--hidden-import websockets`: módulos que PyInstaller no detecta solo.
3. Si PyInstaller falla, el script se detiene con un mensaje de error.
4. Copia las carpetas de datos según el modo elegido.

## Resultado

```
dist\MakeSign\
├── MakeSign.exe
├── _internal\          (librerías y HTML empaquetados)
└── assets\             (y en modo P: models, custom_dataset, sketches)
```

Para ejecutar: `dist\MakeSign\MakeSign.exe`

## Advertencias


- **Modo P no es para entregar:** los datos quedan sueltos junto al `.exe`. La carpeta `dist` de un build de pruebas no se entrega.
- **Modo L no incluye `models`, `custom_dataset` ni `sketches`:** si la versión a entregar los necesita, agregarlos con `--add-data "models;models"` (y equivalentes) en `build.ps1`.
- **Separador de `--add-data`:** es `;` en Windows y `:` en Linux/macOS.
- **Icono de la ventana:** `--icon` solo cambia el icono del `.exe`. El de la ventana lo carga `menu_universal.py` desde `assets/makesign.ico`, por eso `assets` se copia junto al `.exe`.

