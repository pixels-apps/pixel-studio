"""Stockage sur disque : appareils, galerie d'images (un JSON par image), dernières images envoyées.

Arborescence (dossier configurable `pixel-studio.storage.dir`, défaut `~/.pixel-studio`) :

    devices.json                 {"active": id, "devices": [{"id", "name", "kind", …}]}
    gallery/<id>.json            {"id", "name", "size", "pixels": [size² × "rrggbb"], "created", "updated"}
                                 (anciennes images : pas de « size », 16×16)
    last-image/<appareil>.json   {"pixels": [...]}  (l'appareil ne sait pas renvoyer son image)
    last-image.json              ancienne dernière image (avant les appareils multiples), relue une fois
"""

import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import java
from jakarta.inject import Singleton
from micronaut.context.annotation import ConfigurationProperties

from . import pixels as px

ReentrantLock = java.type("java.util.concurrent.locks.ReentrantLock")
Files = java.type("java.nio.file.Files")
Paths = java.type("java.nio.file.Paths")
StandardCopyOption = java.type("java.nio.file.StandardCopyOption")

ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
NAME_MAX = 60


class ImageNotFound(Exception):
    """Aucune image de la galerie ne porte cet identifiant."""


@ConfigurationProperties("pixel-studio.storage")
@dataclass
class StorageConfig:
    dir: str = "~/.pixel-studio"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_name(name: str) -> str:
    name = " ".join(str(name).split())
    if not name:
        raise ValueError("le nom ne peut pas être vide")
    if len(name) > NAME_MAX:
        raise ValueError(f"le nom dépasse {NAME_MAX} caractères")
    return name


def _clean_pixels(pixels: list[str]) -> list[str]:
    return [p.hex() for p in px.parse_pixels(list(pixels))]


@Singleton
class Storage:
    def __init__(self, config: StorageConfig):
        self.root = Path(config.dir).expanduser()
        self.gallery = self.root / "gallery"
        self.lock = ReentrantLock()

    # --- Galerie ---------------------------------------------------------------------

    def images(self) -> list[dict]:
        if not self.gallery.is_dir():
            return []
        items = []
        for path in self.gallery.glob("*.json"):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue  # fichier illisible : ignoré
        return sorted(items, key=lambda i: i.get("updated", ""), reverse=True)

    def image(self, image_id: str) -> dict:
        path = self._path(image_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ImageNotFound(image_id) from None

    def create_image(self, name: str, pixels: list[str]) -> dict:
        now = _now()
        clean = _clean_pixels(pixels)
        item = {"id": secrets.token_hex(6), "name": _clean_name(name), "size": px.size_of(clean),
                "pixels": clean, "created": now, "updated": now}
        self._write(self._path(item["id"]), item)
        return item

    def update_image(self, image_id: str, name: str | None = None, pixels: list[str] | None = None) -> dict:
        self.lock.lock()
        try:
            item = self.image(image_id)
            if name is not None:
                item["name"] = _clean_name(name)
            if pixels is not None:
                item["pixels"] = _clean_pixels(pixels)
                item["size"] = px.size_of(item["pixels"])
            item["updated"] = _now()
            self._write(self._path(image_id), item)
            return item
        finally:
            self.lock.unlock()

    def delete_image(self, image_id: str) -> None:
        try:
            self._path(image_id).unlink()
        except FileNotFoundError:
            raise ImageNotFound(image_id) from None

    # --- Dernière image envoyée, par appareil ------------------------------------------

    def save_last_image(self, device_id: str, pixels: list[str]) -> None:
        self._write(self.root / "last-image" / f"{device_id}.json", {"pixels": pixels})

    def load_last_image(self, device_id: str, legacy: bool = False) -> list[str] | None:
        """``legacy`` : à défaut, reprendre la dernière image d'avant les appareils multiples."""
        paths = [self.root / "last-image" / f"{device_id}.json"]
        if legacy:
            paths.append(self.root / "last-image.json")
        for path in paths:
            try:
                return _clean_pixels(json.loads(path.read_text(encoding="utf-8"))["pixels"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return None

    def delete_last_image(self, device_id: str) -> None:
        (self.root / "last-image" / f"{device_id}.json").unlink(missing_ok=True)

    # --- Appareils ---------------------------------------------------------------------

    def load_devices(self) -> dict | None:
        try:
            return json.loads((self.root / "devices.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_devices(self, data: dict) -> None:
        self._write(self.root / "devices.json", data)

    # --- Interne -----------------------------------------------------------------------

    def _path(self, image_id: str) -> Path:
        if not ID_PATTERN.match(str(image_id)):
            raise ImageNotFound(image_id)  # aussi une protection contre « ../ »
        return self.gallery / f"{image_id}.json"

    def _write(self, path: Path, data: dict) -> None:
        """Écriture atomique : fichier temporaire puis renommage."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        # os.replace échoue sous GraalPy (« Atomic move not supported ») : on passe par java.nio
        source, target = Paths.get(str(tmp)), Paths.get(str(path))
        try:
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
        except BaseException:  # AtomicMoveNotSupportedException (exception Java)
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING)
