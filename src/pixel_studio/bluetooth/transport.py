"""Transports vers l'appareil.

`Transport` est l'interface ; `TcpTransport` parle au relais timebox-bridge (macOS, Linux…).
`TransportFactory` (bean) crée le transport de chaque appareil : les tests la remplacent pour
brancher un faux appareil. D'autres implémentations sont possibles (RFCOMM direct sous Linux).

Dans Pyronaut, le module Python `socket` est exclu de GraalPy : le transport TCP utilise
`java.net.Socket`. Ces objets Java sont aussi partageables entre les contextes GraalPy du pool.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import java
from jakarta.inject import Singleton
from micronaut.context.annotation import ConfigurationProperties

Socket = java.type("java.net.Socket")
InetSocketAddress = java.type("java.net.InetSocketAddress")


class Transport(ABC):
    @abstractmethod
    def write(self, data: bytes) -> None:
        """Envoie des octets (connexion à la demande)."""

    @abstractmethod
    def read_available(self) -> bytes:
        """Renvoie les octets déjà reçus, sans bloquer (b"" si rien)."""

    @abstractmethod
    def close(self) -> None:
        """Ferme la connexion ; la suivante sera rouverte à la demande."""


# Pas de frozen=True : avec des valeurs par défaut, Micronaut affecte les champs après construction.
@ConfigurationProperties("pixel-studio.bridge")
@dataclass
class BridgeConfig:
    """Relais par défaut (appareil Bluetooth créé au premier lancement) et délais."""
    host: str = "127.0.0.1"
    port: int = 7777
    connect_timeout_ms: int = 2000
    reply_timeout_ms: int = 2000


class TcpTransport(Transport):
    def __init__(self, host: str, port: int, connect_timeout_ms: int):
        self.host = host
        self.port = port
        self.connect_timeout_ms = connect_timeout_ms
        self.socket = None

    def _connect(self):
        if self.socket is None or self.socket.isClosed():
            sock = Socket()
            sock.setTcpNoDelay(True)
            sock.connect(InetSocketAddress(self.host, self.port), self.connect_timeout_ms)
            self.socket = sock
        return self.socket

    def write(self, data: bytes) -> None:
        out = self._connect().getOutputStream()
        for b in data:
            out.write(b)
        out.flush()

    def read_available(self) -> bytes:
        stream_in = self._connect().getInputStream()
        count = stream_in.available()
        return bytes(stream_in.read() & 0xFF for _ in range(count)) if count > 0 else b""

    def close(self) -> None:
        if self.socket is not None:
            try:
                self.socket.close()
            finally:
                self.socket = None

    def __str__(self) -> str:
        return f"relais {self.host}:{self.port}"


@Singleton
class TransportFactory:
    def __init__(self, config: BridgeConfig):
        self.config = config

    def create(self, host: str, port: int) -> Transport:
        return TcpTransport(host, port, self.config.connect_timeout_ms)
