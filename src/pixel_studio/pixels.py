"""Images communes à tous les appareils : couleurs « rrggbb », pixels ligne par ligne (x + taille·y).

Deux tailles : 16×16 (Timebox Evo, Pixoo) et 64×64 (Pixoo-64). La taille se déduit du nombre de
pixels ; une image ne change de taille que par une conversion explicite (`resize`).
"""

from collections import Counter

SIZES = (16, 64)


def parse_color(rgb: str) -> bytes:
    """« ff8800 » ou « #FF8800 » → 3 octets."""
    value = rgb.removeprefix("#")
    try:
        if len(value) != 6:
            raise ValueError
        return bytes.fromhex(value)
    except ValueError:
        raise ValueError(f"couleur invalide (attendu RRGGBB) : {rgb}") from None


def size_of(colors: list) -> int:
    """Taille (côté) d'une image d'après son nombre de pixels."""
    for size in SIZES:
        if len(colors) == size * size:
            return size
    expected = " ou ".join(f"{s * s} ({s}×{s})" for s in SIZES)
    raise ValueError(f"une image fait {expected} pixels, pas {len(colors)}")


def parse_pixels(colors: list[str], size: int | None = None) -> list[bytes]:
    """Couleurs « rrggbb » (ou « #rrggbb ») → octets RGB ; ``size`` impose une taille."""
    if size is None:
        size_of(colors)
    elif len(colors) != size * size:
        raise ValueError(f"une image {size}×{size} fait {size * size} pixels, pas {len(colors)}")
    return [parse_color(c) for c in colors]


def resize(colors: list[str], size: int) -> list[str]:
    """Convertit une image à une autre taille.

    Agrandissement : chaque pixel devient un carré (plus proche voisin : le pixel art reste net).
    Réduction : chaque bloc prend sa couleur la plus fréquente (la palette est conservée ; à égalité,
    la première rencontrée dans l'ordre de lecture du bloc).
    """
    if size not in SIZES:
        raise ValueError(f"taille inconnue : {size} (attendu : {', '.join(map(str, SIZES))})")
    source = size_of(colors)
    if size == source:
        return list(colors)
    if size > source:
        factor = size // source
        return [colors[(x // factor) + source * (y // factor)] for y in range(size) for x in range(size)]
    factor = source // size
    result = []
    for y in range(size):
        for x in range(size):
            block = [colors[(x * factor + dx) + source * (y * factor + dy)]
                     for dy in range(factor) for dx in range(factor)]
            result.append(Counter(block).most_common(1)[0][0])
    return result
