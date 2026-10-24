"""Appareils Divoom en Wi-Fi : Pixoo-64 (64×64), par l'API HTTP locale (voir transport.py).

Constaté sur un Pixoo-64 II (journal de l'atelier, phase 0) :

- une image est une « animation » d'une seule image (``Draw/SendHttpGif``, RGB en base64) ; chaque
  image est jouée pendant ``PicSpeed`` avant la suivante : une durée longue (60 s) empile les envois
  et retarde l'affichage de plusieurs minutes. Avec une **durée courte**, la dernière image **reste**
  affichée et la suivante la remplace aussitôt ;
- chaque envoi prend ~1,45 s (l'appareil impose son rythme) : un seul envoi à la fois, et si
  plusieurs images attendent, seule la plus récente est envoyée (envoi automatique de l'éditeur) ;
- ``Draw/ResetHttpGifId`` avant chaque envoi : l'identifiant reste à 1 (au-delà de ~300 envois sans
  réinitialisation, le Pixoo-64 se fige, d'après la communauté).
"""

import base64

import java
from org.slf4j import LoggerFactory

from .. import device
from ..device import Device, DeviceState, DeviceUnavailable
from .transport import CommandFailed, HttpTransport

ReentrantLock = java.type("java.util.concurrent.locks.ReentrantLock")
AtomicLong = java.type("java.util.concurrent.atomic.AtomicLong")

log = LoggerFactory.getLogger("pixel_studio.wifi")

SIZE = 64
FRAME_MS = 1000  # durée courte : l'image reste affichée, sans file d'attente
CHANNELS = {"faces": 0, "cloud": 1, "visualizer": 2, "custom": 3}
CHANNEL_NAMES = {code: name for name, code in CHANNELS.items()}


class WifiDevice(Device):
    def __init__(self, device_id: str, name: str, transport: HttpTransport):
        super().__init__(device_id, name)
        self.transport = transport
        self.lock = ReentrantLock()
        self.latest_image = AtomicLong()  # numéro de la dernière image demandée

    kind = "wifi"
    size = SIZE

    @property
    def address(self) -> str:
        return str(self.transport)

    @property
    def capabilities(self) -> list[str]:
        return [device.SCREEN, device.CHANNELS]

    # --- Commandes --------------------------------------------------------------------

    def state(self) -> DeviceState:
        """Reconstitué à partir de trois lectures : canal, cadran (luminosité), écran allumé."""
        channel = self._command("Channel/GetIndex").get("SelectIndex")
        clock = self._command("Channel/GetClockInfo")
        screen = self._command("Channel/GetOnOffScreen")
        view = CHANNEL_NAMES.get(channel, str(channel))
        return DeviceState(view=view, brightness=int(clock.get("Brightness", 0)), power=screen.get("OnOff") == 1,
                           light_color=None, raw=f"canal {channel}, cadran {clock.get('ClockId')}")

    def set_brightness(self, level: int) -> DeviceState:
        if not 0 <= level <= 100:
            raise ValueError(f"valeur hors de 0..100 : {level}")
        self._command("Channel/SetBrightness", Brightness=level)
        return self.state()

    def set_screen(self, on: bool) -> DeviceState:
        self._command("Channel/OnOffScreen", OnOff=1 if on else 0)
        return self.state()

    def set_channel(self, channel: str) -> DeviceState:
        if channel not in CHANNELS:
            raise ValueError(f"canal inconnu : {channel} (attendu : {', '.join(CHANNELS)})")
        self._command("Channel/SetIndex", SelectIndex=CHANNELS[channel])
        return self.state()

    def send_image(self, pixels: list[bytes]) -> None:
        if len(pixels) != SIZE * SIZE:
            raise ValueError(f"le {self.name} affiche des images {SIZE}×{SIZE}")
        number = self.latest_image.incrementAndGet()
        self.lock.lock()
        try:
            if number != self.latest_image.get():
                log.debug("image {} remplacée par une plus récente avant l'envoi", number)
                return
            data = base64.b64encode(b"".join(pixels)).decode()
            self._command("Draw/ResetHttpGifId")
            self._command("Draw/SendHttpGif", PicNum=1, PicWidth=SIZE, PicOffset=0, PicID=1,
                          PicSpeed=FRAME_MS, PicData=data)
        finally:
            self.lock.unlock()

    # --- Échanges ------------------------------------------------------------------------

    def _command(self, name: str, **fields) -> dict:
        """Une commande à la fois (l'appareil traite mal les requêtes simultanées) ; le verrou est
        réentrant : send_image le garde pendant ses deux commandes."""
        self.lock.lock()
        try:
            return self.transport.command(name, **fields)
        except CommandFailed as e:
            raise DeviceUnavailable(f"{self.transport} a refusé {name} : {e}") from e
        except (DeviceUnavailable, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:  # exceptions Java (connexion refusée, délai…) : hors de Exception
            log.warn("{} : {} en échec : {}", self.transport, name, repr(e))
            raise DeviceUnavailable(f"{self.transport} injoignable ({_reason(e)})") from e
        finally:
            self.lock.unlock()


def _reason(e: BaseException) -> str:
    text = str(e) or type(e).__name__
    return text.split(":")[-1].strip() if "Exception" in text else text
