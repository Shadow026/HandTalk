#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inicio/web_security/auth.py
Gestión de credenciales efímeras, control de sesiones y autenticación.

Responsable: Jason (Seguridad, Redes y Sistemas)
Punto 4.3 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.
"""

import logging
import secrets
import time
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, WebSocket, status

logger = logging.getLogger("HandTalk.Security.Auth")

# Constantes de configuración de seguridad
COOKIE_NAME = "session_id"
MAX_ACTIVE_SESSIONS = 2
DEFAULT_SESSION_TTL_SECONDS = 7200  # 2 horas


class SessionManager:
    """
    Administrador centralizado de sesiones en memoria, tokens efímeros y PINs.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._active_sessions: Dict[str, dict] = {}
        # Credenciales maestras generadas al arrancar
        self.session_token: str = secrets.token_urlsafe(32)
        self.pin: str = f"{secrets.randbelow(1000000):06d}"
        self.credentials_created_at: float = time.time()
        logger.info("Credenciales efímeras inicializadas. PIN: %s", self.pin)

    def regenerate_credentials(self) -> Tuple[str, str]:
        """
        Regenera el token y PIN de acceso, invalidando todas las sesiones existentes.

        Returns:
            Tuple[str, str]: (nuevo_token, nuevo_pin)
        """
        self._active_sessions.clear()
        self.session_token = secrets.token_urlsafe(32)
        self.pin = f"{secrets.randbelow(1000000):06d}"
        self.credentials_created_at = time.time()
        logger.info("Credenciales regeneradas. Todas las sesiones activas fueron revocadas. Nuevo PIN: %s", self.pin)
        return self.session_token, self.pin

    def clean_expired_sessions(self) -> None:
        """Elimina sesiones cuya vigencia haya expirado."""
        now = time.time()
        expired = [sid for sid, data in self._active_sessions.items() if data["expires_at"] <= now]
        for sid in expired:
            del self._active_sessions[sid]
        if expired:
            logger.debug("Se limpiaron %d sesiones expiradas.", len(expired))

    def get_active_sessions_count(self) -> int:
        """Retorna la cantidad actual de sesiones válidas."""
        self.clean_expired_sessions()
        return len(self._active_sessions)

    def validate_token(self, token: Optional[str]) -> bool:
        """Compara un token suministrado de forma segura contra tiempo de ejecución."""
        if not token:
            return False
        return secrets.compare_digest(token.strip(), self.session_token)

    def validate_pin(self, pin: Optional[str]) -> bool:
        """Compara un PIN suministrado de forma segura contra tiempo de ejecución."""
        if not pin:
            return False
        return secrets.compare_digest(str(pin).strip(), self.pin)

    def create_session(self, client_ip: str) -> Optional[str]:
        """
        Crea una nueva sesión si el límite estricto de concurrencia lo permite.

        Args:
            client_ip: Dirección IP del cliente solicitante.

        Returns:
            Optional[str]: ID de sesión generado o None si se alcanzó el límite.
        """
        self.clean_expired_sessions()
        if len(self._active_sessions) >= MAX_ACTIVE_SESSIONS:
            logger.warning(
                "Intento de inicio de sesión rechazado desde %s: Límite de %d sesiones activas alcanzado.",
                client_ip,
                MAX_ACTIVE_SESSIONS,
            )
            return None

        session_id = secrets.token_hex(24)
        now = time.time()
        self._active_sessions[session_id] = {
            "created_at": now,
            "expires_at": now + self.ttl_seconds,
            "client_ip": client_ip,
        }
        logger.info(
            "Sesión creada para IP %s (Activas: %d/%d).",
            client_ip,
            len(self._active_sessions),
            MAX_ACTIVE_SESSIONS,
        )
        return session_id

    def validate_session(self, session_id: Optional[str]) -> bool:
        """Verifica si un session_id está activo y no ha expirado."""
        if not session_id:
            return False
        self.clean_expired_sessions()
        session_data = self._active_sessions.get(session_id)
        if not session_data:
            return False
        if session_data["expires_at"] <= time.time():
            self._active_sessions.pop(session_id, None)
            return False
        return True

    def revoke_session(self, session_id: Optional[str]) -> bool:
        """Revoca y elimina una sesión activa."""
        if session_id and session_id in self._active_sessions:
            del self._active_sessions[session_id]
            logger.info("Sesión %s revocada exitosamente.", session_id[:8])
            return True
        return False


# Instancia singleton del gestor de sesiones
_session_manager_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Obtiene la instancia única del SessionManager."""
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager()
    return _session_manager_instance


# --- Dependencias de Seguridad para FastAPI ---


def verify_session_cookie(request: Request) -> str:
    """
    Dependencia FastAPI para proteger endpoints HTTP.
    Verifica la cookie 'session_id'. Si no es válida, lanza HTTPException 401.
    """
    manager = get_session_manager()
    session_id = request.cookies.get(COOKIE_NAME)

    if not manager.validate_session(session_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida o expirada. Por favor inicie sesión con el PIN o Código QR.",
        )
    return session_id


def is_authenticated_request(request: Request) -> bool:
    """Verifica de forma booleana si la petición contiene una sesión activa."""
    manager = get_session_manager()
    session_id = request.cookies.get(COOKIE_NAME)
    return manager.validate_session(session_id)


def verify_ws_session(websocket: WebSocket) -> bool:
    """
    Verifica la autenticación durante el handshake del WebSocket.
    Acepta la cookie 'session_id' o el query parameter '?token=...'.
    """
    manager = get_session_manager()

    # 1. Comprobar cookie de sesión
    session_id = websocket.cookies.get(COOKIE_NAME)
    if manager.validate_session(session_id):
        return True

    # 2. Comprobar query parameter con token directo
    token = websocket.query_params.get("token")
    if manager.validate_token(token):
        return True

    return False
