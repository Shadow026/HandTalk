"""
Ejemplo mínimo de backend FastAPI para HandTalk:
- /stream            -> video MJPEG de la webcam (para el <img> del visor)
- /ws/translations   -> WebSocket que manda la palabra traducida
- /                  -> sirve el visor.html

Requiere: fastapi, uvicorn, opencv-python
    pip install fastapi uvicorn[standard] opencv-python
"""

import asyncio
import json
import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse

app = FastAPI()

# --- Cámara compartida ---
# En HandTalk real, este mismo objeto de captura es el que ya usa
# tu motor de traducción (MediaPipe). Aquí se abre una webcam directa
# solo para el ejemplo.
camara = cv2.VideoCapture(0)

# --- Clientes WebSocket conectados (para poder mandarles la palabra) ---
clientes_conectados: list[WebSocket] = []


def generar_frames():
    """Generador que produce frames JPEG en formato multipart (MJPEG)."""
    while True:
        ok, frame = camara.read()
        if not ok:
            continue

        # Aquí podrías dibujar algo con cv2 si quieres overlay en el video,
        # pero el texto principal lo mandamos aparte por WebSocket.

        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            continue

        frame_bytes = buffer.tobytes()

        # Formato MJPEG: cada frame se separa con un boundary
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/auth/qr")
def auth_qr():
    """
    Uso futuro:
    Valida token del QR, setea cookie HttpOnly y redirige a /viewer
    """
    print("valid qr token")


@app.get("/login")
def login_get():
    """
    Uso futuro:
    Sirve la pantalla para ingresar el PIN si no se usó el QR.
    """
    #return FileResponse("login.html")
    print("Welcome to login")


@app.post("/login")
def login_post():
    """
    Uso futuro:
    Valida el PIN ingresado y genera la cookie de sesión.
    """
    #return FileResponse("login.html")
    print("Welcome to login")

@app.get("/viewer")
def viewer_get():
    """
    Uso futuro:
    Sirve la página HTML del visor en vivo (diseñada por Wilfredo).
    """
    return FileResponse("visor.html")
    print("live viewer page")
    

# Queda opcional el uso de mostrar la pantalla del programa
@app.get("/stream")
def stream():
    """
    Uso Opcional:
    Sirve el video MJPEG de la webcam(servidor) para el visor en vivo
    """
    return StreamingResponse(
        generar_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.websocket("/ws/translations")
async def ws_translations(websocket: WebSocket):
    await websocket.accept()
    clientes_conectados.append(websocket)
    try:
        while True:
            # Este endpoint no necesita recibir nada del cliente,
            # solo mantenerse abierto para poder enviarle datos.
            # Si el cliente cierra la pestaña, esto lanza WebSocketDisconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        clientes_conectados.remove(websocket)

@app.post("/logout")
def logout():
    """
    Uso futuro:
    Invalida la sesión actual y libera el cupo.
    """
    print("Logged out")


async def notificar_traduccion(word: str, confidence: float):
    """
    Esta función es la que llamarías desde tu motor de traducción
    (el callback on_translation_confirmed del documento EVENTOS.md)
    cada vez que se confirma una seña.
    """
    payload = json.dumps({"word": word, "confidence": confidence})
    for cliente in clientes_conectados.copy():
        try:
            await cliente.send_text(payload)
        except Exception:
            clientes_conectados.remove(cliente)


# --- Ejemplo de prueba: manda una palabra falsa cada 3 segundos ---
@app.on_event("startup")
async def demo_loop():
    async def loop():
        palabras = ["HOLA", "GRACIAS", "BIEN", "ADIÓS"]
        i = 0
        while True:
            await asyncio.sleep(3)
            await notificar_traduccion(palabras[i % len(palabras)], 0.9)
            i += 1

    asyncio.create_task(loop())