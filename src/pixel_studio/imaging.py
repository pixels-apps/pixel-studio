"""Décodage d'images avec javax.imageio (interopérabilité Java, aucune dépendance Python native)."""

import java

ImageIO = java.type("javax.imageio.ImageIO")
ByteArrayInputStream = java.type("java.io.ByteArrayInputStream")
System = java.type("java.lang.System")

System.setProperty("java.awt.headless", "true")

def png_to_pixels(data, size: int) -> list[bytes]:
    """Image ``size``×``size`` (PNG, GIF, BMP, JPEG…) → size² × RGB, ligne par ligne.

    La transparence est composée sur fond noir (un pixel transparent = LED éteinte).
    ``data`` : bytes Python ou byte[] Java.
    """
    image = ImageIO.read(ByteArrayInputStream(data))
    if image is None:
        raise ValueError("format d'image non reconnu")
    if image.getWidth() != size or image.getHeight() != size:
        raise ValueError(f"l'image doit faire {size}×{size} pixels, pas "
                         f"{image.getWidth()}×{image.getHeight()}")
    pixels = []
    for y in range(size):
        for x in range(size):
            argb = image.getRGB(x, y) & 0xFFFFFFFF
            alpha = argb >> 24
            pixels.append(bytes(((argb >> shift) & 0xFF) * alpha // 255 for shift in (16, 8, 0)))
    return pixels
