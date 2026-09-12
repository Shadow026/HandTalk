"""
Backend FastAPI para HandTalk (flujo invertido):
- El navegador del CELULAR abre su propia cámara y manda frames por WebSocket.
- El backend recibe cada frame, lo decodifica a una imagen (numpy array / OpenCV),
  y aquí es donde se conectaría el clasificador de señas real (MediaPipe + modelo).
- El backend responde por el mismo WebSocket con la palabra detectada.

Requiere: fastapi, uvicorn, opencv-python, numpy
    pip install fastapi uvicorn[standard] opencv-python numpy
"""

import base64
import json
from datetime import datetime

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

app = FastAPI()

# Cámara de la PC, solo se usa como respaldo si el celular no puede
# dar acceso a su propia cámara (por ejemplo, por estar en HTTP sin HTTPS).
# Se abre bajo demanda, no al iniciar el servidor, para no ocupar la webcam
# innecesariamente si nadie usa el modo respaldo.
_camara_respaldo = None


def obtener_camara_respaldo():
    global _camara_respaldo
    if _camara_respaldo is None:
        _camara_respaldo = cv2.VideoCapture(0)
    return _camara_respaldo


def generar_frames_respaldo():
    """Generador MJPEG con la webcam de la PC, usado solo en modo respaldo."""
    camara = obtener_camara_respaldo()
    while True:
        ok, frame = camara.read()
        if not ok:
            continue
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )


def decodificar_frame(data_url: str):
    """
    Convierte el string base64 que manda el navegador (formato data URL,
    ej: "data:image/jpeg;base64,/9j/4AAQ...") en una imagen usable con OpenCV.
    Devuelve None si algo falla, para no tumbar la conexión por un frame corrupto.
    """
    try:
        if "," in data_url:
            data_url = data_url.split(",")[1]
        bytes_imagen = base64.b64decode(data_url)
        arreglo = np.frombuffer(bytes_imagen, dtype=np.uint8)
        frame = cv2.imdecode(arreglo, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        print(f"Error decodificando frame: {e}")
        return None


def procesar_frame(frame, numero_frame: int):
    """
    PLACEHOLDER: aquí va la lógica real de MediaPipe + tu modelo de clasificación
    de señas (el mismo pipeline que ya usa HandTalk en el motor de escritorio).

    Por ahora, solo confirma que el frame llegó bien mostrando su tamaño,
    y devuelve una palabra de ejemplo cada cierto número de frames para
    poder probar el flujo completo end-to-end sin el modelo todavía conectado.
    """
    alto, ancho = frame.shape[:2]
    hora = datetime.now().strftime("%H:%M:%S")
    print(f"[{hora}] Frame #{numero_frame} recibido correctamente — {ancho}x{alto} px")

    # --- Aquí se reemplaza esto por la inferencia real ---
    # landmarks = mediapipe_hands.process(frame)
    # palabra, confianza = modelo.predecir(landmarks)
    # return palabra, confianza
    return None  # None = "todavía no hay seña confirmada en este frame"


@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/visor")
def stream():
    """Solo se usa cuando el celular no pudo dar acceso a su propia cámara."""
    return StreamingResponse(
        generar_frames_respaldo(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.websocket("/ws/translations")
async def ws_translations(websocket: WebSocket):
    await websocket.accept()
    print(f"Cliente conectado: {websocket.client.host}")
    contador = 0
    try:
        while True:
            mensaje_bruto = await websocket.receive_text()
            mensaje = json.loads(mensaje_bruto)

            if mensaje.get("type") != "frame":
                continue

            frame = decodificar_frame(mensaje["data"])
            if frame is None:
                print("Frame recibido pero no se pudo decodificar")
                continue

            contador += 1
            resultado = procesar_frame(frame, contador)

            if resultado is not None:
                palabra, confianza = resultado
                await websocket.send_text(json.dumps({
                    "type": "word",
                    "word": palabra,
                    "confidence": confianza,
                }))

    except WebSocketDisconnect:
        print(f"Cliente desconectado. Total de frames recibidos: {contador}")