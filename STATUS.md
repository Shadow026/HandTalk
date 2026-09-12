# STATUS.md — Estado Actual del Visor Web (HandTalk)


## 1. Qué hace ahora mismo

- El servidor abre la webcam de la **PC** con OpenCV y la transmite como video (MJPEG) a cualquier dispositivo que entre a la página.
- El texto de la traducción se manda por WebSocket, independiente del video, y se muestra como subtítulo superpuesto.
- Actualmente el texto es de **prueba** (`demo_loop`): manda una palabra distinta cada 3 segundos, para verificar que el flujo completo funciona antes de conectar el modelo real de señas.
- **No** se usa la cámara del celular en esta versión — por eso funciona en HTTP normal, sin restricciones de navegador.

---

## 2. Estructura de archivos necesaria

```
HandTalk/
├── web_server.py       <- Backend FastAPI (servidor + stream + websocket)
├── visor.html           <- Página que ve el celular/navegador
├── generar_qr.py         <- Script para obtener el enlace + QR
```

Los tres archivos deben estar en la **misma carpeta**, porque `web_server.py` sirve `visor.html` directamente desde ahí (`FileResponse("visor.html")`), y `generar_qr.py` genera el QR apuntando al mismo puerto que usa `web_server.py`.
La estrcutura de estos archivos puede cambiar pero para pruebas es suficiente por ahora.

---

## 3. Cómo funciona cada parte

### `web_server.py` (backend)
| Ruta | Qué hace |
|---|---|
| `GET /` | Sirve `visor.html` |
| `GET /stream` | Transmite la webcam de la PC en formato MJPEG (multipart) |
| `WS /ws/translations` | Mantiene la conexión abierta y manda la palabra traducida en JSON cada vez que hay una nueva |

### `visor.html` (frontend)
- Muestra el `<img>` con el stream de la webcam (`src` se arma dinámicamente con `window.location.host`, no está hardcodeado).
- Se conecta al WebSocket y muestra la palabra recibida en un `<div>` superpuesto con `textContent` (nunca `innerHTML`, por seguridad).

### `generar_qr.py`
- Detecta automáticamente la IP de la PC en la red local (sin tocar el gateway ni la tabla de rutas).
- Genera `qr_visor.png` con el enlace `http://<IP>:8000`.
- También imprime el QR directamente en la terminal en ASCII, para probarlo sin abrir ningún archivo.

---

## 4. Dependencias anexadas

```bash
pip install fastapi uvicorn[standard] 
opencv-python 
qrcode[pil]
```

---

## 5. Pasos para levantarlo

### Paso 1 — Levantar el servidor
Desde la carpeta donde están los tres archivos:

```bash
uvicorn web_server:app --host 0.0.0.0 --port 8000 --reload
```

**Importante:** el `--host 0.0.0.0` es obligatorio. Sin él, uvicorn solo escucha en `127.0.0.1` y ningún otro dispositivo de la red puede conectarse, aunque el firewall esté bien configurado.

Deberías ver algo como:
```
Uvicorn running on http://0.0.0.0:8000
```

### Paso 2 — Generar el QR (en otra terminal, con el servidor ya corriendo)

```bash
python generar_qr.py
```

Esto imprime la IP detectada, guarda `qr_visor.png`, y muestra el QR en la terminal:
```
IP detectada:  192.168.1.45
Enlace visor:  http://192.168.1.45:8000/viewer
QR guardado en: qr_visor.png
```

### Paso 3 — Probar
1. Desde la misma PC: abre `http://localhost:8000` en el navegador — deberías ver tu propia webcam con un subtítulo de prueba cambiando cada 3 segundos.
2. Desde el celular (misma red Wi-Fi): escanea el QR o entra manualmente a la URL que imprimió `generar_qr.py`.

Si el celular no carga la página, revisa primero:
- Que el celular esté en la **misma red Wi-Fi** que la PC.
- Que el firewall de Windows/Linux permita conexiones entrantes al puerto 8000 (regla de red privada).

---

## 6. Pendiente / próximos pasos
- [ ] tomar en cuenta el diseño para el live viewer
- [ ] Reemplazar `demo_loop` por la llamada real desde el motor de traducción (`on_translation_confirmed` de `EVENTOS.md`).