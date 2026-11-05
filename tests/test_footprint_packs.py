from pathlib import Path

import pytest

from maps import footprint_packs

FIXTURE = Path(__file__).parent / "fixtures" / "sample.fpk.gz"


def signed_area(r):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1])) / 2


def test_reads_the_pack_the_javascript_writes():
    header, rings = footprint_packs.read(FIXTURE)
    assert (header["name"], header["w"], header["h"], header["v"]) == ("Fixture", 2000, 1000, 1)
    assert "OpenStreetMap" in header["credit"]
    assert len(rings) == 3 == header["rings"]
    assert rings[0][0] == pytest.approx((-100, -100))
    assert signed_area(rings[0]) * signed_area(rings[1]) < 0      # courtyard wound the other way
    assert max(x for x, _ in rings[2]) == pytest.approx(1000)      # trimmed to the pack's edge


def test_rejects_other_files(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"PNG not a pack")
    with pytest.raises(ValueError):
        footprint_packs.read(f)


def test_thumbnail_draws_the_pack(tmp_path):
    from PIL import Image
    from maps import city_thumbs
    out = city_thumbs.thumbnail(FIXTURE, tmp_path / "t.jpg")
    im = Image.open(out).convert("L")
    assert im.size == city_thumbs.SIZE_PX
    w, h = im.size
    # the courtyard (inside the outer ring) stays paper-coloured; the ring itself is ink
    ring_px = im.getpixel((int(w / 2 + 70 / 2000 * w), h // 2))
    hole_px = im.getpixel((w // 2, h // 2))
    assert ring_px < 100 < hole_px
