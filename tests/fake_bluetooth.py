"""Faux appareil Bluetooth (Timebox Evo par défaut), branché à la place du relais en test.

`FakeTransportFactory` remplace la fabrique de transports dans l'environnement « test » : chaque
appareil Bluetooth déclaré parle alors à un `FakeBluetoothTransport`, qui répond de façon synchrone
comme l'appareil réel (octets observés, docs/protocol.md) : ni socket ni thread (tous deux interdits
dans les contextes GraalPy de Pyronaut).
Avec ``fake-bluetooth.model=pixoo``, il imite le Pixoo : pas d'accusé pour les images (44) ni les
changements d'écran (45), et « 45 01 » seul allume la lumière à luminosité 0.
"""

from typing import Annotated

from jakarta.inject import Singleton
from micronaut.context.annotation import Replaces, Requires, Value

from pixel_studio.bluetooth import protocol as p
from pixel_studio.bluetooth.transport import Transport, TransportFactory


@Singleton
@Requires(env="test")
@Replaces(TransportFactory)
class FakeTransportFactory(TransportFactory):  # sous-classe : sinon Micronaut garde la vraie fabrique
    model: Annotated[str, Value("${fake-bluetooth.model:evo}")]

    def __init__(self):
        self.transports: dict[str, FakeBluetoothTransport] = {}

    def create(self, host: str, port: int) -> Transport:
        key = f"{host}:{port}"
        if key not in self.transports:
            self.transports[key] = FakeBluetoothTransport(self.model)
        return self.transports[key]


class FakeBluetoothTransport(Transport):
    def __init__(self, model: str):
        self.model = model
        self.view = p.VIEW_CLOCK
        self.color = bytes.fromhex("ff5000")
        self.brightness = 100
        self.clock = bytes([0, 0, 0xFF, 0, 1, 0, 0, 0])  # couleur (3), style, heure, météo, temp., calendrier
        self.decoder = p.FrameDecoder()
        self.outgoing = bytearray()
        self.image: list[bytes] | None = None

    def write(self, data: bytes) -> None:
        for frame in self.decoder.feed(data):
            for reply in self._handle(frame[3:-3]):
                self.outgoing.extend(reply)

    def read_available(self) -> bytes:
        data = bytes(self.outgoing)
        self.outgoing.clear()
        return data

    def close(self) -> None:
        pass

    def _reply(self, command: int, data: bytes) -> bytes:
        return p.encode(bytes([p.RESPONSE, command, p.ACK]) + data)

    def _state(self) -> bytes:
        return (bytes([self.view, 0, 0]) + self.color
                + bytes([self.brightness, 0, 1, 3, self.brightness, 0]) + self.clock)

    def _handle(self, payload: bytes) -> list[bytes]:
        command = payload[0]
        if command == p.GET_VIEW:
            return [self._reply(p.GET_VIEW, self._state())]
        if command == p.SET_BRIGHTNESS:
            self.brightness = payload[1]
            return [self._reply(p.LIGHTNESS_STATUS, payload[1:2])]
        if command == p.IMAGE:
            self.image, _ = p.decode_frame(payload[len(p.IMAGE_HEADER):])
            if self.model == "pixoo":  # image affichée sans accusé
                return []
            return [self._reply(p.IMAGE, b"\x43")]  # octet final variable sur l'appareil réel
        if command == p.SET_VIEW:
            self.view = payload[1]
            if self.view == p.VIEW_CLOCK and len(payload) >= 11:  # 45 00 01 TT XX WW EE CC RRGGBB
                self.clock = bytes(payload[8:11]) + bytes(payload[3:8])
            if self.view == p.VIEW_LIGHT and len(payload) >= 6:
                self.color, self.brightness = bytes(payload[2:5]), payload[5]
            elif self.view == p.VIEW_LIGHT and self.model == "pixoo":
                self.brightness = 0  # « 45 01 » seul : lumière éteinte
            light = self._reply(p.LIGHT_STATUS, bytes([self.brightness]))  # message spontané
            if self.model == "pixoo":  # pas d'accusé 45
                return [light] if self.view == p.VIEW_LIGHT else []
            return [light, self._reply(p.SET_VIEW, bytes([self.view]))]
        return []
