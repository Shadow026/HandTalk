## Proceso de compilación con PyInstaller

### Añadido
- `build.ps1`: script de compilación para Windows (se ejecuta desde la raíz de `HandTalk/`). Pregunta el modo al ejecutarse:
  - **Limpio (L):** compila y copia solo `assets` y `drivers` junto al `.exe`, que son lo necesario para una ejecución limpia (`assets` incluye el icono de la ventana).
  - **Pruebas (P):** compila y copia `models`, `custom_dataset`, `sketches`, `assets` y `drivers` junto al `.exe`, para probar cambios sin recompilar.
  - Si se ingresa una opción distinta de L o P, o si PyInstaller falla, el script termina con código de error 1.
- `BUILD.md`: documentación del proceso de compilación, modos, estructura de `dist\MakeSign\` y problemas conocidos.
- Dependencia de desarrollo: **PyInstaller** (`pyinstaller==6.22.3`). Solo se necesita para compilar.

### Detalles del build
- Punto de entrada: `inicio/menu_universal.py`, salida en `dist\MakeSign\MakeSign.exe` (`--onedir`, `--console`, `--noconfirm`) con el icono `assets/makesign.ico`.
- Rutas de búsqueda de módulos: `--paths=.` y `--paths=inicio`.
- Se empaquetan `login.html`, `visor.html` e `index.html` con `--add-data`, porque `web_server.py` los busca dentro de `_internal`.
- Opciones para módulos que PyInstaller no detecta solo: `--collect-all mediapipe`, `--collect-submodules uvicorn`, `--hidden-import websockets`.
- Las carpetas de datos (`assets`, `drivers` y, en Pruebas, `models`, `custom_dataset`, `sketches`) se copian a la raíz de `dist\MakeSign\`, donde `web_server.py` las localiza con `__file__`.

### Notas
- El modo Limpio no empaqueta `models`, `custom_dataset` ni `sketches`.
- Un build de Pruebas no se entrega.