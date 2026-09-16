#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_server.py
Servidor Web FastAPI y WebSocket para HandTalk (Visor Remoto en LAN).

Responsables: Jason (Ciberseguridad, Redes y Middleware) y Jimmy (Servidor Web).
Punto 4.3 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.

Características de Seguridad:
- HTTP puro en LAN (sin dependencias de certificados TLS locales).
- Autenticación por Código QR (Token efímero) o PIN numérico de 6 dígitos.
- Rate Limiting estricto con SlowAPI contra ataques de fuerza bruta.
- Cabeceras de seguridad HTTP completas (CSP, X-Frame-Options, X-Content-Type-Options).
- Sanitización estricta de palabras traducidas (neutralización de XSS).
- Límite de 2 sesiones concurrentes activas en red local.
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
from typing import List, Optional
from urllib.parse import parse_qs

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from slowapi.errors import RateLimitExceeded

# Importaciones del paquete de ciberseguridad
from inicio.web_security import (
    COOKIE_NAME,
    MAX_ACTIVE_SESSIONS,
    SecurityHeadersMiddleware,
    get_session_manager,
    is_authenticated_request,
    limiter,
    rate_limit_exceeded_handler,
    sanitize_word,
    verify_ws_session,
)

logger = logging.getLogger("HandTalk.WebServer")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="HandTalk Remote Viewer",
    description="Servidor web local seguro para visualización remota de traducciones de señas.",
    version="2.0.0",
)

# 1. Configuración de Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# 2. Inyección de Middleware de Cabeceras de Seguridad (CSP, Hardening)
app.add_middleware(SecurityHeadersMiddleware)

# Gestor de sesiones y credenciales
session_manager = get_session_manager()

# Clientes WebSocket autenticados
clientes_conectados: List[WebSocket] = []

# Configuración de rutas del proyecto
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INICIO_DIR = os.path.join(PROJECT_ROOT, "inicio")
if INICIO_DIR not in sys.path:
    sys.path.insert(0, INICIO_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Estado global del pipeline de visión y traducción en vivo
_latest_mjpeg_frame: Optional[bytes] = None
_frame_lock = threading.Lock()
_stop_vision_event = threading.Event()
_vision_thread: Optional[threading.Thread] = None
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None
_translator = None
_virtual_cam = None
_external_feed_mode: bool = False
_server_thread: Optional[threading.Thread] = None
_server_instance = None


def set_external_feed_mode(enabled: bool = True):
    """Configura si el servidor recibe frames de un proceso/interfaz externa."""
    global _external_feed_mode
    _external_feed_mode = enabled


def update_remote_frame(frame: np.ndarray):
    """Actualiza el frame en memoria para el endpoint /stream MJPEG desde el Menú Universal."""
    global _latest_mjpeg_frame
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 68])
    if ok:
        with _frame_lock:
            _latest_mjpeg_frame = buffer.tobytes()


def broadcast_translation_sync(word: str, confidence: float):
    """Emite la traducción confirmada vía WebSocket hacia los clientes remotos."""
    global _main_event_loop
    if _main_event_loop and _main_event_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            notificar_traduccion(word, confidence),
            _main_event_loop
        )


def start_server_background(host="0.0.0.0", port=8000):
    """Inicia el servidor web FastAPI en un hilo en segundo plano si no está corriendo."""
    global _server_thread, _server_instance
    if _server_thread and _server_thread.is_alive():
        return _server_instance

    set_external_feed_mode(True)
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    _server_instance = uvicorn.Server(config)
    _server_thread = threading.Thread(target=_server_instance.run, daemon=True)
    _server_thread.start()
    return _server_instance


def _vision_pipeline_worker():
    """
    Hilo de inferencia y visión en tiempo real:
    - Abre la cámara física de la PC (si no está en modo feed externo).
    - Procesa cada frame con MediaPipe y el modelo de señas preentrenado (Random Forest).
    - Cuando se confirma una seña real del dataset (ej. 'hola', 'dedo'), la emite
      inmediatamente por WebSocket a los celulares/visores conectados.
    - Almacena el frame con overlay en _latest_mjpeg_frame para el stream /stream.
    """
    global _latest_mjpeg_frame, _translator, _virtual_cam

    if _external_feed_mode:
        logger.info("Modo de feed externo activo. El servidor web utilizará los frames provistos por la interfaz.")
        while not _stop_vision_event.is_set():
            time.sleep(0.2)
        return

    cap = None
    try:
        import camera_utils
        cap, dev_id = camera_utils.open_camera(None)
    except Exception:
        try:
            cap = cv2.VideoCapture(0)
        except Exception:
            cap = None

    if cap is None or not cap.isOpened():
        logger.warning("No se pudo abrir la cámara web para el traductor en tiempo real.")
        err_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(err_frame, "Camara no disponible en servidor", (30, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        ok, buf = cv2.imencode(".jpg", err_frame)
        if ok:
            with _frame_lock:
                _latest_mjpeg_frame = buf.tobytes()
        return

    logger.info("[OK] Captura de camara iniciada para el traductor en vivo con IA.")

    try:
        while not _stop_vision_event.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            frame = cv2.flip(frame, 1)

            if _translator is not None:
                try:
                    label, confidence, results, confirmed = _translator.predict(frame)
                    frame = _translator.draw_overlay(frame, label, confidence, results, confirmed)

                    if confirmed:
                        logger.info("[OK] Sena real confirmada por IA: '%s' (confianza: %.2f)", confirmed, confidence)
                        if _main_event_loop and _main_event_loop.is_running():
                            asyncio.run_coroutine_threadsafe(
                                notificar_traduccion(confirmed, confidence),
                                _main_event_loop
                            )

                        if _virtual_cam and _virtual_cam.is_active:
                            _virtual_cam.on_translation_confirmed(confirmed, confidence)
                except Exception as e:
                    logger.debug("Error en inferencia de frame: %s", e)

            if _virtual_cam and _virtual_cam.is_active:
                try:
                    _virtual_cam.send_frame(frame)
                except Exception:
                    pass

            ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 68])
            if ok:
                with _frame_lock:
                    _latest_mjpeg_frame = buffer.tobytes()

            time.sleep(0.015)  # ~30 FPS

    finally:
        if cap is not None:
            cap.release()
        logger.info("Hilo de visión y traducción detenido.")


def generar_frames():
    """Generador que produce frames JPEG en formato multipart (MJPEG) desde el feed real de IA."""
    while True:
        frame_bytes = None
        with _frame_lock:
            frame_bytes = _latest_mjpeg_frame

        if frame_bytes is None:
            time.sleep(0.04)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        time.sleep(0.033)  # ~30 FPS


# --- RUTAS DE NAVEGACIÓN Y AUTENTICACIÓN ---


@app.get("/")
def index(request: Request):
    """Ruta raíz: redirige a /viewer si está autenticado, o a /login si no."""
    if is_authenticated_request(request):
        return RedirectResponse(url="/viewer", status_code=status.HTTP_303_SEE_OTHER)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if request.cookies.get(COOKIE_NAME):
        response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


@app.get("/auth/qr")
@limiter.limit("5/minute")
def auth_qr(request: Request, token: Optional[str] = None):
    """
    Autenticación transparente mediante escaneo de Código QR.
    Valida el token efímero, setea la cookie HttpOnly y redirige a /viewer.
    Protegido con rate limit de 5 peticiones por minuto.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"

    if not token or not session_manager.validate_token(token):
        logger.warning("Intento de acceso por QR con token inválido desde IP %s.", client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de acceso inválido o expirado. Verifique el código QR generado en la aplicación.",
        )

    # Crear nueva sesión
    session_id = session_manager.create_session(client_ip)
    if not session_id:
        return RedirectResponse(url="/login?error=max_sessions", status_code=status.HTTP_303_SEE_OTHER)

    response = RedirectResponse(url="/viewer", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=session_manager.ttl_seconds,
    )
    logger.info("Autenticación exitosa por QR desde IP %s.", client_ip)
    return response


@app.get("/login")
@limiter.limit("60/minute")
def login_get(request: Request):
    """Sirve la pantalla minimalista para ingresar el PIN numérico de acceso."""
    if is_authenticated_request(request):
        return RedirectResponse(url="/viewer", status_code=status.HTTP_303_SEE_OTHER)

    login_path = os.path.join(os.path.dirname(__file__), "login.html")
    if not os.path.exists(login_path):
        login_path = "login.html"
    response = FileResponse(login_path, media_type="text/html")
    if request.cookies.get(COOKIE_NAME):
        response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


@app.post("/login")
@limiter.limit("5/minute")
async def login_post(request: Request):
    """
    Valida el PIN de 6 dígitos con rate limit estricto anti-fuerza bruta.
    Emite la cookie de sesión y redirige al visor.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    pin_ingresado = None

    content_type = request.headers.get("content-type", "")

    # 1. Intentar extraer de JSON si la petición lo declara
    if "application/json" in content_type:
        try:
            body = await request.json()
            pin_ingresado = body.get("pin")
        except Exception:
            pin_ingresado = None

    # 2. Parseo nativo de application/x-www-form-urlencoded (evita depender de librerías externas)
    if not pin_ingresado:
        try:
            raw_body = await request.body()
            parsed = parse_qs(raw_body.decode("utf-8"))
            if "pin" in parsed and parsed["pin"]:
                pin_ingresado = parsed["pin"][0]
        except Exception:
            pass

    # 3. Respaldo adicional con request.form()
    if not pin_ingresado:
        try:
            form = await request.form()
            pin_ingresado = form.get("pin")
        except Exception:
            pass

    pin_str = str(pin_ingresado).strip() if pin_ingresado is not None else ""

    if not pin_str or not session_manager.validate_pin(pin_str):
        logger.warning("Fallo de autenticación con PIN desde IP %s.", client_ip)
        if "application/json" in content_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="PIN incorrecto.",
            )
        response = RedirectResponse(url="/login?error=invalid_pin", status_code=status.HTTP_303_SEE_OTHER)
        if request.cookies.get(COOKIE_NAME):
            response.delete_cookie(key=COOKIE_NAME, path="/")
        return response

    # Crear sesión activa
    session_id = session_manager.create_session(client_ip)
    if not session_id:
        if "application/json" in content_type:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Límite de sesiones concurrentes alcanzado (máx. 2).",
            )
        return RedirectResponse(url="/login?error=max_sessions", status_code=status.HTTP_303_SEE_OTHER)

    if "application/json" in content_type:
        res = JSONResponse({"status": "ok", "message": "Autenticado correctamente."})
    else:
        res = RedirectResponse(url="/viewer", status_code=status.HTTP_303_SEE_OTHER)

    res.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=session_manager.ttl_seconds,
    )
    logger.info("Autenticación exitosa por PIN desde IP %s.", client_ip)
    return res


@app.get("/viewer")
@limiter.limit("60/minute")
def viewer_get(request: Request):
    """
    Sirve la página del visor en vivo.
    Requiere cookie de sesión válida; si no existe, redirige a /login eliminando cookies viejas.
    """
    if not is_authenticated_request(request):
        response = RedirectResponse(url="/login?error=unauthorized", status_code=status.HTTP_303_SEE_OTHER)
        if request.cookies.get(COOKIE_NAME):
            response.delete_cookie(key=COOKIE_NAME, path="/")
        return response

    visor_path = os.path.join(os.path.dirname(__file__), "visor.html")
    if not os.path.exists(visor_path):
        visor_path = "visor.html"
    return FileResponse(visor_path, media_type="text/html")


@app.get("/logout")
@app.post("/logout")
def logout(request: Request):
    """Invalida la sesión actual y elimina la cookie en el cliente."""
    session_id = request.cookies.get(COOKIE_NAME)
    session_manager.revoke_session(session_id)

    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


@app.get("/api/info")
def api_info(request: Request):
    """Devuelve metadatos del modelo preentrenado activo y estado del sistema."""
    if not is_authenticated_request(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Acceso denegado.")

    words = []
    if _translator and hasattr(_translator, "meta"):
        words = _translator.meta.get("words", [])

    return {
        "status": "online",
        "model_loaded": _translator is not None,
        "pretrained_words": words,
        "ip": request.client.host if request.client else "unknown",
    }


# --- STREAM DE VIDEO OPCIONAL ---


@app.get("/stream")
def stream(request: Request):
    """Transmite video MJPEG de la cámara si la sesión está autenticada."""
    if not is_authenticated_request(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Acceso denegado.")

    return StreamingResponse(
        generar_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# --- WEBSOCKET DE TRADUCCIÓN CON CONTROL DE ACCESO ---


@app.websocket("/ws/translations")
async def ws_translations(websocket: WebSocket):
    """
    Canal WebSocket para difusión en tiempo real de palabras traducidas.
    Valida la cookie de sesión o token en el handshake.
    Rechaza de inmediato con código 1008 si no está autenticado.
    """
    # 1. Validación estricta en el Handshake
    if not verify_ws_session(websocket):
        client_ip = websocket.client.host if websocket.client else "desconocido"
        logger.warning("Intento de conexión WebSocket no autorizada desde %s.", client_ip)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="No autorizado")
        return

    await websocket.accept()
    clientes_conectados.append(websocket)
    client_ip = websocket.client.host if websocket.client else "desconocido"
    logger.info("Cliente WebSocket autenticado conectado desde %s. Total: %d", client_ip, len(clientes_conectados))

    try:
        while True:
            # Mantener la conexión abierta para recibir pings o desconexiones
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in clientes_conectados:
            clientes_conectados.remove(websocket)
        logger.info("Cliente WebSocket desconectado. Restantes: %d", len(clientes_conectados))
    except Exception as e:
        if websocket in clientes_conectados:
            clientes_conectados.remove(websocket)
        logger.debug("Excepción en canal WebSocket: %s", e)


# --- DIFUSIÓN Y SANITIZACIÓN DE TRADUCCIONES ---


async def notificar_traduccion(word: str, confidence: float, timestamp: Optional[str] = None):
    """
    Sanitiza la palabra confirmada y la transmite a los visores remotos autenticados.
    Integrable con el callback on_translation_confirmed de EVENTOS.md.
    """
    # 1. Sanitización estricta anti-XSS antes del broadcast
    safe_word = sanitize_word(word)
    safe_timestamp = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    payload = json.dumps({
        "word": safe_word,
        "confidence": round(float(confidence), 2),
        "timestamp": safe_timestamp,
    })

    for cliente in clientes_conectados.copy():
        try:
            await cliente.send_text(payload)
        except Exception:
            if cliente in clientes_conectados:
                clientes_conectados.remove(cliente)


# --- CICLO DE VIDA DEL SERVIDOR Y PIPELINE DE IA ---


@app.on_event("startup")
async def startup_event():
    """Inicializa el modelo de IA real de señas y arranca el pipeline de visión."""
    global _main_event_loop, _translator, _virtual_cam, _vision_thread

    _main_event_loop = asyncio.get_running_loop()
    logger.info("HandTalk WebServer iniciado.")
    logger.info("Token efímero de sesión: %s", session_manager.session_token)
    logger.info("PIN numérico de acceso:   %s", session_manager.pin)

    # Cargar el modelo preentrenado real del proyecto
    models_dir = os.path.join(PROJECT_ROOT, "models")
    try:
        from realtime_translator import CustomSignTranslator
        _translator = CustomSignTranslator(models_dir=models_dir)
        logger.info(
            "[OK] Modelo IA de senas preentrenadas cargado con exito. Senas reconocibles: %s",
            _translator.meta.get("words", []),
        )
    except Exception as e:
        logger.warning("No se pudo cargar el clasificador de señas (%s). Verifique el directorio ./models.", e)
        _translator = None

    # Inicializar gestor de cámara virtual
    try:
        from virtual_cam import VirtualCamManager
        _virtual_cam = VirtualCamManager(width=640, height=480, fps=30)
    except Exception:
        _virtual_cam = None

    # Iniciar pipeline de visión en hilo secundario (no bloqueante)
    _stop_vision_event.clear()
    _vision_thread = threading.Thread(target=_vision_pipeline_worker, daemon=True)
    _vision_thread.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Libera la cámara y detiene los hilos de inferencia."""
    global _vision_thread
    logger.info("Deteniendo servidor web y liberando cámara...")
    _stop_vision_event.set()
    if _vision_thread and _vision_thread.is_alive():
        _vision_thread.join(timeout=2.0)


if __name__ == "__main__":
    import uvicorn
    import qr_generator

    # Generar y mostrar el Código QR directamente en la terminal
    info = qr_generator.generar_info_visor(
        token=session_manager.session_token,
        pin=session_manager.pin,
    )
    print("=" * 65)
    print("       HandTalk — Servidor Web y Visor Remoto en Red Local")
    print("=" * 65)
    print(f"IP Local Detectada:    {info['ip']}")
    print(f"Puerto de Servicio:    {info['puerto']}")
    print(f"PIN de Acceso Manual:  {session_manager.pin}")
    print(f"Enlace Directo / Web:  {info['url_directa']}")
    print(f"URL de Acceso QR:      {info['url_qr']}")
    print(f"Código QR guardado en: {info['archivo_qr']}")
    print("-" * 65)
    print("Escanee este Código QR desde el celular (misma red Wi-Fi):")
    qr_generator.mostrar_qr_en_terminal(info["url_qr"])
    print("=" * 65)
    print("Iniciando servidor en http://0.0.0.0:8000 (Presione CTRL+C para detener)")

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)