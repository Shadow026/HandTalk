#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qr_generator.py
Módulo encargado de la generación de códigos QR y gestión de credenciales
para el Visor Web remoto de HandTalk.
"""

import os
import socket
import uuid
import qrcode
from PIL import Image
from typing import Optional

PUERTO = 8000

def obtener_ip_local():
    """
    Obtiene la dirección IP local de la máquina para que el usuario
    sepa a dónde conectarse desde el móvil.
    """
    try:
        # Creamos un socket UDP temporal para detectar la interfaz de red activa
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No es necesario que el host exista realmente, solo sirve para forzar la resolución de IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def generar_info_visor(token: Optional[str] = None, pin: Optional[str] = None):
    """
    Genera la información necesaria para la conexión remota:
    - Archivo de imagen QR.
    - PIN de acceso (se puede recibir uno ya generado por el SessionManager).
    - Puerto del servidor.

    Devuelve un diccionario con los datos.
    """
    from inicio.web_security.auth import get_session_manager

    # Si no se pasan credenciales, las obtenemos del SessionManager singleton
    if pin is None or token is None:
        sm = get_session_manager()
        pin = sm.pin
        token = sm.session_token

    ip = obtener_ip_local()
    puerto = PUERTO
    url_directa = f"http://{ip}:{puerto}/"
    url_qr = f"{url_directa}auth/qr?token={token}"

    # Crear el código QR con la URL que incluye el token para acceso directo
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url_qr)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Guardar el archivo QR en la raíz para que el menú pueda cargarlo
    ruta_qr = "qr_visor.png"
    img.save(ruta_qr)

    return {
        "archivo_qr": ruta_qr,
        "url": url_directa,
        "url_directa": url_directa,
        "url_qr": url_qr,
        "puerto": puerto,
        "pin": pin,
        "ip": ip
    }

if __name__ == "__main__":
    # Prueba rápida
    print(f"IP Local: {obtener_ip_local()}")
    info = generar_info_visor()
    print(f"Info Visor generada: {info}")
