#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inicio/web_security
Paquete modular de seguridad para el servidor web FastAPI de HandTalk.

Responsable: Jason (Seguridad, Redes y Sistemas)
Punto 4.3 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.
"""

from .auth import (
    COOKIE_NAME,
    MAX_ACTIVE_SESSIONS,
    SessionManager,
    get_session_manager,
    is_authenticated_request,
    verify_session_cookie,
    verify_ws_session,
)
from .rate_limiter import limiter, rate_limit_exceeded_handler
from .schemas import LoginRequest, TranslationPayload, sanitize_word
from .security_headers import SecurityHeadersMiddleware

__all__ = [
    "COOKIE_NAME",
    "MAX_ACTIVE_SESSIONS",
    "SessionManager",
    "get_session_manager",
    "verify_session_cookie",
    "is_authenticated_request",
    "verify_ws_session",
    "limiter",
    "rate_limit_exceeded_handler",
    "SecurityHeadersMiddleware",
    "LoginRequest",
    "TranslationPayload",
    "sanitize_word",
]
