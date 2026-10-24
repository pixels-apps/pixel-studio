"""Tests de WifiDevice avec le faux Pixoo-64, sans contexte Micronaut."""

import base64

import pytest

from fake_wifi import UNREACHABLE, FakePixoo64
from pixel_studio.device import DeviceUnavailable
from pixel_studio.wifi.device import WifiDevice
from pixel_studio.wifi.transport import CommandFailed, api_path, check

RED = [b"\xff\x00\x00"] * 4096


def make(host: str = "192.168.1.50") -> tuple[WifiDevice, FakePixoo64]:
    fake = FakePixoo64(host, 9000)
    return WifiDevice("pixoo64", "Pixoo-64", fake), fake


def test_state():
    device, fake = make()
    state = device.state()
    assert (state.view, state.brightness, state.power, state.light_color) == ("visualizer", 100, True, None)


def test_brightness_screen_channel():
    device, fake = make()
    assert device.set_brightness(30).brightness == 30
    assert device.set_screen(False).power is False
    assert device.set_channel("faces").view == "faces"
    with pytest.raises(ValueError):
        device.set_channel("disco")


def test_send_image_resets_gif_id_and_encodes_rgb():
    device, fake = make()
    device.send_image(RED)
    assert fake.commands[-2:] == ["Draw/ResetHttpGifId", "Draw/SendHttpGif"]
    assert fake.image == b"\xff\x00\x00" * 4096


def test_send_image_wrong_size():
    device, _ = make()
    with pytest.raises(ValueError):
        device.send_image(RED[:256])


def test_unreachable():
    device, _ = make(UNREACHABLE)
    with pytest.raises(DeviceUnavailable, match="injoignable"):
        device.state()


def test_check_both_envelopes():
    assert check({"ReturnCode": 0}) == {"ReturnCode": 0}
    assert check({"error_code": 0}) == {"error_code": 0}
    with pytest.raises(CommandFailed, match="Only accept"):
        check({"ReturnCode": 1, "ReturnMessage": "Only accept JSON parameters"})
    with pytest.raises(CommandFailed, match="illegal json"):
        check({"error_code": "Request data illegal json"})


def test_api_path():
    assert (api_path(9000), api_path(80)) == ("/divoom_api", "/post")
