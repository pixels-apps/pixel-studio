"""Appareils Divoom en Bluetooth (Timebox Evo, Pixoo 16×16), à travers le relais timebox-bridge.

Commandes, attente des réponses, décodage de l'état. Pyronaut fait tourner plusieurs contextes
GraalPy, et seul un @Singleton (ici le registre qui possède l'appareil) est partagé entre eux : le
verrou qui sérialise les échanges est donc un objet Java (ReentrantLock).
"""

import time

import java
from org.slf4j import LoggerFactory

from .. import device
from ..device import Device, DeviceState, DeviceUnavailable
from . import protocol
from .transport import Transport

ReentrantLock = java.type("java.util.concurrent.locks.ReentrantLock")

log = LoggerFactory.getLogger("pixel_studio.bluetooth")

VIEWS = {"clock": protocol.VIEW_CLOCK, "light": protocol.VIEW_LIGHT}
VIEW_NAMES = {code: name for name, code in VIEWS.items()}


class BluetoothDevice(Device):
    def __init__(self, device_id: str, name: str, transport: Transport, reply_timeout_ms: int):
        super().__init__(device_id, name)
        self.transport = transport
        self.reply_timeout_ms = reply_timeout_ms
        self.lock = ReentrantLock()
        self.decoder = protocol.FrameDecoder()

    kind = "bluetooth"
    size = protocol.SIZE

    @property
    def address(self) -> str:
        return str(self.transport)

    @property
    def capabilities(self) -> list[str]:
        return [device.COLOR, device.VIEWS]

    # --- Commandes --------------------------------------------------------------------

    def state(self) -> DeviceState:
        return _state(protocol.parse_state(self.exchange(protocol.get_view()).data))

    def set_color(self, color: bytes, brightness: int) -> DeviceState:
        return self._apply(protocol.set_light(color, brightness))

    def set_brightness(self, level: int) -> DeviceState:
        return self._apply(protocol.set_brightness(level))

    def set_view(self, view: str) -> DeviceState:
        """Change d'écran avec la commande complète et les réglages actuels (couleur, luminosité,
        style d'horloge) : la forme courte « 45 01 » éteint la lumière du Pixoo (luminosité 0)."""
        if view not in VIEWS:
            raise ValueError(f"écran inconnu : {view} (attendu : {', '.join(VIEWS)})")
        current = protocol.parse_state(self.exchange(protocol.get_view()).data)
        if view == "light":
            # octet de luminosité hors de 0..100 dans certains modes (« aa ») : valeur non décodée
            brightness = current.brightness if current.brightness <= 100 else 100
            return self.set_color(bytes.fromhex(current.light_color), brightness)
        if current.clock is None:  # état trop court pour connaître les réglages : forme courte
            return self._apply(protocol.set_view(protocol.VIEW_CLOCK))
        return self._apply(_clock(current.clock, bytes.fromhex(current.clock.color)))

    def set_clock_color(self, color: bytes) -> DeviceState:
        """Affiche l'horloge dans cette couleur, en gardant son style et ses options."""
        clock = protocol.parse_state(self.exchange(protocol.get_view()).data).clock
        return self._apply(_clock(clock, color) if clock else protocol.set_clock(color))

    def send_image(self, pixels: list[bytes]) -> None:
        self._apply(protocol.set_image(pixels))

    def close(self) -> None:
        self.transport.close()

    # --- Échange de trames ----------------------------------------------------------

    def _apply(self, payload: bytes) -> DeviceState:
        """Envoie une commande puis lit l'état : la réponse à 46, que l'appareil donne une fois la
        commande traitée, la confirme (les accusés varient : le Pixoo n'acquitte ni 44 ni 45)."""
        return _state(protocol.parse_state(self.exchange(protocol.get_view(), before=payload).data))

    def exchange(self, payload: bytes, before: bytes | None = None) -> protocol.Response:
        """Envoie une commande et attend la réponse de même code.

        ``before`` : commande envoyée juste avant, sans attendre de réponse (``payload`` sert alors
        de confirmation).
        """
        expected = payload[0]
        self.lock.lock()
        try:
            return self._exchange(payload, expected, before)
        except (DeviceUnavailable, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:  # sous GraalPy, une exception Java (IOException…) n'hérite pas
            # de la classe Python Exception : on intercepte large et on repart d'une connexion neuve
            log.warn("échange {} en échec : {}", payload.hex(" "), repr(e))
            self.transport.close()
            self.decoder = protocol.FrameDecoder()
            raise DeviceUnavailable(f"{self.transport} : {e}") from e
        finally:
            self.lock.unlock()

    def _exchange(self, payload: bytes, expected: int, before: bytes | None) -> protocol.Response:
        self.decoder.feed(self.transport.read_available())  # ignore les messages spontanés en attente
        if before is not None:
            self.transport.write(protocol.encode(before))
        self.transport.write(protocol.encode(payload))

        deadline = time.monotonic() + self.reply_timeout_ms / 1000
        while time.monotonic() < deadline:
            for frame in self.decoder.feed(self.transport.read_available()):
                reply = protocol.parse_response(frame)
                if reply is not None and reply.command == expected:
                    return reply
            time.sleep(0.01)
        raise DeviceUnavailable(f"pas de réponse {expected:02x} de l'appareil")


def _clock(clock: protocol.Clock, color: bytes) -> bytes:
    return protocol.set_clock(color, clock.style, clock.time, clock.weather, clock.temperature, clock.calendar)


def _state(s: protocol.DeviceState) -> DeviceState:
    return DeviceState(view=VIEW_NAMES.get(s.view, f"{s.view:02x}"), brightness=s.brightness, power=s.power,
                       light_color=s.light_color, raw=s.raw, clock_color=s.clock.color if s.clock else None)
