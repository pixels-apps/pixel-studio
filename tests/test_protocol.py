"""Tests du protocole, à partir d'octets réellement échangés avec l'appareil (docs/protocol.md)."""

import pytest

from timebox.evo import protocol as p


def test_encode_brightness():
    assert p.encode(p.set_brightness(50)).hex(" ") == "01 04 00 74 32 aa 00 02"


def test_encode_light_red():
    frame = p.encode(p.set_light(p.parse_color("ff0000"), brightness=100))
    assert frame.hex(" ") == "01 0d 00 45 01 ff 00 00 64 00 01 00 00 00 b7 01 02"


def test_encode_get_view():
    assert p.encode(p.get_view()).hex(" ") == "01 03 00 46 49 00 02"


def test_decoder_handles_split_and_concatenated_frames():
    stream = bytes.fromhex("01 06 00 04 31 55 64 f4 00 02 01 06 00 04 45 55 01 a5 00 02")
    decoder = p.FrameDecoder()
    assert decoder.feed(stream[:7]) == []
    frames = decoder.feed(stream[7:])
    responses = [p.parse_response(f) for f in frames]
    assert responses == [
        p.Response(command=0x31, status=0x55, data=b"\x64"),
        p.Response(command=0x45, status=0x55, data=b"\x01"),
    ]


def test_decoder_skips_garbage_and_bad_checksum():
    good = bytes.fromhex("01 06 00 04 32 55 1e af 00 02")
    bad = bytes.fromhex("01 06 00 04 32 55 1e 00 00 02")
    frames = p.FrameDecoder().feed(b"\xff\x00" + bad + good)
    assert frames == [good]


def test_parse_state_from_real_response():
    frame = bytes.fromhex(
        "01 19 00 04 46 55 01 00 00 00 ff 00 64 00 01 03 64 00 00 00 ff 00 01 00 00 00 84 03 02")
    response = p.parse_response(frame)
    assert response is not None and response.ok and response.command == p.GET_VIEW
    state = p.parse_state(response.data)
    assert state.view == p.VIEW_LIGHT
    assert state.light_color == "00ff00"
    assert state.brightness == 100
    assert state.power is True


@pytest.mark.parametrize("value", ["fff", "gg0000", "#12345"])
def test_parse_color_rejects_invalid(value):
    with pytest.raises(ValueError):
        p.parse_color(value)


def test_brightness_out_of_range():
    with pytest.raises(ValueError):
        p.set_brightness(101)


# --- Images (commande 44) ---------------------------------------------------------------

def _payload(frame: bytes) -> bytes:
    return frame[3:-3]


def test_checkerboard_bit_packing():
    """Vecteur calculé à la main : damier bleu/rouge, 2 couleurs → 1 bit par pixel.

    Le pixel (0, 0) est bleu → index 0, rouge → index 1. Les bits sont rangés poids faible
    en premier : une ligne « bleu, rouge, bleu… » donne 0b10101010 = aa, la suivante 55.
    """
    blue, red = b"\x00\x00\xff", b"\xff\x00\x00"
    pixels = [red if (x + y) % 2 else blue for y in range(16) for x in range(16)]
    frame = p.encode_frame(pixels)
    assert frame[:7].hex(" ") == "aa 2d 00 00 00 00 02"  # aa | longueur 45 | T=0 | R=0 | 2 couleurs
    assert frame[7:13] == blue + red
    assert frame[13:] == bytes.fromhex("aaaa5555") * 8
    assert p.decode_frame(frame) == (pixels, 0)


# Flèche blanche vers le haut (+ un pixel dans chaque coin bas) : trame complète envoyée le
# 2026-10-09 et affichée correctement par l'appareil (orientation x + 16·y vérifiée).
ARROW_FRAME = bytes.fromhex(
    "01340044000a0a04aa2d0000000002000000ffffff4000e000f001f803400040004000400040004000400040"
    "004000400040000180b30a02")


def test_arrow_frame_validated_on_device():
    pixels, duration = p.decode_frame(_payload(ARROW_FRAME)[len(p.IMAGE_HEADER):])
    white = b"\xff\xff\xff"
    assert duration == 0
    assert pixels[6] == white and pixels[5] != white  # pointe en haut, colonne 6
    assert pixels[15 * 16] == white and pixels[255] == white  # coins du bas
    assert p.encode(p.set_image(pixels)) == ARROW_FRAME


@pytest.mark.parametrize("colors,bits,frame_length", [
    (1, 1, 7 + 3 + 32), (2, 1, 7 + 6 + 32), (3, 2, 7 + 9 + 64), (16, 4, 7 + 48 + 128),
    (17, 5, 7 + 51 + 160), (256, 8, 7 + 768 + 256)])
def test_encode_frame_sizes(colors, bits, frame_length):
    pixels = [bytes([i % colors, 0, 0]) for i in range(256)]
    frame = p.encode_frame(pixels)
    assert p.bits_per_pixel(colors) == bits
    assert len(frame) == frame_length
    assert int.from_bytes(frame[1:3], "little") == frame_length
    assert frame[6] == colors % 256
    assert p.decode_frame(frame)[0] == pixels


def test_set_image_static_defaults():
    payload = p.set_image([b"\x00\xff\x00"] * 256)
    # T=0000 et R=00 : seule combinaison validée pour l'affichage (R=01 n'affiche rien)
    assert payload.hex(" ")[:41] == "44 00 0a 0a 04 aa 2a 00 00 00 00 01 00 ff"


def test_image_needs_256_pixels():
    with pytest.raises(ValueError):
        p.set_image([b"\x00\x00\x00"] * 255)


def test_parse_pixels():
    assert p.parse_pixels(["#ff0000"] + ["00ff00"] * 255)[:2] == [b"\xff\x00\x00", b"\x00\xff\x00"]
    with pytest.raises(ValueError):
        p.parse_pixels(["zz0000"] + ["00ff00"] * 255)
