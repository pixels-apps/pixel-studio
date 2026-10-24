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

from . import imaging, protocol
from .client import TimeboxClient, TimeboxUnavailable
from .storage import ImageNotFound, Storage

log = LoggerFactory.getLogger("timebox.evo.controller")
PolyglotException = java.type("org.graalvm.polyglot.PolyglotException")

VIEWS = {"clock": protocol.VIEW_CLOCK, "light": protocol.VIEW_LIGHT}


@Serdeable
@dataclass
class State:
    view: str
    light_color: str
    brightness: int
    power: bool
    raw: str


@Serdeable
@dataclass
class Image:
    """Image 16×16 : 256 couleurs « rrggbb », ligne par ligne (index x + 16·y)."""
    pixels: list[str]


@Serdeable
@dataclass
class GalleryImage:
    id: str
    name: str
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


def to_gallery_image(item: dict) -> GalleryImage:
    return GalleryImage(**{k: item[k] for k in ("id", "name", "pixels", "created", "updated")})


def to_state(s: protocol.DeviceState) -> State:
    names = {code: name for name, code in VIEWS.items()}
    return State(view=names.get(s.view, f"{s.view:02x}"), light_color=s.light_color,
                 brightness=s.brightness, power=s.power, raw=s.raw)


@Controller("/timebox")
class TimeboxController:
    def __init__(self, client: TimeboxClient, storage: Storage):
        self.client = client
        self.storage = storage

    @Get("/state")
    def state(self) -> State:
        """État courant de l'appareil (réponse à la commande 46)."""
        return to_state(self.client.state())

    @Post("/color/{rgb}")
    def color(self, rgb: str,
              brightness: Annotated[int, QueryValue(defaultValue="100"), Min(0), Max(100)]) -> State:
        """Affiche une couleur unie, ex. POST /timebox/color/ff8800?brightness=50."""
        return to_state(self.client.set_color(protocol.parse_color(rgb), brightness))

    @Post("/brightness/{level}")
    def brightness(self, level: Annotated[int, Min(0), Max(100)]) -> State:
        return to_state(self.client.set_brightness(level))

    @Post("/view/{name}")
    def view(self, name: str) -> State:
        """Change d'écran : clock ou light."""
        if name not in VIEWS:
            raise ValueError(f"écran inconnu : {name} (attendu : {', '.join(VIEWS)})")
        return to_state(self.client.set_view(VIEWS[name]))

    @Post("/image")
    def send_image(self, image: Annotated[Image, Body]) -> Image:
        """Affiche une image 16×16 envoyée en JSON."""
        self.client.send_image(protocol.parse_pixels(list(image.pixels)))
        return Image(pixels=self.client.last_image)

    @Post(value="/image/png", consumes=[MediaType.IMAGE_PNG, MediaType.IMAGE_GIF,
                                       MediaType.IMAGE_BMP, MediaType.IMAGE_JPEG])
    def send_png(self, data: Annotated[bytes, Body]) -> Image:
        """Affiche une image 16×16 envoyée brute (PNG, GIF, BMP, JPEG), décodée avec javax.imageio."""
        self.client.send_image(imaging.png_to_pixels(data))
        return Image(pixels=self.client.last_image)

    @Get("/image")
    def last_image(self) -> HttpResponse:
        """Dernière image envoyée (l'appareil ne sait pas la renvoyer) ; 404 si aucune."""
        if self.client.last_image is None:
            return HttpResponse.notFound(JsonError("aucune image envoyée depuis le démarrage"))
        return HttpResponse.ok(Image(pixels=self.client.last_image))

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
    def gallery_create(self, image: Annotated[GalleryCreate, Body]) -> GalleryImage:
        return to_gallery_image(self.storage.create_image(image.name, list(image.pixels)))

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
        """Affiche une image de la galerie sur l'appareil."""
        item = self.storage.image(image_id)
        self.client.send_image(protocol.parse_pixels(item["pixels"]))
        return Image(pixels=self.client.last_image)

    # Pyronaut génère une classe Java pour chaque exception définie dans l'application :
    # TimeboxUnavailable se gère donc comme une exception Java ordinaire.
    @Error
    def on_unavailable(self, request: HttpRequest, e: TimeboxUnavailable) -> HttpResponse:
        log.warn("Timebox indisponible : {}", str(e))
        return HttpResponse.status(HttpStatus.SERVICE_UNAVAILABLE).body(
            JsonError(f"Timebox indisponible : {e}"))

    @Error
    def on_not_found(self, request: HttpRequest, e: ImageNotFound) -> HttpResponse:
        return HttpResponse.notFound(JsonError(f"image introuvable : {e}"))

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
