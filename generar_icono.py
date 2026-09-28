# generar_icono.py
"""
Script temporal para generar el ícono de MakeSign.
Ejecutar UNA SOLA VEZ: python generar_icono.py
Genera: assets/makesign.ico y assets/makesign.png
"""

import os
from PIL import Image, ImageDraw, ImageFont


def crear_icono_makesign(size=256):
    """
    Genera un ícono minimalista para MakeSign:
    - Fondo: degradado púrpura (color de marca)
    - Símbolo: Letra M estilizada blanca
    - Esquinas: redondeadas
    """
    # Crear imagen con fondo transparente
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Colores del degradado (púrpura principal → púrpura oscuro)
    color_top = (108, 92, 231)      # #6C5CE7
    color_bottom = (72, 52, 212)    # #4834D4

    # Dibujar degradado en franjas horizontales
    for y in range(size):
        t = y / size
        r = int(color_top[0] * (1 - t) + color_bottom[0] * t)
        g = int(color_top[1] * (1 - t) + color_bottom[1] * t)
        b = int(color_top[2] * (1 - t) + color_bottom[2] * t)
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Aplicar máscara de esquinas redondeadas
    radio = int(size * 0.22)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=radio,
        fill=255
    )

    # Combinar fondo con máscara
    fondo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fondo.paste(img, (0, 0), mask)

    # Dibujar la letra "M" en blanco
    draw = ImageDraw.Draw(fondo)

    # Intentar cargar fuente bold del sistema
    font = None
    rutas_fuentes = [
        "arialbd.ttf",                                          # Arial Bold (Windows)
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",                        # Segoe UI Bold
        "/System/Library/Fonts/Helvetica.ttc",                  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Linux
    ]
    font_size = int(size * 0.55)
    for ruta in rutas_fuentes:
        try:
            font = ImageFont.truetype(ruta, font_size)
            break
        except Exception:
            continue

    if font is None:
        font = ImageFont.load_default()

    texto = "M"
    bbox = draw.textbbox((0, 0), texto, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) / 2 - bbox[0]
    y = (size - text_height) / 2 - bbox[1] - int(size * 0.04)

    # Sombra sutil + texto principal
    draw.text((x + 3, y + 3), texto, font=font, fill=(0, 0, 0, 60))
    draw.text((x, y), texto, font=font, fill=(255, 255, 255, 255))

    return fondo


def main():
    print("Generando ícono de MakeSign...")

    # 1. Crear carpeta assets si no existe
    os.makedirs("assets", exist_ok=True)
    print("[OK] Carpeta assets/ verificada")

    # 2. Generar PNG 256x256
    img_256 = crear_icono_makesign(256)
    png_path = os.path.join("assets", "makesign.png")
    img_256.save(png_path, "PNG")
    print(f"[OK] PNG guardado: {png_path}")

    # 3. Generar ICO con múltiples tamaños
    ico_path = os.path.join("assets", "makesign.ico")
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    imagenes = [crear_icono_makesign(s[0]) for s in sizes]
    imagenes[0].save(
        ico_path,
        format="ICO",
        sizes=sizes,
        append_images=imagenes[1:]
    )
    print(f"[OK] ICO guardado: {ico_path}")

    print("\n[LISTO] El ícono está en la carpeta assets/")


if __name__ == "__main__":
    main()