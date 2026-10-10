"""Client haut niveau du Timebox Evo : commandes, attente des réponses, décodage de l'état.

Pyronaut fait tourner plusieurs contextes GraalPy, et seul un @Singleton est partagé entre eux.
Le verrou qui sérialise les échanges est donc un objet Java (ReentrantLock).
"""

import time
from typing import Annotated

import java
from jakarta.inject import Singleton
from micronaut.context.annotation import Value
from org.slf4j import LoggerFactory

from . import protocol
from .storage import Storage
from .transport import Transport

ReentrantLock = java.type("java.util.concurrent.locks.ReentrantLock")

log = LoggerFactory.getLogger("timebox.evo.client")


class TimeboxUnavailable(Exception):
    """Le relais est injoignable ou l'appareil ne répond pas."""


@Singleton
class TimeboxClient:
    reply_timeout_ms: Annotated[int, Value("${timebox.reply-timeout-ms:2000}")]

    def __init__(self, transport: Transport, storage: Storage):
        self.transport = transport
        self.storage = storage
        self.lock = ReentrantLock()
        self.decoder = protocol.FrameDecoder()
        # L'appareil ne sait pas renvoyer l'image affichée : on mémorise (et persiste) la dernière.
        self.last_image: list[str] | None = storage.load_last_image()

    # --- API de haut niveau ---------------------------------------------------------

    def state(self) -> protocol.DeviceState:
        return protocol.parse_state(self.exchange(protocol.get_view()).data)

    def set_color(self, color: bytes, brightness: int = 100) -> None:
        self.exchange(protocol.set_light(color, brightness))

    def set_brightness(self, level: int) -> None:
        self.exchange(protocol.set_brightness(level))

    def set_view(self, view: int) -> None:
        self.exchange(protocol.set_view(view))

    def send_image(self, pixels: list[bytes]) -> None:
        """Affiche une image 16×16 (256 couleurs RGB, ligne par ligne)."""
        self.exchange(protocol.set_image(pixels))
        self.last_image = [p.hex() for p in pixels]
        self.storage.save_last_image(self.last_image)

    # --- Échange de trames ----------------------------------------------------------

    def exchange(self, payload: bytes) -> protocol.Response:
        """Envoie une commande et attend la réponse qui la confirme."""
        expected = protocol.EXPECTED_REPLY.get(payload[0], payload[0])
        self.lock.lock()
        try:
            return self._exchange(payload, expected)
        except (TimeboxUnavailable, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:  # sous GraalPy, une exception Java (IOException…) n'hérite pas
            # de la classe Python Exception : on intercepte large et on repart d'une connexion neuve
            log.warn("échange {} en échec : {}", payload.hex(" "), repr(e))
            self.transport.close()
            self.decoder = protocol.FrameDecoder()
            raise TimeboxUnavailable(f"{self.transport} : {e}") from e
        finally:
            self.lock.unlock()

    def _exchange(self, payload: bytes, expected: int) -> protocol.Response:
        self.decoder.feed(self.transport.read_available())  # ignore les messages spontanés en attente
        self.transport.write(protocol.encode(payload))

        deadline = time.monotonic() + self.reply_timeout_ms / 1000
        while time.monotonic() < deadline:
            for frame in self.decoder.feed(self.transport.read_available()):
                reply = protocol.parse_response(frame)
                if reply is not None and reply.command == expected:
                    return reply
            time.sleep(0.01)
        raise TimeboxUnavailable(f"pas de réponse {expected:02x} de l'appareil")
