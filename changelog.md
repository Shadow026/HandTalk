## Proceso de compilación con PyInstaller

### Añadido
- `build.ps1`: script de compilación para Windows. Pregunta el modo al ejecutarse:
  - **Limpio (L):** compila y copia solo `assets` junto al `.exe` (icono de la ventana).
  - **Pruebas (P):** compila y copia `models`, `custom_dataset`, `sketches` y `assets` junto al `.exe`, para probar cambios sin recompilar.
- `BUILD.md`: documentación del proceso de compilación, modos, estructura de `dist\MakeSign\` y problemas conocidos.
- Dependencia de desarrollo: **PyInstaller** (`pyinstaller==6.22.3`). Solo se necesita para compilar.

### Detalles del build
- Punto de entrada: `inicio/menu_universal.py`, salida en `dist\MakeSign\MakeSign.exe` (`--onedir`).
- Se empaquetan `login.html`, `visor.html` e `index.html` con `--add-data`, porque `web_server.py` los busca dentro de `_internal`.
- Opciones para módulos que PyInstaller no detecta solo: `--collect-all mediapipe`, `--collect-submodules uvicorn`, `--hidden-import websockets`.

### Notas
- El modo Limpio no empaqueta `models`, `custom_dataset` ni `sketches`.
- Un build de Pruebas no se entrega.