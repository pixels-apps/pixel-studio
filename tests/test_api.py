"""Tests de bout en bout de l'API HTTP.

En environnement « test », `FakeTimeboxTransport` (tests/fake_timebox.py) remplace le transport
TCP : toute la chaîne HTTP → contrôleur → client → protocole est exercée sans matériel.
"""

import pytest
import requests

from pyronaut.test import MicronautTest, micronaut_test_fixture


def start(request, storage_dir, **properties):
    """Contexte Micronaut de test, avec un dossier de stockage dédié (jamais ~/.pixel-studio)."""
    return micronaut_test_fixture(request, MicronautTest(
        environments=["test"], transactional=False,
        properties={"timebox.storage.dir": str(storage_dir)} | properties))


@pytest.fixture
def client(request, tmp_path):
    fixture = start(request, tmp_path)
    yield requests.with_context(fixture)
    fixture.stop()


def test_state(client):
    response = client.get("/timebox/state")
    assert response.status_code == 200
    assert response.json() | {"raw": None} == {
        "view": "clock", "light_color": "ff5000", "brightness": 100, "power": True, "raw": None}


def test_color(client):
    response = client.post("/timebox/color/0000ff?brightness=50")
    assert response.status_code == 200, response.text
    state = response.json()
    assert (state["view"], state["light_color"], state["brightness"]) == ("light", "0000ff", 50), state


def test_brightness(client):
    response = client.post("/timebox/brightness/30")
    assert response.status_code == 200
    assert response.json()["brightness"] == 30


def test_view(client):
    assert client.post("/timebox/view/light").json()["view"] == "light"


def test_invalid_color(client):
    assert client.post("/timebox/color/zzz").status_code == 400


def test_brightness_out_of_range(client):
    assert client.post("/timebox/brightness/150").status_code == 400


def test_unknown_view(client):
    assert client.post("/timebox/view/disco").status_code == 400


# --- Images ---------------------------------------------------------------------------------

import struct  # noqa: E402
import zlib  # noqa: E402


def make_png(width: int = 16, height: int = 16) -> bytes:
    """PNG RGBA minimal en Python pur : diagonale rouge opaque sur fond transparent."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(
        b"\x00" + b"".join(b"\xff\x00\x00\xff" if x == y else b"\x00\x00\x00\x00" for x in range(width))
        for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def test_no_image_yet(client):
    assert client.get("/timebox/image").status_code == 404


def test_send_image_json(client):
    pixels = ["ff0000" if (x + y) % 2 else "0000ff" for y in range(16) for x in range(16)]
    response = client.post("/timebox/image", json={"pixels": pixels})
    assert response.status_code == 200, response.text
    assert response.json()["pixels"] == pixels
    assert client.get("/timebox/image").json()["pixels"] == pixels


@pytest.fixture
def pixoo(request, tmp_path):
    """Faux appareil qui imite le Pixoo (pas d'accusé 44 ni 45)."""
    fixture = start(request, tmp_path, **{"fake-timebox.model": "pixoo"})
    yield requests.with_context(fixture)
    fixture.stop()


def test_pixoo_image_without_ack(pixoo):
    """Le Pixoo affiche l'image sans l'acquitter : la lecture de l'état qui suit la confirme."""
    response = pixoo.post("/timebox/image", json={"pixels": ["ff0000", "0000ff"] * 128})
    assert response.status_code == 200, response.text


def test_pixoo_views(pixoo):
    """Changements d'écran sans accusé ; « lumière » garde la couleur et la luminosité."""
    assert pixoo.post("/timebox/color/00ff00?brightness=40").status_code == 200
    clock = pixoo.post("/timebox/view/clock")
    assert clock.status_code == 200, clock.text
    assert clock.json()["view"] == "clock"
    light = pixoo.post("/timebox/view/light")
    assert light.status_code == 200, light.text
    state = light.json()
    assert (state["view"], state["light_color"], state["brightness"]) == ("light", "00ff00", 40), state


def test_pixoo_brightness(pixoo):
    response = pixoo.post("/timebox/brightness/30")
    assert response.status_code == 200, response.text
    assert response.json()["brightness"] == 30


def test_send_image_accepts_hash_prefix(client):
    response = client.post("/timebox/image", json={"pixels": ["#00FF00"] * 256})
    assert response.status_code == 200, response.text
    assert response.json()["pixels"] == ["00ff00"] * 256


def test_send_image_wrong_size(client):
    assert client.post("/timebox/image", json={"pixels": ["ff0000"] * 10}).status_code == 400


def test_send_image_bad_color(client):
    assert client.post("/timebox/image", json={"pixels": ["red"] * 256}).status_code == 400


def test_send_png(client):
    response = client.post("/timebox/image/png", data=make_png(), headers={"Content-Type": "image/png"})
    assert response.status_code == 200, response.text
    pixels = response.json()["pixels"]
    assert pixels[0] == "ff0000" and pixels[17] == "ff0000"  # diagonale
    assert pixels[1] == "000000"  # transparent → noir


def test_send_png_wrong_size(client):
    response = client.post("/timebox/image/png", data=make_png(32, 32), headers={"Content-Type": "image/png"})
    assert response.status_code == 400


def test_send_png_garbage(client):
    response = client.post("/timebox/image/png", data=b"pas une image", headers={"Content-Type": "image/png"})
    assert response.status_code == 400



# --- Galerie --------------------------------------------------------------------------------

CHECKER = ["ff0000" if (x + y) % 2 else "0000ff" for y in range(16) for x in range(16)]


def create(client, name="Damier", pixels=CHECKER):
    response = client.post("/timebox/gallery", json={"name": name, "pixels": pixels})
    assert response.status_code == 201, response.text
    return response.json()


def test_gallery_empty(client):
    response = client.get("/timebox/gallery")
    assert response.status_code == 200
    assert response.json() == []


def test_gallery_create_get_list(client):
    item = create(client, name="  Mon   damier ")
    assert len(item["id"]) == 12 and item["name"] == "Mon damier" and item["pixels"] == CHECKER
    assert item["created"] == item["updated"]
    assert client.get(f"/timebox/gallery/{item['id']}").json() == item
    assert [i["id"] for i in client.get("/timebox/gallery").json()] == [item["id"]]


def test_gallery_update(client):
    item = create(client)
    renamed = client.put(f"/timebox/gallery/{item['id']}", json={"name": "Renommé"}).json()
    assert renamed["name"] == "Renommé" and renamed["pixels"] == CHECKER
    redrawn = client.put(f"/timebox/gallery/{item['id']}", json={"pixels": ["00ff00"] * 256}).json()
    assert redrawn["name"] == "Renommé" and redrawn["pixels"] == ["00ff00"] * 256


def test_gallery_validation(client):
    assert client.post("/timebox/gallery", json={"name": " ", "pixels": CHECKER}).status_code == 400
    assert client.post("/timebox/gallery", json={"name": "x" * 61, "pixels": CHECKER}).status_code == 400
    assert client.post("/timebox/gallery", json={"name": "ok", "pixels": ["ff0000"]}).status_code == 400
    item = create(client)
    assert client.put(f"/timebox/gallery/{item['id']}", json={"pixels": ["zz"] * 256}).status_code == 400


def test_gallery_not_found(client):
    assert client.get("/timebox/gallery/000000000000").status_code == 404
    assert client.get("/timebox/gallery/..%2F..%2Fetc").status_code == 404
    assert client.delete("/timebox/gallery/000000000000").status_code == 404


def test_gallery_delete(client):
    item = create(client)
    assert client.delete(f"/timebox/gallery/{item['id']}").status_code == 204
    assert client.get(f"/timebox/gallery/{item['id']}").status_code == 404
    assert client.get("/timebox/gallery").json() == []


def test_gallery_send(client):
    item = create(client)
    response = client.post(f"/timebox/gallery/{item['id']}/send")
    assert response.status_code == 200, response.text
    assert client.get("/timebox/image").json()["pixels"] == CHECKER


def test_last_image_survives_restart(request, tmp_path):
    first = start(request, tmp_path)
    try:
        assert requests.with_context(first).post("/timebox/image", json={"pixels": CHECKER}).status_code == 200
    finally:
        first.stop()
    second = start(request, tmp_path)
    try:
        assert requests.with_context(second).get("/timebox/image").json()["pixels"] == CHECKER
    finally:
        second.stop()
