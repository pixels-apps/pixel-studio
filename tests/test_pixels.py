"""Tests des images communes : tailles, conversion 16 ↔ 64."""

import pytest

from pixel_studio import pixels as px

CHECKER16 = ["ff0000" if (x + y) % 2 else "0000ff" for y in range(16) for x in range(16)]


def test_size_of():
    assert px.size_of(["000000"] * 256) == 16
    assert px.size_of(["000000"] * 4096) == 64
    with pytest.raises(ValueError, match="256 \\(16×16\\) ou 4096 \\(64×64\\)"):
        px.size_of(["000000"] * 1024)


def test_parse_pixels_with_size():
    assert len(px.parse_pixels(["00ff00"] * 4096)) == 4096
    with pytest.raises(ValueError):
        px.parse_pixels(["00ff00"] * 256, size=64)


def test_enlarge_nearest_neighbour():
    big = px.resize(CHECKER16, 64)
    assert len(big) == 4096
    # chaque pixel devient un carré 4×4
    for y in range(64):
        for x in range(64):
            assert big[x + 64 * y] == CHECKER16[x // 4 + 16 * (y // 4)]


def test_shrink_back_is_identity():
    assert px.resize(px.resize(CHECKER16, 64), 16) == CHECKER16


def test_shrink_keeps_most_frequent_colour():
    big = ["000000"] * 4096
    for dy in range(4):  # bloc (0, 0) : 10 rouges, 6 noirs → rouge
        for dx in range(4):
            if dy * 4 + dx < 10:
                big[dx + 64 * dy] = "ff0000"
    big[4] = big[5] = "00ff00"  # bloc (1, 0) : 2 verts, 14 noirs → noir
    small = px.resize(big, 16)
    assert (small[0], small[1]) == ("ff0000", "000000")


def test_shrink_tie_takes_first_in_block():
    big = ["000000"] * 4096
    for dy in range(4):
        for dx in range(4):
            big[dx + 64 * dy] = "ffffff" if dy < 2 else "000000"  # 8 blancs (en haut), 8 noirs
    assert px.resize(big, 16)[0] == "ffffff"


def test_resize_unknown_size():
    with pytest.raises(ValueError):
        px.resize(CHECKER16, 32)
