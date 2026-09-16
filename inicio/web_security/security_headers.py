#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inicio/web_security/security_headers.py
Middleware ASGI para inyección de cabeceras de blindaje HTTP (CSP, XSS, Clickjacking).

Responsable: Jason (Seguridad, Redes y Sistemas)
Punto 4.3 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Política de Seguridad del Contenido (CSP)
# Restringe conexiones de scripts, estilos, orígenes de frames y WebSockets a sí mismo.
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self' ws:; "
    "frame-ancestors 'none'; "
    "object-src 'none';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware que intercepta todas las respuestas HTTP para inyectar
    cabeceras estándar de ciberseguridad recomendadas por OWASP.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Inyección de cabeceras de seguridad
        response.headers["Content-Security-Policy"] = CSP_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Prevención de caché para evitar que el navegador reutilice sesiones inválidas o datos obsoletos
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response
