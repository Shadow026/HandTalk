#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qr_generator.py
Script y utilidades de Red y Generación de Códigos QR para HandTalk.

Responsable: Jason (Seguridad, Redes y Sistemas)
Punto 4.3 de PLAN_DE_TRABAJO_EQUIPO.md y plan_integracion.MD.

Principios:
1. Detección automática de la IP de la interfaz LAN activa vía socket UDP (8.8.8.8:80),
   garantizando que la tabla de rutas y la conexión a Internet del host no se toquen.
2. Sincronización criptográfica con auth.py: la URL del QR contiene el token efímero
   (/auth/qr?token=...) y se provee el PIN de 6 dígitos como alternativa accesible.
"""

import os
import socket
from typing import Dict, Optional
import qrcode

PUERTO = 8000  # Debe coincidir con el puerto donde escucha FastAPI / Uvicorn


def obtener_ip_local() -> str:
    """
    Detecta la IP local de la interfaz que tiene salida a Internet/Gateway,
    SIN enviar ningún paquete real por la red. Se abre un socket UDP hacia una
    IP externa (8.8.8.8:80) solo para que el kernel del sistema operativo elija
    la interfaz de red predeterminada; luego se lee esa IP con getsockname()[0].
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip_local = s.getsockname()[0]
    except Exception:
        # Respaldo si el equipo no está conectado a ninguna interfaz
        ip_local = "127.0.0.1"
    finally:
        s.close()
    return ip_local


def generar_qr(url: str, nombre_archivo: str = "qr_visor.png") -> str:
    """
    Genera una imagen PNG con el QR del enlace para acceso móvil.

    Args:
        url: URL completa con el token de acceso.
        nombre_archivo: Ruta donde se guardará la imagen.

    Returns:
        str: Ruta absoluta o relativa del archivo generado.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    imagen = qr.make_image(fill_color="black", back_color="white")
    imagen.save(nombre_archivo)
    return nombre_archivo


def mostrar_qr_en_terminal(url: str):
    """Imprime el QR directamente en la terminal en arte ASCII."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def obtener_credenciales_visor() -> Dict[str, str]:
    """
    Obtiene las credenciales activas del SessionManager de HandTalk.
    Si no está corriendo o no se puede importar, genera un par de prueba.
    """
    try:
        from inicio.web_security import get_session_manager
        manager = get_session_manager()
        return {
            "token": manager.session_token,
            "pin": manager.pin,
        }
    except Exception:
        import secrets
        return {
            "token": secrets.token_urlsafe(32),
            "pin": f"{secrets.randbelow(1000000):06d}",
        }


def generar_info_visor(
    nombre_archivo: str = "qr_visor.png",
    token: Optional[str] = None,
    pin: Optional[str] = None,
) -> Dict[str, str]:
    """
    Genera la información completa de acceso (IP, URL, Token, PIN y archivo QR).
    Ideal para ser invocada desde la GUI de escritorio o el servidor web.
    """
    ip = obtener_ip_local()
    creds = obtener_credenciales_visor()
    token_actual = token or creds["token"]
    pin_actual = pin or creds["pin"]

    url_qr = f"http://{ip}:{PUERTO}/auth/qr?token={token_actual}"
    url_directa = f"http://{ip}:{PUERTO}/login"

    archivo_guardado = generar_qr(url_qr, nombre_archivo)

    return {
        "ip": ip,
        "puerto": str(PUERTO),
        "url_qr": url_qr,
        "url_directa": url_directa,
        "token": token_actual,
        "pin": pin_actual,
        "archivo_qr": archivo_guardado,
    }


def main():
    info = generar_info_visor()

    print("=" * 65)
    print("       HandTalk — Visor Remoto en Red Local (Seguridad y Red)")
    print("=" * 65)
    print(f"IP Local Detectada:    {info['ip']}")
    print(f"Puerto de Servicio:    {info['puerto']}")
    print(f"PIN de Acceso Manual:  {info['pin']}")
    print(f"Enlace Directo / Web:  {info['url_directa']}")
    print(f"URL de Acceso QR:      {info['url_qr']}")
    print(f"Código QR guardado en: {info['archivo_qr']}")
    print("-" * 65)
    print("Escanee el siguiente Código QR con el celular (misma red Wi-Fi):")
    print()
    mostrar_qr_en_terminal(info["url_qr"])
    print("=" * 65)


if __name__ == "__main__":
    main()