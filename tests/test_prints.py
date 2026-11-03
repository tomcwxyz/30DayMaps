"""Print maker: pure layout, grid and parsing tests, plus a synthetic render."""
import geopandas as gpd
import pytest
from shapely.geometry import box

from maps import prints


@pytest.mark.parametrize("e,n,tile", [(425000, 564000, "NZ"), (530000, 180000, "TQ"),
                                      (325000, 673000, "NT"), (358000, 172000, "ST")])
def test_grid_tiles(e, n, tile):
    assert prints.grid_tile(e, n) == tile


def test_window_spanning_tiles_lists_each():
    assert prints.tiles_for((399000, 560000, 401000, 562000)) == ["NY", "NZ"]


@pytest.mark.parametrize("lat,lon,gb", [(54.97, -1.61, True), (53.35, -6.26, False),
                                        (54.6, -5.93, False), (48.86, 2.35, False), (57.48, -4.22, True)])
def test_source_follows_great_britain(lat, lon, gb):
    assert prints.in_great_britain(lat, lon) is gb


def test_os_refused_outside_gb():
    spec = prints.Spec(name="Paris", lat=48.86, lon=2.35, title="Paris", source="os")
    with pytest.raises(ValueError, match="Great Britain"):
        prints.pick_source(spec)


def test_ground_window_matches_map_box_shape():
    pw, ph = prints.paper_mm("A3")
    lay = prints.layout(pw, ph, False)
    minx, miny, maxx, maxy = prints.ground_window((0, 0), 9000, lay["map"], pw, ph)
    box_ratio = (lay["map"][3] * ph) / (lay["map"][2] * pw)
    assert maxx - minx == pytest.approx(9000)
    assert (maxy - miny) / (maxx - minx) == pytest.approx(box_ratio)


def test_landscape_swaps_paper():
    assert prints.paper_mm("A3", landscape=True) == (420, 297)


def test_overpass_ways_and_multipolygons_become_polygons():
    sq = lambda x: [{"lon": x, "lat": 0}, {"lon": x + 1, "lat": 0}, {"lon": x + 1, "lat": 1},
                    {"lon": x, "lat": 1}, {"lon": x, "lat": 0}]
    payload = {"elements": [
        {"type": "way", "geometry": sq(0)},
        {"type": "way", "geometry": sq(5)[:-1]},  # not closed: ignored
        {"type": "relation", "members": [
            {"type": "way", "role": "outer", "geometry": [{"lon": 10, "lat": 0}, {"lon": 14, "lat": 0}, {"lon": 14, "lat": 4}]},
            {"type": "way", "role": "outer", "geometry": [{"lon": 14, "lat": 4}, {"lon": 10, "lat": 4}, {"lon": 10, "lat": 0}]},
            {"type": "way", "role": "inner", "geometry": [{"lon": 11, "lat": 1}, {"lon": 13, "lat": 1}, {"lon": 13, "lat": 3}, {"lon": 11, "lat": 3}, {"lon": 11, "lat": 1}]},
        ]},
    ]}
    polys = prints.osm_polygons(payload)
    assert len(polys) == 2
    assert sorted(p.area for p in polys) == pytest.approx([1, 12])


def test_spec_from_preset_and_overrides():
    import argparse
    ns = argparse.Namespace(place="York", lat=None, lon=None, name=None, title="Ebor", subtitle=None,
                            kicker=None, note=None, paper="A2", landscape=True, width_km=None,
                            theme="night", ink=None, background=None, source="auto", dpi=200,
                            formats="web")
    spec = prints.spec_from_args(ns)
    assert (spec.name, spec.title, spec.paper, spec.formats) == ("York", "Ebor", "A2", ["web"])
    assert spec.slug == "york"


def test_render_writes_png_and_pdf(tmp_path):
    spec = prints.Spec(name="Testville", lat=54.97, lon=-1.61, title="Testville",
                       subtitle="A long subtitle that should wrap onto more than one line on a small sheet",
                       kicker="30 Day Map Challenge", paper="A4", theme="night")
    b = gpd.GeoDataFrame(geometry=[box(i * 30, j * 30, i * 30 + 20, j * 30 + 12)
                                   for i in range(30) for j in range(40)], crs=27700)
    pw, ph = prints.paper_mm("A4")
    bounds = prints.ground_window((450, 600), 900, prints.layout(pw, ph, True)["map"], pw, ph)
    png = prints.draw(spec, b, bounds, "os", tmp_path / "t.png", dpi=100)
    pdf = prints.draw(spec, b, bounds, "osm", tmp_path / "t.pdf", dpi=100, vector=True)
    assert png.stat().st_size > 5000 and pdf.stat().st_size > 5000
