"""Faux Pixoo-64 (Wi-Fi), branché à la place de l'API HTTP dans l'environnement « test ».

Répond comme le Pixoo-64 II observé (port 9000, enveloppe ``ReturnCode``) ; l'hôte
« injoignable » simule un appareil éteint. Chaque appareil déclaré a son faux Pixoo (par adresse).
"""

import base64

from jakarta.inject import Singleton
from micronaut.context.annotation import Replaces, Requires

from pixel_studio.wifi.transport import CommandFailed, HttpTransport, HttpTransportFactory, check

UNREACHABLE = "injoignable"


@Singleton
@Requires(env="test")
@Replaces(HttpTransportFactory)
class FakeHttpTransportFactory(HttpTransportFactory):  # sous-classe : sinon Micronaut garde la vraie
    def __init__(self):
        self.devices: dict[str, FakePixoo64] = {}

    def create(self, host: str, port: int, path: str | None = None) -> HttpTransport:
        key = f"{host}:{port}"
        if key not in self.devices:
            self.devices[key] = FakePixoo64(host, port)
        return self.devices[key]


class FakePixoo64(HttpTransport):
    def __init__(self, host: str, port: int):
        self.address = f"{host}:{port}"
        self.reachable = host != UNREACHABLE
        self.channel = 2
        self.brightness = 100
        self.screen = 1
        self.image: bytes | None = None
        self.gif_id_resets = 0
        self.commands: list[str] = []

    def command(self, name: str, **fields) -> dict:
        if not self.reachable:
            raise ConnectionError(f"connexion refusée par {self.address}")
        self.commands.append(name)
        reply = {"Command": name, "DeviceId": 300443285, "ReturnCode": 0, "ReturnMessage": ""}
        if name == "Channel/GetIndex":
            reply["SelectIndex"] = self.channel
        elif name == "Channel/SetIndex":
            self.channel = fields["SelectIndex"]
        elif name == "Channel/GetClockInfo":
            reply |= {"Brightness": self.brightness, "ClockId": 10}
        elif name == "Channel/SetBrightness":
            self.brightness = fields["Brightness"]
        elif name == "Channel/GetOnOffScreen":
            reply["OnOff"] = self.screen
        elif name == "Channel/OnOffScreen":
            self.screen = fields["OnOff"]
        elif name == "Draw/ResetHttpGifId":
            self.gif_id_resets += 1
        elif name == "Draw/SendHttpGif":
            data = base64.b64decode(fields["PicData"])
            if fields["PicWidth"] != 64 or len(data) != 64 * 64 * 3:
                reply = {"ReturnCode": 1, "ReturnMessage": "bad picture"}
            else:
                self.image = data
        else:
            reply = {"ReturnCode": 1, "ReturnMessage": "Only accept JSON parameters"}
        return check(reply)

    def __str__(self) -> str:
        return self.address


__all__ = ["CommandFailed", "FakeHttpTransportFactory", "FakePixoo64"]
