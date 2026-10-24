"""Registre des appareils : appareils déclarés, appareil actif, dernière image de chacun.

Les appareils sont enregistrés dans `devices.json` (dossier de stockage). Tant que l'utilisateur
n'a rien changé, un seul appareil existe : « Divoom Bluetooth », derrière le relais configuré
(`pixel-studio.bridge.host` / `port`) — le fichier n'est écrit qu'au premier changement.

Types d'appareils : « bluetooth » (``host`` / ``port`` du relais) et « wifi » (``host`` / ``port``
de l'appareil : 9000 pour le Pixoo-64 II, 80 pour le Pixoo-64 d'origine).
"""

import re
import unicodedata

import java
from jakarta.annotation import PreDestroy
from jakarta.inject import Singleton
from org.slf4j import LoggerFactory

from .bluetooth.device import BluetoothDevice
from .bluetooth.transport import BridgeConfig, TransportFactory
from .device import Device
from .storage import Storage
from .wifi.device import WifiDevice
from .wifi.transport import HttpTransportFactory

ReentrantLock = java.type("java.util.concurrent.locks.ReentrantLock")

log = LoggerFactory.getLogger("pixel_studio.registry")

DEFAULT_ID = "bluetooth"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
KINDS = ("bluetooth", "wifi")
DEFAULT_PORTS = {"bluetooth": 7777, "wifi": 9000}
NAME_MAX = 40


class DeviceNotFound(Exception):
    """Aucun appareil déclaré ne porte cet identifiant."""


class LastDevice(Exception):
    """Le dernier appareil déclaré ne peut pas être retiré."""


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:32] or "appareil"


def clean_config(name: str, kind: str, host: str, port: int | None) -> dict:
    """Valide la description d'un appareil (formulaire « Ajouter un appareil »)."""
    name = " ".join(str(name).split())
    if not name or len(name) > NAME_MAX:
        raise ValueError(f"le nom doit faire de 1 à {NAME_MAX} caractères")
    if kind not in KINDS:
        raise ValueError(f"type d'appareil inconnu : {kind} (attendu : {', '.join(KINDS)})")
    host = str(host).strip()
    if not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]{1,253}", host):
        raise ValueError(f"adresse invalide : {host!r}")
    port = DEFAULT_PORTS[kind] if port is None else int(port)
    if not 1 <= port <= 65535:
        raise ValueError(f"port hors de 1..65535 : {port}")
    return {"name": name, "kind": kind, "host": host, "port": port}


@Singleton
class DeviceRegistry:
    def __init__(self, storage: Storage, bridge: BridgeConfig, transports: TransportFactory,
                 http: HttpTransportFactory):
        self.storage = storage
        self.bridge = bridge
        self.transports = transports
        self.http = http
        self.lock = ReentrantLock()
        data = storage.load_devices() or self._default()
        self.configs: list[dict] = [c for c in data.get("devices", []) if ID_PATTERN.match(str(c.get("id", "")))]
        if not self.configs:
            data = self._default()
            self.configs = data["devices"]
        self.devices: dict[str, Device] = {c["id"]: self._create(c) for c in self.configs}
        active = data.get("active")
        self.active_id: str = active if active in self.devices else self.configs[0]["id"]
        self.last_images: dict[str, list[str] | None] = {}

    def _default(self) -> dict:
        return {"active": DEFAULT_ID, "devices": [{
            "id": DEFAULT_ID, "name": "Divoom Bluetooth", "kind": "bluetooth",
            "host": self.bridge.host, "port": self.bridge.port}]}

    def _create(self, config: dict) -> Device:
        kind = config.get("kind")
        if kind == "bluetooth":
            transport = self.transports.create(config.get("host", self.bridge.host),
                                               int(config.get("port", self.bridge.port)))
            return BluetoothDevice(config["id"], config["name"], transport, self.bridge.reply_timeout_ms)
        if kind == "wifi":
            transport = self.http.create(config["host"], int(config.get("port", 9000)), config.get("path"))
            return WifiDevice(config["id"], config["name"], transport)
        raise ValueError(f"type d'appareil inconnu : {kind}")

    # --- Appareils ---------------------------------------------------------------------

    def all(self) -> list[Device]:
        return [self.devices[c["id"]] for c in self.configs]

    def get(self, device_id: str) -> Device:
        if device_id not in self.devices:
            raise DeviceNotFound(device_id)
        return self.devices[device_id]

    def active(self) -> Device:
        return self.devices[self.active_id]

    def activate(self, device_id: str) -> Device:
        device = self.get(device_id)
        self.lock.lock()
        try:
            self.active_id = device_id
            self._save()
        finally:
            self.lock.unlock()
        log.info("appareil actif : {}", device.name)
        return device

    def add(self, name: str, kind: str, host: str, port: int | None) -> Device:
        config = clean_config(name, kind, host, port)
        self.lock.lock()
        try:
            base = _slug(config["name"])
            device_id, n = base, 2
            while device_id in self.devices:
                device_id, n = f"{base}-{n}", n + 1
            config = {"id": device_id, **config}
            device = self._create(config)
            self.configs.append(config)
            self.devices[device_id] = device
            self._save()
        finally:
            self.lock.unlock()
        log.info("appareil ajouté : {} ({}, {})", device.name, device.kind, device.address)
        return device

    def remove(self, device_id: str) -> None:
        device = self.get(device_id)
        self.lock.lock()
        try:
            if len(self.configs) == 1:
                raise LastDevice(device.name)
            self.configs = [c for c in self.configs if c["id"] != device_id]
            del self.devices[device_id]
            if self.active_id == device_id:
                self.active_id = self.configs[0]["id"]
            self._save()
            self.last_images.pop(device_id, None)
            self.storage.delete_last_image(device_id)
        finally:
            self.lock.unlock()
        device.close()
        log.info("appareil retiré : {}", device.name)

    def probe(self, name: str, kind: str, host: str, port: int | None) -> Device:
        """Appareil temporaire (non enregistré), pour le bouton « Tester »."""
        return self._create({"id": "essai", **clean_config(name, kind, host, port)})

    def _save(self) -> None:
        self.storage.save_devices({"active": self.active_id, "devices": self.configs})

    # --- Dernière image ------------------------------------------------------------------

    def last_image(self, device: Device) -> list[str] | None:
        if device.id not in self.last_images:
            # l'ancienne dernière image (un seul appareil) revient à l'appareil par défaut
            self.last_images[device.id] = self.storage.load_last_image(device.id, legacy=device.id == DEFAULT_ID)
        return self.last_images[device.id]

    def remember_image(self, device: Device, pixels: list[str]) -> None:
        self.last_images[device.id] = pixels
        self.storage.save_last_image(device.id, pixels)

    @PreDestroy
    def close(self) -> None:
        for device in self.devices.values():
            device.close()
