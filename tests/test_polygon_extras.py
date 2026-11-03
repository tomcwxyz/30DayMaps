"""Day 03 extras: invented geometries only, no network."""
import json
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

from maps import access_land, footprints, land_parcels, watersheds
from maps.arcgis import query_features


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, url, params=None, **kwargs):
        self.calls.append(params)
        return FakeResponse(self.pages.pop(0))


def feature(i, x=-1.6, y=55.0):
    return {"type": "Feature", "properties": {"OBJECTID": i},
            "geometry": {"type": "Polygon", "coordinates": [[[x, y], [x + .01, y], [x + .01, y + .01], [x, y]]]}}


# --- ArcGIS pagination -------------------------------------------------------

def test_arcgis_pages_until_short_page_and_returns_bng():
    session = FakeSession([
        {"features": [feature(1), feature(2)], "properties": {"exceededTransferLimit": True}},
        {"features": [feature(3)]},
    ])
    data = query_features("https://x/FeatureServer/0", page_size=2, session=session)
    assert list(data.OBJECTID) == [1, 2, 3]
    assert data.crs.to_epsg() == 27700
    assert [c["resultOffset"] for c in session.calls] == ["0", "2"]


def test_arcgis_error_is_raised_not_swallowed():
    with pytest.raises(RuntimeError, match="ArcGIS error"):
        query_features("https://x/0", session=FakeSession([{"error": {"code": 400}}]))


# --- Land parcels -------------------------------------------------------------

def test_concentration_counts_parcels_for_half_and_top_shares():
    stats = land_parcels.concentration([50] + [1] * 99)  # one giant, 99 small
    assert stats["parcels"] == 100
    assert stats["parcels_for_half"] == 26  # 50 + 25 small > half of 149
    assert stats["top_1pct_share"] == pytest.approx(50 / 149)
    assert stats["median_ha"] == 1


def test_concentration_rejects_empty_or_zero_areas():
    with pytest.raises(ValueError):
        land_parcels.concentration([1, 0])


def test_bands_follow_rank_not_absolute_size():
    parcels = gpd.GeoDataFrame({"area_ha": np.arange(1, 201)},
                               geometry=[box(i, 0, i + 1, 1) for i in range(200)], crs=27700)
    banded = land_parcels.band_parcels(parcels)
    counts = banded.band.value_counts()
    assert counts["Largest 1% of parcels"] == 2
    assert counts["Next 9%"] == 18
    assert banded.area_ha.iloc[0] == 200


def test_inspire_timestamp_is_read_from_the_dump(tmp_path):
    archive = tmp_path / "x.zip"
    with ZipFile(archive, "w") as z:
        z.writestr("Land_Registry_Cadastral_Parcels.gml",
                   '<wfs:FeatureCollection numberMatched="2" timeStamp="2023-03-05T04:21:10Z">')
    assert land_parcels.gml_timestamp(archive) == "2023-03-05T04:21:10Z"


def test_parcel_map_renders(tmp_path):
    county = box(0, 0, 10_000, 10_000)
    parcels = gpd.GeoDataFrame({"area_ha": [400.0] + [1.0] * 99},
        geometry=[box(0, 0, 2000, 2000)] + [box(3000 + i * 50, 3000, 3000 + i * 50 + 40, 3040) for i in range(99)],
        crs=27700)
    stats = land_parcels.concentration(parcels.area_ha)
    out = land_parcels.draw(land_parcels.band_parcels(parcels), county, stats, 0.06,
                            "2023-03-05", tmp_path / "p.png")
    assert out.stat().st_size > 10_000


# --- Access land -------------------------------------------------------------

def test_dedicated_only_land_is_separated_from_open_country():
    data = gpd.GeoDataFrame({"OC": ["Yes", "No", "No"], "RCL": ["No", "Yes", "No"],
                             "S16": ["Yes", "No", "Yes"]},
                            geometry=[box(0, 0, 1, 1)] * 3, crs=27700)
    assert list(access_land.classify(data).kind) == ["open", "open", "dedicated"]


def test_touching_polygons_become_one_island():
    access = gpd.GeoDataFrame(geometry=[box(0, 0, 100, 100), box(100, 0, 200, 100),
                                        box(1000, 0, 1100, 100)], crs=27700)
    islands = access_land.access_islands(access, box(-10, -10, 2000, 2000))
    assert len(islands) == 2
    assert islands.area_ha.iloc[0] == pytest.approx(2.0)


def test_rasterised_distance_is_straight_line_from_access_land():
    bounds = (0, 0, 10_000, 1_000)
    mask = access_land.rasterise([box(0, 0, 1_000, 1_000)], bounds, 100)
    assert mask.shape == (10, 100)
    assert mask[:, :10].all() and not mask[:, 11:].any()  # edge pixel may fill
    km = access_land.distance_to_access_km(mask, 100)
    assert km[5, 99] == pytest.approx(9.0, abs=0.11)
    assert km[5, 0] == 0


def test_hole_in_polygon_is_not_access_land():
    ring = box(0, 0, 1000, 1000).difference(box(300, 300, 700, 700))
    mask = access_land.rasterise([ring], (0, 0, 1000, 1000), 100)
    assert not mask[5, 5] and mask[0, 0]


# --- Watersheds --------------------------------------------------------------

@pytest.mark.parametrize("rbd,mncat,sea", [
    ("Northumbria", "Tyne", "North Sea"), ("Humber", "Esk and Coast", "North Sea"),
    ("North West", "Lune", "Irish Sea"), ("Solway Tweed", "Till", "North Sea"),
    ("Solway Tweed", "Eden and Esk", "Irish Sea"),
])
def test_catchments_are_assigned_to_their_sea(rbd, mncat, sea):
    assert watersheds.sea_for(rbd, mncat) == sea


def test_unknown_solway_catchment_fails_loudly():
    with pytest.raises(ValueError, match="Unclassified"):
        watersheds.sea_for("Solway Tweed", "Somewhere New")


def test_watershed_is_the_shared_edge_only():
    data = gpd.GeoDataFrame({"WB_ID": ["a", "b"], "RBD_NAME": ["Northumbria", "North West"],
                             "MNCAT_NAME": ["Tyne", "Lune"]},
                            geometry=[box(1000, 0, 2000, 3000), box(0, 0, 1000, 3000)], crs=27700)
    seas = watersheds.dissolve_by(watersheds.classify(data), "sea", (0, 0, 2000, 3000))
    line = watersheds.watershed_line(seas)
    assert line.length == pytest.approx(3000, rel=0.02)
    assert line.bounds[0] == pytest.approx(1000) and line.bounds[2] == pytest.approx(1000)


# --- Footprints --------------------------------------------------------------

def test_building_layer_ignores_important_buildings(tmp_path):
    archive = tmp_path / "oml.zip"
    with ZipFile(archive, "w") as z:
        for n in ["NZ/data/NZ_Building.shp", "NZ/data/NZ_ImportantBuilding.shp"]:
            z.writestr(n, b"")
    assert footprints.building_layer(archive).endswith("!NZ/data/NZ_Building.shp")


def test_windows_are_centred_in_bng():
    minx, miny, maxx, maxy = footprints.window(*footprints.CITY_CENTRE, 1000)
    assert maxx - minx == pytest.approx(1000)
    assert 420_000 < (minx + maxx) / 2 < 430_000
    assert 560_000 < (miny + maxy) / 2 < 570_000


def test_clip_trims_buildings_to_the_frame():
    b = gpd.GeoDataFrame(geometry=[box(-5, 0, 5, 10), box(50, 50, 60, 60)], crs=27700)
    kept = footprints.clip(b, (0, 0, 20, 20))
    assert len(kept) == 1 and kept.area.iloc[0] == pytest.approx(50)
