"""API REST : appareils (`/devices`), appareil actif (`/device/*`), galerie (`/gallery/*`)."""

from dataclasses import dataclass
from typing import Annotated

import java
from jakarta.validation.constraints import Max, Min
from micronaut.http import HttpRequest, HttpResponse, HttpStatus
from micronaut.http import MediaType
from micronaut.http.annotation import Body, Controller, Delete, Error, Get, Post, Put, QueryValue, Status
from micronaut.http.hateoas import JsonError
from micronaut.serde.annotation import Serdeable
from org.slf4j import LoggerFactory

from . import imaging
from . import pixels as px
from . import storage
from .device import Device, DeviceState, DeviceUnavailable, UnsupportedCommand
from .registry import DeviceNotFound, DeviceRegistry, LastDevice
from .storage import ImageNotFound, Storage

log = LoggerFactory.getLogger("pixel_studio.api")
PolyglotException = java.type("org.graalvm.polyglot.PolyglotException")


@Serdeable
@dataclass
class DeviceInfo:
    id: str
    name: str
    kind: str
    size: int
    address: str
    capabilities: list[str]
    active: bool


@Serdeable
@dataclass
class DeviceList:
    active: str
    devices: list[DeviceInfo]


@Serdeable
@dataclass
class DeviceSelection:
    id: str


@Serdeable
@dataclass
class DeviceCreate:
    """Appareil à ajouter (ou à tester) : ``kind`` = « bluetooth » (adresse du relais) ou « wifi »
    (adresse de l'appareil) ; ``port`` facultatif (7777 pour le relais, 9000 pour le Pixoo-64 II)."""
    name: str
    kind: str
    host: str
    port: int | None = None


@Serdeable
@dataclass
class State:
    view: str
    light_color: str | None
    clock_color: str | None
    brightness: int
    power: bool
    raw: str


@Serdeable
@dataclass
class Image:
    """Image 16×16 ou 64×64 : size² couleurs « rrggbb », ligne par ligne (index x + size·y).
    En entrée, ``size`` est facultatif (déduit du nombre de pixels)."""
    pixels: list[str]
    size: int | None = None


@Serdeable
@dataclass
class GalleryImage:
    id: str
    name: str
    size: int
    pixels: list[str]
    created: str
    updated: str


@Serdeable
@dataclass
class GalleryCreate:
    name: str
    pixels: list[str]


@Serdeable
@dataclass
class GalleryUpdate:
    """Champs à modifier (absents = inchangés)."""
    name: str | None = None
    pixels: list[str] | None = None


class ImageSizeMismatch(Exception):
    """L'image n'a pas la taille de l'appareil actif (conversion à faire depuis la galerie)."""


def to_gallery_image(item: dict) -> GalleryImage:
    size = item.get("size") or px.size_of(item["pixels"])  # anciennes images : pas de « size »
    return GalleryImage(size=size, **{k: item[k] for k in ("id", "name", "pixels", "created", "updated")})


def image(pixels: list[str]) -> Image:
    return Image(pixels=pixels, size=px.size_of(pixels))


def to_state(s: DeviceState) -> State:
    return State(view=s.view, light_color=s.light_color, clock_color=s.clock_color, brightness=s.brightness,
                 power=s.power, raw=s.raw)


@Controller
class ApiController:
    def __init__(self, registry: DeviceRegistry, storage: Storage):
        self.registry = registry
        self.storage = storage

    def _info(self, device: Device) -> DeviceInfo:
        return DeviceInfo(id=device.id, name=device.name, kind=device.kind, size=device.size,
                          address=device.address, capabilities=list(device.capabilities),
                          active=device.id == self.registry.active_id)

    def _devices(self) -> DeviceList:
        return DeviceList(active=self.registry.active_id, devices=[self._info(d) for d in self.registry.all()])

    def _send(self, pixels: list[bytes]) -> Image:
        device = self.registry.active()
        size = px.size_of(pixels)
        if size != device.size:
            raise ImageSizeMismatch(f"image {size}×{size}, mais {device.name} affiche du {device.size}×{device.size} : "
                                    "convertissez-la depuis la galerie")
        device.send_image(pixels)
        hexes = [p.hex() for p in pixels]
        self.registry.remember_image(device, hexes)
        return image(hexes)

    # --- Appareils -------------------------------------------------------------------------

    @Get("/devices")
    def devices(self) -> DeviceList:
        """Appareils déclarés et appareil actif."""
        return self._devices()

    @Put("/devices/active")
    def activate(self, selection: Annotated[DeviceSelection, Body]) -> DeviceList:
        """Change d'appareil actif : les routes /device/* s'adressent ensuite à lui."""
        self.registry.activate(selection.id)
        return self._devices()

    @Post("/devices")
    @Status(HttpStatus.CREATED)
    def add_device(self, body: Annotated[DeviceCreate, Body]) -> DeviceInfo:
        """Déclare un appareil (il ne devient pas actif)."""
        return self._info(self.registry.add(body.name, body.kind, body.host, body.port))

    @Delete("/devices/{device_id}")
    @Status(HttpStatus.NO_CONTENT)
    def remove_device(self, device_id: str) -> None:
        """Retire un appareil (pas le dernier) ; s'il était actif, le premier restant le devient."""
        self.registry.remove(device_id)

    @Post("/devices/test")
    def test_device(self, body: Annotated[DeviceCreate, Body]) -> HttpResponse:
        """Interroge un appareil sans l'enregistrer (bouton « Tester ») : son état, ou 503."""
        device = self.registry.probe(body.name, body.kind, body.host, body.port)
        try:
            return HttpResponse.ok(to_state(device.state()))
        except DeviceUnavailable as e:
            return HttpResponse.status(HttpStatus.SERVICE_UNAVAILABLE).body(JsonError(f"{device.name} : {e}"))
        finally:
            device.close()

    # --- Appareil actif ----------------------------------------------------------------------

    @Get("/device")
    def device(self) -> DeviceInfo:
        return self._info(self.registry.active())

    @Get("/device/state")
    def state(self) -> State:
        """État courant de l'appareil actif."""
        return to_state(self.registry.active().state())

    @Post("/device/color/{rgb}")
    def color(self, rgb: str,
              brightness: Annotated[int, QueryValue(defaultValue="100"), Min(0), Max(100)]) -> State:
        """Affiche une couleur unie, ex. POST /device/color/ff8800?brightness=50."""
        return to_state(self.registry.active().set_color(px.parse_color(rgb), brightness))

    @Post("/device/clock/color/{rgb}")
    def clock_color(self, rgb: str) -> State:
        """Affiche l'horloge dans cette couleur (style et options inchangés), ex. POST /device/clock/color/00d800."""
        return to_state(self.registry.active().set_clock_color(px.parse_color(rgb)))

    @Post("/device/screen/{power}")
    def screen(self, power: str) -> State:
        """Allume (on) ou éteint (off) l'écran — capacité « screen »."""
        if power not in ("on", "off"):
            raise ValueError(f"état d'écran inconnu : {power} (attendu : on, off)")
        return to_state(self.registry.active().set_screen(power == "on"))

    @Post("/device/channel/{name}")
    def channel(self, name: str) -> State:
        """Change de canal : faces, cloud, visualizer, custom — capacité « channels »."""
        return to_state(self.registry.active().set_channel(name))

    @Post("/device/brightness/{level}")
    def brightness(self, level: Annotated[int, Min(0), Max(100)]) -> State:
        return to_state(self.registry.active().set_brightness(level))

    @Post("/device/view/{name}")
    def view(self, name: str) -> State:
        """Change d'écran : clock ou light."""
        return to_state(self.registry.active().set_view(name))

    @Post("/device/image")
    def send_image(self, body: Annotated[Image, Body]) -> Image:
        """Affiche une image envoyée en JSON ; elle doit avoir la taille de l'appareil actif."""
        return self._send(px.parse_pixels(list(body.pixels), body.size))

    @Post(value="/device/image/png", consumes=[MediaType.IMAGE_PNG, MediaType.IMAGE_GIF,
                                              MediaType.IMAGE_BMP, MediaType.IMAGE_JPEG])
    def send_png(self, data: Annotated[bytes, Body]) -> Image:
        """Affiche une image envoyée brute (PNG, GIF, BMP, JPEG), à la taille de l'appareil actif,
        décodée avec javax.imageio."""
        return self._send(imaging.png_to_pixels(data, self.registry.active().size))

    @Get("/device/image")
    def last_image(self) -> HttpResponse:
        """Dernière image envoyée à l'appareil actif (il ne sait pas la renvoyer) ; 404 si aucune."""
        pixels = self.registry.last_image(self.registry.active())
        if pixels is None:
            return HttpResponse.notFound(JsonError("aucune image envoyée à cet appareil"))
        return HttpResponse.ok(image(pixels))

    # --- Galerie -------------------------------------------------------------------------

    @Get("/gallery")
    def gallery(self) -> list[GalleryImage]:
        """Images enregistrées, de la plus récemment modifiée à la plus ancienne."""
        return [to_gallery_image(i) for i in self.storage.images()]

    @Get("/gallery/{image_id}")
    def gallery_image(self, image_id: str) -> GalleryImage:
        return to_gallery_image(self.storage.image(image_id))

    @Post("/gallery")
    @Status(HttpStatus.CREATED)
    def gallery_create(self, body: Annotated[GalleryCreate, Body]) -> GalleryImage:
        return to_gallery_image(self.storage.create_image(body.name, list(body.pixels)))

    @Put("/gallery/{image_id}")
    def gallery_update(self, image_id: str, changes: Annotated[GalleryUpdate, Body]) -> GalleryImage:
        pixels = list(changes.pixels) if changes.pixels is not None else None
        return to_gallery_image(self.storage.update_image(image_id, changes.name, pixels))

    @Delete("/gallery/{image_id}")
    @Status(HttpStatus.NO_CONTENT)
    def gallery_delete(self, image_id: str) -> None:
        self.storage.delete_image(image_id)

    @Post("/gallery/{image_id}/send")
    def gallery_send(self, image_id: str) -> Image:
        """Affiche une image de la galerie sur l'appareil actif."""
        return self._send(px.parse_pixels(self.storage.image(image_id)["pixels"]))

    @Post("/gallery/{image_id}/convert")
    @Status(HttpStatus.CREATED)
    def gallery_convert(self, image_id: str, size: Annotated[int, QueryValue]) -> GalleryImage:
        """Copie de l'image à une autre taille (16 ou 64), ex. POST /gallery/{id}/convert?size=64."""
        item = self.storage.image(image_id)
        pixels = px.resize(item["pixels"], size)
        suffix = f" ({size}×{size})"
        name = item["name"][:storage.NAME_MAX - len(suffix)] + suffix
        return to_gallery_image(self.storage.create_image(name, pixels))

    # --- Erreurs -------------------------------------------------------------------------

    # Pyronaut génère une classe Java pour chaque exception définie dans l'application :
    # elles se gèrent donc comme des exceptions Java ordinaires.
    @Error
    def on_unavailable(self, request: HttpRequest, e: DeviceUnavailable) -> HttpResponse:
        name = self.registry.active().name
        log.warn("{} indisponible : {}", name, str(e))
        return HttpResponse.status(HttpStatus.SERVICE_UNAVAILABLE).body(JsonError(f"{name} indisponible : {e}"))

    @Error
    def on_unsupported(self, request: HttpRequest, e: UnsupportedCommand) -> HttpResponse:
        return HttpResponse.badRequest(JsonError(str(e)))

    @Error
    def on_size_mismatch(self, request: HttpRequest, e: ImageSizeMismatch) -> HttpResponse:
        return HttpResponse.status(HttpStatus.CONFLICT).body(JsonError(str(e)))

    @Error
    def on_image_not_found(self, request: HttpRequest, e: ImageNotFound) -> HttpResponse:
        return HttpResponse.notFound(JsonError(f"image introuvable : {e}"))

    @Error
    def on_last_device(self, request: HttpRequest, e: LastDevice) -> HttpResponse:
        return HttpResponse.status(HttpStatus.CONFLICT).body(
            JsonError(f"{e} est le dernier appareil : ajoutez-en un autre avant de le retirer"))

    @Error
    def on_device_not_found(self, request: HttpRequest, e: DeviceNotFound) -> HttpResponse:
        return HttpResponse.notFound(JsonError(f"appareil inconnu : {e}"))

    # Les exceptions Python natives (ValueError…) arrivent enveloppées dans une PolyglotException ;
    # getGuestObject() rend l'exception Python d'origine. Les exceptions Java (validation…) restent
    # gérées par Micronaut.
    @Error(exception=PolyglotException)
    def on_python_error(self, request: HttpRequest, error: PolyglotException) -> HttpResponse:
        e = error.getGuestObject() if error.isGuestException() else None
        if isinstance(e, ValueError):
            return HttpResponse.badRequest(JsonError(str(e)))
        log.error("erreur inattendue sur {} : {}", request.getPath(), error.getMessage())
        return HttpResponse.serverError(JsonError(error.getMessage()))
