"""Protocole série des appareils Divoom en Bluetooth : Timebox Evo, Pixoo 16×16 (Python pur).

Trame : ``01 | LLLL | payload | CRCR | 02``

- ``LLLL`` : longueur du payload + 2 (checksum), petit-boutiste ;
- ``CRCR`` : somme des octets de ``LLLL + payload`` sur 16 bits, petit-boutiste ;
- pas d'échappement sur l'Evo.

Les réponses de l'appareil ont pour payload ``04 | commande | 55 | données``.
Voir docs/protocol.md pour la description du protocole et les observations.
"""

from dataclasses import dataclass

START = 0x01
END = 0x02
RESPONSE = 0x04
ACK = 0x55

SET_VIEW = 0x45
GET_VIEW = 0x46
SET_BRIGHTNESS = 0x74
LIGHT_STATUS = 0x31
LIGHTNESS_STATUS = 0x32

VIEW_CLOCK = 0x00
VIEW_LIGHT = 0x01

IMAGE = 0x44

# Les accusés varient selon l'appareil (le Pixoo n'acquitte ni 44 ni 45) : chaque commande est
# confirmée par la lecture de l'état (46) qui la suit (bluetooth.device.BluetoothDevice._apply).


def checksum(body: bytes) -> int:
    return sum(body) & 0xFFFF


def encode(payload: bytes) -> bytes:
    """Encapsule un payload dans une trame complète."""
    body = (len(payload) + 2).to_bytes(2, "little") + payload
    return bytes([START]) + body + checksum(body).to_bytes(2, "little") + bytes([END])


@dataclass(frozen=True)
class Response:
    command: int
    status: int
    data: bytes

    @property
    def ok(self) -> bool:
        return self.status == ACK


def parse_response(frame: bytes) -> Response | None:
    """Décode une trame de réponse (``04 | commande | statut | données``), sinon None."""
    payload = frame[3:-3]
    if len(payload) < 3 or payload[0] != RESPONSE:
        return None
    return Response(command=payload[1], status=payload[2], data=bytes(payload[3:]))


class FrameDecoder:
    """Reconstitue les trames à partir d'un flux d'octets arrivant par morceaux.

    Les octets parasites avant un ``01`` sont ignorés ; une trame dont la fin ou le
    checksum est invalide est abandonnée et le décodage reprend à l'octet suivant.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self._buffer.extend(data)
        frames: list[bytes] = []
        while True:
            start = self._buffer.find(START)
            if start < 0:
                self._buffer.clear()
                break
            del self._buffer[:start]
            if len(self._buffer) < 3:
                break
            length = int.from_bytes(self._buffer[1:3], "little")
            end = 3 + length  # index de l'octet 02
            if len(self._buffer) < end + 1:
                break
            frame = bytes(self._buffer[:end + 1])
            body, crc = frame[1:-3], int.from_bytes(frame[-3:-1], "little")
            if length < 2 or frame[-1] != END or checksum(body) != crc:
                del self._buffer[:1]  # resynchronisation
                continue
            frames.append(frame)
            del self._buffer[:end + 1]
        return frames


# --- Construction des commandes (payloads) -------------------------------------------

def _level(value: int) -> int:
    if not 0 <= value <= 100:
        raise ValueError(f"valeur hors de 0..100 : {value}")
    return value


def get_view() -> bytes:
    return bytes([GET_VIEW])


def set_view(view: int) -> bytes:
    return bytes([SET_VIEW, view])


def set_brightness(level: int) -> bytes:
    return bytes([SET_BRIGHTNESS, _level(level)])


def set_clock(color: bytes, style: int = 0, time: bool = True, weather: bool = False,
              temperature: bool = False, calendar: bool = False) -> bytes:
    """Écran « horloge » complet : ``45 00 01 TT XX WW EE CC RRGGBB`` (style, heure, météo,
    température, calendrier, couleur) ; « 45 00 » seul reprend les réglages en place."""
    if len(color) != 3:
        raise ValueError("la couleur doit faire 3 octets")
    return bytes([SET_VIEW, VIEW_CLOCK, 1, style, time, weather, temperature, calendar]) + color


def set_light(color: bytes, brightness: int = 100, effect: int = 0, power: bool = True) -> bytes:
    """Écran « lumière » : couleur unie (effect=0) ou effet."""
    if len(color) != 3:
        raise ValueError("la couleur doit faire 3 octets")
    return bytes([SET_VIEW, VIEW_LIGHT]) + color + bytes(
        [_level(brightness), effect, 1 if power else 0, 0, 0, 0])


# --- Images 16×16 (commande 44) -------------------------------------------------------
#
# Validé sur l'appareil (docs/protocol.md) : 1 à 256 couleurs, T=0000 pour une image fixe,
# R doit valoir 00 (avec R=01 l'image n'est pas affichée), ordre des pixels x + 16·y.

IMAGE_HEADER = bytes([IMAGE, 0x00, 0x0A, 0x0A, 0x04])
FRAME_START = 0xAA
SIZE = 16
PIXELS = SIZE * SIZE


def bits_per_pixel(colors: int) -> int:
    return max(1, (colors - 1).bit_length())


def encode_frame(pixels: list[bytes], duration_ms: int = 0, reset_palette: bool = False) -> bytes:
    """Frame ``aa | LLLL | TTTT | RR | NN | couleurs | pixels`` (format commun image/animation).

    ``pixels`` : 256 couleurs RGB de 3 octets, ligne par ligne (index ``x + 16·y``).
    Les index de palette sont regroupés sur ``bits_per_pixel`` bits, poids faible en premier.
    """
    if len(pixels) != PIXELS:
        raise ValueError(f"une image fait {PIXELS} pixels, pas {len(pixels)}")
    palette: dict[bytes, int] = {}
    for color in pixels:
        if len(color) != 3:
            raise ValueError("chaque pixel doit faire 3 octets (RGB)")
        palette.setdefault(bytes(color), len(palette))
    bits = bits_per_pixel(len(palette))

    packed = bytearray()
    acc = filled = 0
    for color in pixels:
        acc |= palette[bytes(color)] << filled
        filled += bits
        while filled >= 8:
            packed.append(acc & 0xFF)
            acc >>= 8
            filled -= 8
    if filled:
        packed.append(acc & 0xFF)

    body = (duration_ms.to_bytes(2, "little") + bytes([1 if reset_palette else 0, len(palette) & 0xFF])
            + b"".join(palette) + bytes(packed))
    return bytes([FRAME_START]) + (len(body) + 3).to_bytes(2, "little") + body


def decode_frame(frame: bytes) -> tuple[list[bytes], int]:
    """Inverse de encode_frame : renvoie (256 pixels RGB, durée en ms)."""
    if frame[0] != FRAME_START:
        raise ValueError("début de frame absent (aa)")
    duration = int.from_bytes(frame[3:5], "little")
    colors = frame[6] or 256
    palette = [bytes(frame[7 + 3 * i:10 + 3 * i]) for i in range(colors)]
    data = frame[7 + 3 * colors:]
    bits, mask = bits_per_pixel(colors), (1 << bits_per_pixel(colors)) - 1
    value = int.from_bytes(data, "little")
    return [palette[(value >> (i * bits)) & mask] for i in range(PIXELS)], duration


def set_image(pixels: list[bytes]) -> bytes:
    """Image fixe : T=0, R=00 (seule combinaison validée pour l'affichage)."""
    return IMAGE_HEADER + encode_frame(pixels)


# --- Décodage de l'état (réponse à GET_VIEW) -----------------------------------------

@dataclass(frozen=True)
class Clock:
    """Réglages de l'écran horloge (octets 12 à 19 de la réponse 46)."""
    color: str
    style: int
    time: bool
    weather: bool
    temperature: bool
    calendar: bool


@dataclass(frozen=True)
class DeviceState:
    view: int
    light_color: str
    brightness: int
    power: bool
    raw: str
    clock: Clock | None = None


def parse_state(data: bytes) -> DeviceState:
    """Décode les données d'une réponse 46 (interprétation partielle, cf. docs/protocol.md)."""
    if len(data) < 9:
        raise ValueError(f"état trop court ({len(data)} octets)")
    clock = None
    if len(data) >= 20:
        clock = Clock(color=data[12:15].hex(), style=data[15], time=data[16] == 1, weather=data[17] == 1,
                      temperature=data[18] == 1, calendar=data[19] == 1)
    return DeviceState(
        view=data[0],
        light_color=data[3:6].hex(),
        brightness=data[6],
        power=data[8] == 1,
        raw=data.hex(" "),
        clock=clock,
    )
