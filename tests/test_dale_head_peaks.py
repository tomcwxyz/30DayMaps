"""Offline tests for OSM peak names and visibility-checked summit labels."""
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from maps.dale_head_peaks import (
    source_candidates, parse_height, pick_labels, classify_candidates,
    MIN_DISTANCE_M, SUMMIT_LON, SUMMIT_LAT
)


def test_osm_heights_only_accept_unambiguous_metres():
    assert parse_height("753") == 753
    assert parse_height(" 839.2 m ") == pytest.approx(839.2)
    assert parse_height("753 ft") is None
    assert parse_height("-50") is None
    assert parse_height("100;150") is None
    assert parse_height("unknown") is None


def test_candidate_filter_excludes_unnamed_and_summit_itself():
    source = [
        {"type": "node", "id": 1, "lat": SUMMIT_LAT, "lon": SUMMIT_LON,
         "tags": {"name": "Dale Head", "natural": "peak", "ele": "753"}},
        {"type": "node", "id": 2, "lat": SUMMIT_LAT + .030, "lon": SUMMIT_LON,
         "tags": {"name": "Nearby fell", "natural": "peak", "ele": "800"}},
        {"type": "node", "id": 3, "lat": SUMMIT_LAT + .025, "lon": SUMMIT_LON,
         "tags": {"natural": "peak", "ele": "800"}},
    ]
    data = source_candidates(source, 20_000)
    assert [p["osm_node_id"] for p in data] == [2]
    assert data[0]["distance_km"] > MIN_DISTANCE_M / 1000


def test_peak_labels_exclude_uncertain_and_hidden_and_avoid_direction_duplicates():
    peaks = [
        dict(name="A", visibility="visible", bearing_deg=30, distance_km=2,
             osm_height_m=950, dem_height_m=947),
        dict(name="B", visibility="visible", bearing_deg=31, distance_km=3,
             osm_height_m=900, dem_height_m=905),
        dict(name="C", visibility="hidden", bearing_deg=70, distance_km=4,
             osm_height_m=980, dem_height_m=980),
        dict(name="D", visibility="uncertain", bearing_deg=100, distance_km=7,
             osm_height_m=975, dem_height_m=970),
        dict(name="E", visibility="visible", bearing_deg=150, distance_km=12,
             osm_height_m=None, dem_height_m=840),
    ]
    chosen = pick_labels(peaks)
    assert {p["name"] for p in chosen} == {"A", "E"}
    assert [p["bearing_deg"] for p in chosen] == sorted(p["bearing_deg"] for p in chosen)


def test_classification_uses_same_viewshed_and_independent_ray(tmp_path):
    # Flat 1 km synthetic DEM, observer above the middle at eye height.
    size, cell = 100, 10
    e, n = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(
        SUMMIT_LON, SUMMIT_LAT
    )
    left, top = e - 500, n + 500
    transform = from_origin(left, top, cell, cell)
    dem = np.full((size, size), 750.0, dtype=np.float32)
    vis = np.full((size, size), 255, dtype=np.uint8)
    vis[:, 79] = 0    # Model GDAL hidden east of the observer
    dem_path, view_path = tmp_path / "dem.tif", tmp_path / "visibility.tif"
    for path, array, nodata in [(dem_path, dem, -9999), (view_path, vis, 128)]:
        with rasterio.open(
            path, "w", driver="GTiff", width=size, height=size,
            count=1, dtype=array.dtype, crs="EPSG:27700",
            transform=transform, nodata=nodata
        ) as output:
            output.write(array, 1)
    lon, lat = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True).transform(
        e + 180, n
    )
    candidates = [{
        "name": "Fixture Peak", "latitude": lat, "longitude": lon,
        "osm_height_m": 800, "bearing_deg": 90, "distance_km": .18,
        "source_url": "https://www.openstreetmap.org/node/1", "osm_node_id": 1
    }]
    result = classify_candidates(candidates, dem_path, view_path, (e, n))
    assert result[0]["visibility"] == "visible"
    assert result[0]["gdal_visible"] is True
    assert result[0]["independent_ray_visible"] is True
    # A disagreement is explicitly uncertain, never promoted to visible.
    rr, cc = rasterio.transform.rowcol(transform, e + 180, n)
    vis[rr, cc] = 0
    with rasterio.open(view_path, "r+") as dest:
        dest.write(vis, 1)
    result = classify_candidates(candidates, dem_path, view_path, (e, n))
    assert result[0]["visibility"] == "uncertain"
