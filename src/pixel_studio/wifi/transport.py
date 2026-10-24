"""Transport HTTP vers les appareils Divoom en Wi-Fi (Pixoo-64) : API JSON locale, non officielle.

- Pixoo-64 II : ``POST http://<ip>:9000/divoom_api``, réponse avec ``ReturnCode`` (0 = succès) ;
- Pixoo-64 d'origine : ``POST http://<ip>/post`` (port 80), réponse avec ``error_code``.

Contraintes du serveur de l'appareil (ESP32) : **HTTP/1.1** seulement (HTTP/2 → 400) et la clé
``Command`` en **première position** du JSON. Le module Python ``socket`` étant exclu de GraalPy,
on passe par ``java.net.http.HttpClient`` (objet Java, partageable entre les contextes GraalPy).
`HttpTransportFactory` (bean) crée le transport de chaque appareil : les tests la remplacent.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

import java
from jakarta.inject import Singleton
from micronaut.context.annotation import ConfigurationProperties

HttpClient = java.type("java.net.http.HttpClient")
HttpRequest = java.type("java.net.http.HttpRequest")
BodyPublishers = java.type("java.net.http.HttpRequest$BodyPublishers")
BodyHandlers = java.type("java.net.http.HttpResponse$BodyHandlers")
Version = java.type("java.net.http.HttpClient$Version")
URI = java.type("java.net.URI")
Duration = java.type("java.time.Duration")


class CommandFailed(Exception):
    """L'appareil a répondu, mais refuse la commande (ReturnCode / error_code ≠ 0)."""


class HttpTransport(ABC):
    @abstractmethod
    def command(self, name: str, **fields) -> dict:
        """Envoie une commande ; renvoie la réponse décodée, lève CommandFailed si elle est refusée."""


# Pas de frozen=True : avec des valeurs par défaut, Micronaut affecte les champs après construction.
@ConfigurationProperties("pixel-studio.wifi")
@dataclass
class WifiConfig:
    connect_timeout_ms: int = 2000
    request_timeout_ms: int = 5000  # un envoi d'image prend ~1,5 s


def api_path(port: int) -> str:
    """Chemin de l'API selon le port : 80 = Pixoo-64 d'origine, sinon API de l'application (II)."""
    return "/post" if port == 80 else "/divoom_api"


def check(reply: dict) -> dict:
    """Succès si ``ReturnCode`` (II) ou ``error_code`` (Pixoo-64) vaut 0 ; ce dernier peut être un texte."""
    code = reply.get("ReturnCode", reply.get("error_code", 0))
    if code != 0:
        raise CommandFailed(str(reply.get("ReturnMessage") or code))
    return reply


class JavaHttpTransport(HttpTransport):
    def __init__(self, host: str, port: int, path: str, config: WifiConfig):
        self.url = f"http://{host}:{port}{path}"
        self.address = f"{host}:{port}"
        self.timeout = Duration.ofMillis(config.request_timeout_ms)
        self.client = (HttpClient.newBuilder().version(Version.HTTP_1_1)
                       .connectTimeout(Duration.ofMillis(config.connect_timeout_ms)).build())

    def command(self, name: str, **fields) -> dict:
        body = json.dumps({"Command": name, **fields})  # « Command » en première clé
        request = (HttpRequest.newBuilder(URI.create(self.url))
                   .header("Content-Type", "application/json")
                   .timeout(self.timeout)
                   .POST(BodyPublishers.ofString(body)).build())
        response = self.client.send(request, BodyHandlers.ofString())
        if response.statusCode() != 200:
            raise CommandFailed(f"HTTP {response.statusCode()}")
        return check(json.loads(str(response.body())))

    def __str__(self) -> str:
        return self.address


@Singleton
class HttpTransportFactory:
    def __init__(self, config: WifiConfig):
        self.config = config

    def create(self, host: str, port: int, path: str | None = None) -> HttpTransport:
        return JavaHttpTransport(host, port, path or api_path(port), self.config)
