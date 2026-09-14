#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inicio/web_security/rate_limiter.py
Configuración de Rate Limiting con SlowAPI para prevención de ataques DoS y fuerza bruta.

Responsable: Jason (Seguridad, Redes y Sistemas)
Punto 4.3 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.
"""

import logging
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger("HandTalk.Security.RateLimiter")


def get_client_ip(request: Request) -> str:
    """
    Obtiene la dirección IP real del cliente evitando cabeceras spoofeadas
    en redes locales a menos que se configure proxy confiable.
    """
    if request.client and request.client.host:
        return request.client.host
    return get_remote_address(request)


# Instancia central de rate limiter
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["60/minute"],
    headers_enabled=True,
    strategy="fixed-window",
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Manejador personalizado cuando un cliente excede la cuota de peticiones.
    Retorna HTTP 429 Too Many Requests con la cabecera Retry-After exigida.
    """
    client_ip = get_client_ip(request)
    logger.warning(
        "Rate limit excedido para IP %s en ruta '%s' (%s).",
        client_ip,
        request.url.path,
        exc.detail,
    )

    content = {
        "error": "Demasiadas peticiones (Rate limit excedido)",
        "detail": "Ha superado el límite de intentos permitidos. Intente nuevamente en 60 segundos.",
        "retry_after_seconds": 60,
        "path": request.url.path,
    }

    # Si es una petición HTML de navegador común, podemos devolver un HTML limpio
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header and not "application/json" in accept_header:
        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>429 - Demasiadas Peticiones | HandTalk</title>
    <style>
        body {{
            background: #121214;
            color: #f0f0f0;
            font-family: system-ui, -apple-system, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            text-align: center;
            padding: 20px;
        }}
        .card {{
            background: #1c1c24;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.5);
            max-width: 420px;
            border: 1px solid #ff4757;
        }}
        h1 {{ color: #ff4757; font-size: 24px; margin-top: 0; }}
        p {{ color: #a4b0be; line-height: 1.5; font-size: 15px; }}
        .timer {{ font-size: 13px; color: #747d8c; margin-top: 15px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Demasiadas Peticiones</h1>
        <p>Ha alcanzado el límite de intentos de seguridad para esta acción.</p>
        <p>Por favor, espere 60 segundos antes de volver a intentar.</p>
        <div class="timer">Código: HTTP 429 Too Many Requests</div>
    </div>
</body>
</html>"""
        return Response(
            content=html_content,
            status_code=429,
            media_type="text/html",
            headers={"Retry-After": "60"},
        )

    return JSONResponse(
        content=content,
        status_code=429,
        headers={"Retry-After": "60"},
    )
