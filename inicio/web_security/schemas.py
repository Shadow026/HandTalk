#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inicio/web_security/schemas.py
Esquemas Pydantic y utilidades de sanitización contra XSS.

Responsable: Jason (Seguridad, Redes y Sistemas)
Punto 4.3 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.
"""

import html
import time
from typing import Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """
    Esquema de validación estricta para el PIN numérico de acceso.
    Debe constar exactamente de 6 dígitos numéricos.
    """
    pin: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="PIN numérico de acceso de 6 dígitos generado por HandTalk",
        examples=["123456"],
    )


class TranslationPayload(BaseModel):
    """
    Esquema del payload transmitido por WebSocket y emitido según EVENTOS.md.
    """
    word: str = Field(..., description="Palabra o etiqueta de la seña confirmada")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Nivel de certeza de 0.0 a 1.0")
    timestamp: Optional[str] = Field(default=None, description="Marca de tiempo ISO 8601")


def sanitize_word(word: Optional[str]) -> str:
    """
    Sanitiza estrictamente una palabra o texto antes de inyectarla al canal
    WebSocket o plantilla HTML, neutralizando caracteres como <, >, &, ", '.

    Args:
        word: Texto crudo a sanitizar.

    Returns:
        str: Texto escapado en entidades HTML seguro contra XSS.
    """
    if not word:
        return ""
    # Strip y escape estricto
    clean_text = str(word).strip()
    return html.escape(clean_text, quote=True)
