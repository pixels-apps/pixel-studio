"""Tests de BluetoothDevice avec le faux appareil, sans contexte Micronaut."""

from fake_bluetooth import FakeBluetoothTransport
from pixel_studio.bluetooth import protocol as p
from pixel_studio.bluetooth.device import BluetoothDevice


def make(model: str = "evo") -> tuple[BluetoothDevice, FakeBluetoothTransport]:
    transport = FakeBluetoothTransport(model)
    return BluetoothDevice("test", "Test", transport, reply_timeout_ms=500), transport


def test_clock_keeps_settings():
    device, fake = make()
    fake.clock = bytes.fromhex("00d800") + bytes([2, 1, 1, 0, 1])  # vert, style 2, heure, météo, calendrier
    state = device.set_view("clock")
    assert state.view == "clock"
    assert fake.clock == bytes.fromhex("00d800") + bytes([2, 1, 1, 0, 1])


def test_clock_keeps_dark_color():
    """Pas de couleur imposée : une horloge très sombre reste telle quelle (l'état la montre)."""
    device, fake = make()
    fake.clock = bytes.fromhex("0f0000") + bytes([0, 1, 1, 1, 1])
    assert device.set_view("clock").clock_color == "0f0000"
    assert fake.clock == bytes.fromhex("0f0000") + bytes([0, 1, 1, 1, 1])


def test_clock_color_keeps_style():
    device, fake = make()
    fake.clock = bytes.fromhex("0f0000") + bytes([2, 1, 0, 1, 0])
    state = device.set_clock_color(bytes.fromhex("00d800"))
    assert (state.view, state.clock_color) == ("clock", "00d800")
    assert fake.clock == bytes.fromhex("00d800") + bytes([2, 1, 0, 1, 0])


def test_light_keeps_brightness_zero():
    device, fake = make("pixoo")
    fake.brightness = 0
    assert device.set_view("light").brightness == 0


def test_parse_clock_from_real_response():
    data = bytes.fromhex("00 00 00 33 44 ff 53 00 01 03 53 00 ff ff ff 00 01 00 00 00".replace(" ", ""))
    assert p.parse_state(data).clock == p.Clock(color="ffffff", style=0, time=True, weather=False,
                                                 temperature=False, calendar=False)


def test_set_clock_frame():
    assert p.set_clock(bytes.fromhex("ff0000"), style=2, weather=True).hex(" ") == "45 00 01 02 01 01 00 00 ff 00 00"
