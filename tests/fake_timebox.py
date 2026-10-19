"""Faux Timebox Evo, injecté à la place du transport TCP dans l'environnement « test ».

Répond de façon synchrone comme l'appareil réel (octets observés, docs/protocol.md) :
ni socket ni thread (tous deux interdits dans les contextes GraalPy de Pyronaut).
Avec ``fake-timebox.image-ack=false``, il imite le Pixoo, qui n'acquitte pas les images.
"""

from typing import Annotated

from jakarta.inject import Singleton
from micronaut.context.annotation import Replaces, Requires, Value

from timebox.evo import protocol as p
from timebox.evo.transport import TcpTransport, Transport


@Singleton
@Requires(env="test")
@Replaces(TcpTransport)
class FakeTimeboxTransport(Transport):
    image_ack: Annotated[bool, Value("${fake-timebox.image-ack:true}")]

    def __init__(self):
        self.view = p.VIEW_CLOCK
        self.color = bytes.fromhex("ff5000")
        self.brightness = 100
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
                + bytes([self.brightness, 0, 1, 3, self.brightness, 0, 0, 0, 0xFF, 0, 1, 0, 0, 0]))

    def _handle(self, payload: bytes) -> list[bytes]:
        command = payload[0]
        if command == p.GET_VIEW:
            return [self._reply(p.GET_VIEW, self._state())]
        if command == p.SET_BRIGHTNESS:
            self.brightness = payload[1]
            return [self._reply(p.LIGHTNESS_STATUS, payload[1:2])]
        if command == p.IMAGE:
            self.image, _ = p.decode_frame(payload[len(p.IMAGE_HEADER):])
            if not self.image_ack:  # Pixoo : image affichée sans accusé
                return []
            return [self._reply(p.IMAGE, b"\x43")]  # octet final variable sur l'appareil réel
        if command == p.SET_VIEW:
            self.view = payload[1]
            if self.view == p.VIEW_LIGHT and len(payload) >= 6:
                self.color, self.brightness = bytes(payload[2:5]), payload[5]
            return [self._reply(p.LIGHT_STATUS, b"\x64"),  # message spontané, comme l'appareil réel
                    self._reply(p.SET_VIEW, bytes([self.view]))]
        return []
