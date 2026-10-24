"""Interface commune des appareils Divoom pilotés par pixel-studio.

Chaque famille d'appareils a son implémentation : `bluetooth.device.BluetoothDevice` (Timebox Evo,
Pixoo 16×16, à travers le relais timebox-bridge) et `wifi.device.WifiDevice` (Pixoo-64, API HTTP
locale).
L'interface web n'affiche que les commandes que l'appareil sait faire (`capabilities`).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Capacités facultatives (les autres commandes sont communes à tous les appareils)
COLOR = "color"        # couleur unie (écran « lumière »)
VIEWS = "views"        # changement d'écran : horloge, lumière ; couleur de l'horloge
SCREEN = "screen"      # écran allumé / éteint (veille)
CHANNELS = "channels"  # canaux : cadrans, cloud, visualiseur, personnalisé


class DeviceUnavailable(Exception):
    """L'appareil (ou son relais) est injoignable, ou ne répond pas."""


class UnsupportedCommand(Exception):
    """L'appareil ne sait pas exécuter cette commande."""


@dataclass(frozen=True)
class DeviceState:
    view: str              # Bluetooth : « clock », « light » ; Wi-Fi : canal (« faces »…) ; sinon code brut
    brightness: int
    power: bool
    light_color: str | None
    raw: str
    clock_color: str | None = None


class Device(ABC):
    """Un appareil : identité, état, commandes. Les échanges sont sérialisés par l'implémentation."""

    def __init__(self, device_id: str, name: str):
        self.id = device_id
        self.name = name

    @property
    @abstractmethod
    def kind(self) -> str:
        """Famille d'appareils (« bluetooth », « wifi »)."""

    @property
    @abstractmethod
    def size(self) -> int:
        """Côté de la matrice en pixels (16 ou 64)."""

    @property
    @abstractmethod
    def address(self) -> str:
        """Adresse lisible (relais ou appareil)."""

    @property
    def capabilities(self) -> list[str]:
        return []

    @abstractmethod
    def state(self) -> DeviceState:
        ...

    @abstractmethod
    def set_brightness(self, level: int) -> DeviceState:
        ...

    @abstractmethod
    def send_image(self, pixels: list[bytes]) -> None:
        """Affiche une image de `size` × `size` couleurs RGB, ligne par ligne."""

    def set_color(self, color: bytes, brightness: int) -> DeviceState:
        raise UnsupportedCommand(f"{self.name} n'affiche pas de couleur unie")

    def set_view(self, view: str) -> DeviceState:
        raise UnsupportedCommand(f"{self.name} n'a pas d'écrans horloge / lumière")

    def set_clock_color(self, color: bytes) -> DeviceState:
        raise UnsupportedCommand(f"{self.name} n'a pas d'écran horloge")

    def set_screen(self, on: bool) -> DeviceState:
        raise UnsupportedCommand(f"{self.name} ne sait pas éteindre son écran")

    def set_channel(self, channel: str) -> DeviceState:
        raise UnsupportedCommand(f"{self.name} n'a pas de canaux")

    def close(self) -> None:
        """Libère les connexions (appareil retiré ou arrêt de l'application)."""
