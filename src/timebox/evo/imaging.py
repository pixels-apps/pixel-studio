"""Décodage d'images avec javax.imageio (interopérabilité Java, aucune dépendance Python native)."""

import java

ImageIO = java.type("javax.imageio.ImageIO")
ByteArrayInputStream = java.type("java.io.ByteArrayInputStream")
System = java.type("java.lang.System")

System.setProperty("java.awt.headless", "true")

SIZE = 16


def png_to_pixels(data) -> list[bytes]:
    """Image 16×16 (PNG, GIF, BMP, JPEG…) → 256 × RGB, ligne par ligne.

    La transparence est composée sur fond noir (un pixel transparent = LED éteinte).
    ``data`` : bytes Python ou byte[] Java.
    """
    image = ImageIO.read(ByteArrayInputStream(data))
    if image is None:
        raise ValueError("format d'image non reconnu")
    if image.getWidth() != SIZE or image.getHeight() != SIZE:
        raise ValueError(f"l'image doit faire {SIZE}×{SIZE} pixels, pas "
                         f"{image.getWidth()}×{image.getHeight()}")
    pixels = []
    for y in range(SIZE):
        for x in range(SIZE):
            argb = image.getRGB(x, y) & 0xFFFFFFFF
            alpha = argb >> 24
            pixels.append(bytes(((argb >> shift) & 0xFF) * alpha // 255 for shift in (16, 8, 0)))
    return pixels
