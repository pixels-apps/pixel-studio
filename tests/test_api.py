"""Tests de bout en bout de l'API HTTP.

En environnement « test », `FakeTransportFactory` (tests/fake_bluetooth.py) remplace le relais
Bluetooth : toute la chaîne HTTP → contrôleur → client → protocole est exercée sans matériel.
"""

import json

import pytest
import requests

from pyronaut.test import MicronautTest, micronaut_test_fixture


def start(request, storage_dir, **properties):
    """Contexte Micronaut de test, avec un dossier de stockage dédié (jamais ~/.pixel-studio)."""
    return micronaut_test_fixture(request, MicronautTest(
        environments=["test"], transactional=False,
        properties={"pixel-studio.storage.dir": str(storage_dir)} | properties))


@pytest.fixture
def client(request, tmp_path):
    fixture = start(request, tmp_path)
    yield requests.with_context(fixture)
    fixture.stop()


def test_state(client):
    response = client.get("/device/state")
    assert response.status_code == 200
    assert response.json() | {"raw": None} == {
        "view": "clock", "light_color": "ff5000", "clock_color": "0000ff", "brightness": 100, "power": True,
        "raw": None}


def test_color(client):
    response = client.post("/device/color/0000ff?brightness=50")
    assert response.status_code == 200, response.text
    state = response.json()
    assert (state["view"], state["light_color"], state["brightness"]) == ("light", "0000ff", 50), state


def test_clock_color(client):
    response = client.post("/device/clock/color/00d800")
    assert response.status_code == 200, response.text
    state = response.json()
    assert (state["view"], state["clock_color"]) == ("clock", "00d800"), state
    assert client.post("/device/clock/color/zzz").status_code == 400


def test_brightness(client):
    response = client.post("/device/brightness/30")
    assert response.status_code == 200
    assert response.json()["brightness"] == 30


def test_view(client):
    assert client.post("/device/view/light").json()["view"] == "light"


def test_invalid_color(client):
    assert client.post("/device/color/zzz").status_code == 400


def test_brightness_out_of_range(client):
    assert client.post("/device/brightness/150").status_code == 400


def test_unknown_view(client):
    assert client.post("/device/view/disco").status_code == 400


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
    assert client.get("/device/image").status_code == 404


def test_send_image_json(client):
    pixels = ["ff0000" if (x + y) % 2 else "0000ff" for y in range(16) for x in range(16)]
    response = client.post("/device/image", json={"pixels": pixels})
    assert response.status_code == 200, response.text
    assert response.json()["pixels"] == pixels
    assert client.get("/device/image").json()["pixels"] == pixels


@pytest.fixture
def pixoo(request, tmp_path):
    """Faux appareil qui imite le Pixoo (pas d'accusé 44 ni 45)."""
    fixture = start(request, tmp_path, **{"fake-bluetooth.model": "pixoo"})
    yield requests.with_context(fixture)
    fixture.stop()


def test_pixoo_image_without_ack(pixoo):
    """Le Pixoo affiche l'image sans l'acquitter : la lecture de l'état qui suit la confirme."""
    response = pixoo.post("/device/image", json={"pixels": ["ff0000", "0000ff"] * 128})
    assert response.status_code == 200, response.text


def test_pixoo_views(pixoo):
    """Changements d'écran sans accusé ; « lumière » garde la couleur et la luminosité."""
    assert pixoo.post("/device/color/00ff00?brightness=40").status_code == 200
    clock = pixoo.post("/device/view/clock")
    assert clock.status_code == 200, clock.text
    assert clock.json()["view"] == "clock"
    light = pixoo.post("/device/view/light")
    assert light.status_code == 200, light.text
    state = light.json()
    assert (state["view"], state["light_color"], state["brightness"]) == ("light", "00ff00", 40), state


def test_pixoo_brightness(pixoo):
    response = pixoo.post("/device/brightness/30")
    assert response.status_code == 200, response.text
    assert response.json()["brightness"] == 30


def test_send_image_accepts_hash_prefix(client):
    response = client.post("/device/image", json={"pixels": ["#00FF00"] * 256})
    assert response.status_code == 200, response.text
    assert response.json()["pixels"] == ["00ff00"] * 256


def test_send_image_wrong_size(client):
    assert client.post("/device/image", json={"pixels": ["ff0000"] * 10}).status_code == 400


def test_send_image_bad_color(client):
    assert client.post("/device/image", json={"pixels": ["red"] * 256}).status_code == 400


def test_send_png(client):
    response = client.post("/device/image/png", data=make_png(), headers={"Content-Type": "image/png"})
    assert response.status_code == 200, response.text
    pixels = response.json()["pixels"]
    assert pixels[0] == "ff0000" and pixels[17] == "ff0000"  # diagonale
    assert pixels[1] == "000000"  # transparent → noir


def test_send_png_wrong_size(client):
    response = client.post("/device/image/png", data=make_png(32, 32), headers={"Content-Type": "image/png"})
    assert response.status_code == 400


def test_send_png_garbage(client):
    response = client.post("/device/image/png", data=b"pas une image", headers={"Content-Type": "image/png"})
    assert response.status_code == 400



# --- Galerie --------------------------------------------------------------------------------

CHECKER = ["ff0000" if (x + y) % 2 else "0000ff" for y in range(16) for x in range(16)]


def create(client, name="Damier", pixels=CHECKER):
    response = client.post("/gallery", json={"name": name, "pixels": pixels})
    assert response.status_code == 201, response.text
    return response.json()


def test_gallery_empty(client):
    response = client.get("/gallery")
    assert response.status_code == 200
    assert response.json() == []


def test_gallery_create_get_list(client):
    item = create(client, name="  Mon   damier ")
    assert len(item["id"]) == 12 and item["name"] == "Mon damier" and item["pixels"] == CHECKER
    assert item["created"] == item["updated"]
    assert client.get(f"/gallery/{item['id']}").json() == item
    assert [i["id"] for i in client.get("/gallery").json()] == [item["id"]]


def test_gallery_update(client):
    item = create(client)
    renamed = client.put(f"/gallery/{item['id']}", json={"name": "Renommé"}).json()
    assert renamed["name"] == "Renommé" and renamed["pixels"] == CHECKER
    redrawn = client.put(f"/gallery/{item['id']}", json={"pixels": ["00ff00"] * 256}).json()
    assert redrawn["name"] == "Renommé" and redrawn["pixels"] == ["00ff00"] * 256


def test_gallery_validation(client):
    assert client.post("/gallery", json={"name": " ", "pixels": CHECKER}).status_code == 400
    assert client.post("/gallery", json={"name": "x" * 61, "pixels": CHECKER}).status_code == 400
    assert client.post("/gallery", json={"name": "ok", "pixels": ["ff0000"]}).status_code == 400
    item = create(client)
    assert client.put(f"/gallery/{item['id']}", json={"pixels": ["zz"] * 256}).status_code == 400


def test_gallery_not_found(client):
    assert client.get("/gallery/000000000000").status_code == 404
    assert client.get("/gallery/..%2F..%2Fetc").status_code == 404
    assert client.delete("/gallery/000000000000").status_code == 404


def test_gallery_delete(client):
    item = create(client)
    assert client.delete(f"/gallery/{item['id']}").status_code == 204
    assert client.get(f"/gallery/{item['id']}").status_code == 404
    assert client.get("/gallery").json() == []


def test_gallery_send(client):
    item = create(client)
    response = client.post(f"/gallery/{item['id']}/send")
    assert response.status_code == 200, response.text
    assert client.get("/device/image").json()["pixels"] == CHECKER


def test_last_image_survives_restart(request, tmp_path):
    first = start(request, tmp_path)
    try:
        assert requests.with_context(first).post("/device/image", json={"pixels": CHECKER}).status_code == 200
    finally:
        first.stop()
    second = start(request, tmp_path)
    try:
        assert requests.with_context(second).get("/device/image").json()["pixels"] == CHECKER
    finally:
        second.stop()


def test_legacy_last_image(request, tmp_path):
    """La dernière image d'avant les appareils multiples revient à l'appareil par défaut."""
    (tmp_path / "last-image.json").write_text(json.dumps({"pixels": CHECKER}), encoding="utf-8")
    fixture = start(request, tmp_path)
    try:
        assert requests.with_context(fixture).get("/device/image").json()["pixels"] == CHECKER
    finally:
        fixture.stop()


# --- Appareils ------------------------------------------------------------------------------

def test_devices_default(client):
    """Sans devices.json : un seul appareil, Bluetooth derrière le relais configuré."""
    response = client.get("/devices")
    assert response.status_code == 200, response.text
    devices = response.json()
    assert devices["active"] == "bluetooth"
    assert [(d["id"], d["kind"], d["size"], d["active"]) for d in devices["devices"]] == [
        ("bluetooth", "bluetooth", 16, True)]
    assert set(devices["devices"][0]["capabilities"]) == {"color", "views"}
    assert client.get("/device").json()["name"] == "Divoom Bluetooth"


def test_activate_device(client, tmp_path):
    response = client.put("/devices/active", json={"id": "bluetooth"})
    assert response.status_code == 200, response.text
    assert response.json()["active"] == "bluetooth"
    saved = json.loads((tmp_path / "devices.json").read_text(encoding="utf-8"))
    assert saved["active"] == "bluetooth" and saved["devices"][0]["kind"] == "bluetooth"
    assert client.put("/devices/active", json={"id": "inconnu"}).status_code == 404


def test_devices_from_file(request, tmp_path):
    """devices.json décide des appareils et de l'appareil actif ; chacun a sa dernière image."""
    (tmp_path / "devices.json").write_text(json.dumps({"active": "salon", "devices": [
        {"id": "bureau", "name": "Timebox du bureau", "kind": "bluetooth", "host": "127.0.0.1", "port": 9},
        {"id": "salon", "name": "Pixoo du salon", "kind": "bluetooth", "host": "127.0.0.2", "port": 9},
    ]}), encoding="utf-8")
    fixture = start(request, tmp_path)
    try:
        client = requests.with_context(fixture)
        assert client.get("/device").json()["name"] == "Pixoo du salon"
        assert client.post("/device/image", json={"pixels": CHECKER}).status_code == 200
        assert client.put("/devices/active", json={"id": "bureau"}).json()["active"] == "bureau"
        assert client.get("/device/image").status_code == 404  # pas d'image envoyée au bureau
        client.put("/devices/active", json={"id": "salon"})
        assert client.get("/device/image").json()["pixels"] == CHECKER
    finally:
        fixture.stop()


# --- Tailles d'image (16×16, 64×64) -----------------------------------------------------------

BIG = ["00ff00" if (x // 8 + y // 8) % 2 else "ff00ff" for y in range(64) for x in range(64)]


def test_gallery_sizes(client):
    small = create(client)
    big = create(client, name="Grand", pixels=BIG)
    assert (small["size"], big["size"]) == (16, 64)
    assert {i["id"]: i["size"] for i in client.get("/gallery").json()} == {small["id"]: 16, big["id"]: 64}


def test_legacy_gallery_item_has_size(client, tmp_path):
    (tmp_path / "gallery").mkdir()
    (tmp_path / "gallery" / "0123456789ab.json").write_text(json.dumps({
        "id": "0123456789ab", "name": "Ancienne", "pixels": CHECKER,
        "created": "2026-10-01T00:00:00+00:00", "updated": "2026-10-01T00:00:00+00:00"}), encoding="utf-8")
    assert client.get("/gallery/0123456789ab").json()["size"] == 16


def test_send_wrong_size_is_refused(client):
    """Le faux appareil Bluetooth affiche du 16×16 : une image 64×64 est refusée (409)."""
    response = client.post("/device/image", json={"pixels": BIG})
    assert response.status_code == 409, response.text
    assert "64×64" in response.json()["message"] and "convertissez" in response.json()["message"]
    big = create(client, name="Grand", pixels=BIG)
    assert client.post(f"/gallery/{big['id']}/send").status_code == 409


def test_send_image_returns_size(client):
    response = client.post("/device/image", json={"pixels": CHECKER})
    assert response.json()["size"] == 16
    assert client.get("/device/image").json()["size"] == 16


def test_gallery_convert(client):
    item = create(client, name="Damier")
    response = client.post(f"/gallery/{item['id']}/convert?size=64")
    assert response.status_code == 201, response.text
    copy = response.json()
    assert (copy["name"], copy["size"], len(copy["pixels"])) == ("Damier (64×64)", 64, 4096)
    assert copy["id"] != item["id"]
    assert client.get(f"/gallery/{item['id']}").json()["pixels"] == CHECKER  # original inchangé
    back = client.post(f"/gallery/{copy['id']}/convert?size=16").json()
    assert (back["name"], back["pixels"]) == ("Damier (64×64) (16×16)", CHECKER)
    assert client.post(f"/gallery/{back['id']}/send").status_code == 200


def test_gallery_convert_errors(client):
    item = create(client, name="x" * 60)
    copy = client.post(f"/gallery/{item['id']}/convert?size=64").json()
    assert len(copy["name"]) == 60 and copy["name"].endswith(" (64×64)")
    assert client.post(f"/gallery/{item['id']}/convert?size=32").status_code == 400
    assert client.post("/gallery/000000000000/convert?size=64").status_code == 404


# --- Appareils Wi-Fi (faux Pixoo-64) -----------------------------------------------------------

def add_pixoo64(client, host="192.168.1.50"):
    response = client.post("/devices", json={"name": "Pixoo-64 II", "kind": "wifi", "host": host})
    assert response.status_code == 201, response.text
    return response.json()


def test_add_and_use_wifi_device(client, tmp_path):
    info = add_pixoo64(client)
    assert (info["id"], info["kind"], info["size"], info["address"], info["active"]) == (
        "pixoo-64-ii", "wifi", 64, "192.168.1.50:9000", False)
    assert set(info["capabilities"]) == {"screen", "channels"}
    assert client.put("/devices/active", json={"id": info["id"]}).status_code == 200

    state = client.get("/device/state").json()
    assert (state["view"], state["brightness"], state["power"]) == ("visualizer", 100, True)
    assert client.post("/device/brightness/40").json()["brightness"] == 40
    assert client.post("/device/screen/off").json()["power"] is False
    assert client.post("/device/channel/faces").json()["view"] == "faces"
    assert client.post("/device/color/ff0000").status_code == 400  # pas de couleur unie
    assert client.post("/device/view/clock").status_code == 400

    assert client.post("/device/image", json={"pixels": BIG}).status_code == 200
    assert client.post("/device/image", json={"pixels": CHECKER}).status_code == 409
    assert client.get("/device/image").json()["size"] == 64

    saved = json.loads((tmp_path / "devices.json").read_text(encoding="utf-8"))
    assert saved["active"] == "pixoo-64-ii"
    assert saved["devices"][-1] == {"id": "pixoo-64-ii", "name": "Pixoo-64 II", "kind": "wifi",
                                     "host": "192.168.1.50", "port": 9000}


def test_add_device_validation(client):
    assert client.post("/devices", json={"name": " ", "kind": "wifi", "host": "1.2.3.4"}).status_code == 400
    assert client.post("/devices", json={"name": "x", "kind": "zigbee", "host": "1.2.3.4"}).status_code == 400
    assert client.post("/devices", json={"name": "x", "kind": "wifi", "host": "a b"}).status_code == 400
    assert client.post("/devices", json={"name": "x", "kind": "wifi", "host": "h", "port": 0}).status_code == 400
    first, second = add_pixoo64(client), add_pixoo64(client, host="192.168.1.71")
    assert (first["id"], second["id"]) == ("pixoo-64-ii", "pixoo-64-ii-2")


def test_test_device(client):
    response = client.post("/devices/test", json={"name": "Pixoo-64 II", "kind": "wifi", "host": "192.168.1.50"})
    assert response.status_code == 200, response.text
    assert response.json()["view"] == "visualizer"
    response = client.post("/devices/test", json={"name": "Éteint", "kind": "wifi", "host": "injoignable"})
    assert response.status_code == 503
    assert response.json()["message"].startswith("Éteint : injoignable:9000 injoignable")
    assert [d["id"] for d in client.get("/devices").json()["devices"]] == ["bluetooth"]  # rien d'enregistré


def test_remove_device(client):
    info = add_pixoo64(client)
    client.put("/devices/active", json={"id": info["id"]})
    assert client.delete(f"/devices/{info['id']}").status_code == 204
    devices = client.get("/devices").json()
    assert devices["active"] == "bluetooth" and len(devices["devices"]) == 1
    assert client.delete("/devices/bluetooth").status_code == 409  # dernier appareil
    assert client.delete("/devices/inconnu").status_code == 404


def test_wifi_unreachable_is_503(client):
    info = add_pixoo64(client, host="injoignable")
    client.put("/devices/active", json={"id": info["id"]})
    response = client.get("/device/state")
    assert response.status_code == 503
    assert response.json()["message"].startswith("Pixoo-64 II indisponible : injoignable:9000 injoignable")
