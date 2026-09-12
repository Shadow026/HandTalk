"""
Script para generar el código QR con el enlace de acceso al visor de HandTalk.

Detecta automáticamente la IP de la PC dentro de la red local (LAN),
sin necesidad de escribirla a mano ni de tocar la tabla de rutas
ni el gateway de Internet.

Requiere: qrcode, pillow
    pip install qrcode[pil]
"""

import socket
import qrcode

PUERTO = 8000  # Debe coincidir con el puerto donde corre uvicorn


def obtener_ip_local() -> str:
    """
    Detecta la IP local de la interfaz que tiene salida a Internet,
    SIN enviar ningún paquete real. Se abre un socket UDP hacia una
    IP externa (8.8.8.8) solo para que el sistema operativo elija
    la interfaz de salida; luego se lee esa IP con getsockname().
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip_local = s.getsockname()[0]
    except Exception:
        # Si falla (sin red, por ejemplo), usamos localhost como respaldo
        ip_local = "127.0.0.1"
    finally:
        s.close()
    return ip_local


def generar_qr(url: str, nombre_archivo: str = "qr_visor.png"):
    """Genera una imagen PNG con el QR del enlace."""
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
    """Imprime el QR directamente en la terminal, sin necesidad de abrir un archivo."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def main():
    ip = obtener_ip_local()
    url = f"http://{ip}:{PUERTO}"

    print(f"IP detectada:  {ip}")
    print(f"Enlace visor:  {url}")
    print()

    archivo = generar_qr(url)
    print(f"QR guardado en: {archivo}")
    print()
    print("Escanéalo desde el celular (misma red Wi-Fi):")
    print()
    mostrar_qr_en_terminal(url)


if __name__ == "__main__":
    main()