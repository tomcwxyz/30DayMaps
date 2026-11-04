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


def _tile(features, extent=4096):
    import mapbox_vector_tile
    return mapbox_vector_tile.encode([{"name": "building", "features": features}],
                                     default_options={"extents": extent, "y_coord_down": True, "quantize_bounds": None})


def test_tile_buildings_keep_holes_and_land_in_the_right_place():
    from maps import osm_tiles
    from shapely.geometry import Polygon
    courtyard = Polygon([(100, 100), (500, 100), (500, 500), (100, 500)], [[(200, 200), (400, 200), (400, 400), (200, 400)]])
    data = _tile([{"geometry": courtyard.wkt, "properties": {}}, {"geometry": "POINT (5 5)", "properties": {}}])
    polys = osm_tiles.decode_buildings(data, 8100, 5100)
    assert len(polys) == 1 and len(polys[0].interiors) == 1
    unit = osm_tiles.EARTH / (4096 * 2 ** 14)
    assert polys[0].area == pytest.approx((400 ** 2 - 200 ** 2) * unit ** 2, rel=0.01)
    minx, miny, maxx, maxy = polys[0].bounds
    assert minx == pytest.approx(8100 * 4096 * unit - osm_tiles.EARTH / 2 + 100 * unit, abs=unit)
    assert maxy == pytest.approx(osm_tiles.EARTH / 2 - (5100 * 4096 + 100) * unit, abs=unit)  # y flipped to north-up


def test_tile_margins_are_trimmed_so_neighbours_only_just_overlap():
    from maps import osm_tiles
    from shapely.geometry import box
    # a building straddling the tile edge appears in both tiles' margins
    left = osm_tiles.decode_buildings(_tile([{"geometry": box(4000, 10, 4150, 60).wkt, "properties": {}}]), 10, 10)[0]
    right = osm_tiles.decode_buildings(_tile([{"geometry": box(-96, 10, 54, 60).wkt, "properties": {}}]), 11, 10)[0]
    unit = osm_tiles.EARTH / (4096 * 2 ** 14)
    overlap = left.intersection(right).area / (50 * unit * unit)
    assert 0 < overlap <= 2 * osm_tiles.OVERLAP + 0.01                 # a sliver, not the whole margin
    assert left.union(right).area == pytest.approx(150 * 50 * unit ** 2, rel=0.02)


def test_tile_range_covers_newcastle_at_zoom_14():
    from maps import osm_tiles
    xs, ys = osm_tiles.tile_range(-1.692, 54.921, -1.534, 55.026)
    assert (len(xs), len(ys)) == (9, 9)
    assert xs.start == 8114 and ys.start == 5180  # standard slippy-map tile numbers


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


def test_shop_recipe_rebuilds_the_design():
    recipe = ('{"v":1,"lat":54.97383,"lon":-1.6132,"name":"Newcastle","title":"Home",'
              '"subtitle":"Where we met","kicker":"","paper":"A3","orient":"landscape",'
              '"width_km":4.5,"theme":"night","source":"osm"}')
    spec = prints.spec_from_recipe(recipe)
    assert (spec.title, spec.subtitle, spec.paper, spec.landscape, spec.width_km, spec.theme, spec.source) == \
        ("Home", "Where we met", "A3", True, 4.5, "night", "osm")


@pytest.mark.parametrize("change", [{"paper": "A0"}, {"width_km": 50}, {"title": ""},
                                    {"title": "x" * 61}, {"v": 2}, {"theme": "neon"}])
def test_bad_recipes_are_refused(change):
    base = {"v": 1, "lat": 54.97, "lon": -1.61, "name": "N", "title": "T", "subtitle": "",
            "kicker": "", "paper": "A3", "orient": "portrait", "width_km": 4, "theme": "paper"}
    with pytest.raises(ValueError):
        prints.spec_from_recipe({**base, **change})
