"""Tests for geospatial truthfulness and the generated Day 8/9 data products."""
import json
from pathlib import Path

import numpy as np
from rasterio.transform import from_origin

from maps.day08_day09 import CLASS_COLOUR, D8, D9, START, END, classify_pct, sample_landcover


def test_landcover_classification_counts_only_valid_source_classes():
    cells = np.array([50, 50, 10, 40, 30, 20, 80, 0, 255] * 20, dtype=np.uint8)
    out = classify_pct(cells)
    assert out["sample_count"] == 140
    assert abs(out["built"] - 100 * 2 / 7) < .01
    assert abs(out["trees"] - 100 / 7) < .01
    assert abs(out["cropland"] - 100 / 7) < .01
    assert abs(sum(out[k] for k in ("built", "trees", "cropland", "open", "other")) - 100) < .1


def test_colour_mapping_is_defined_for_all_worldcover_classes():
    assert set(CLASS_COLOUR) == {0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100}


def test_generated_2050_allocation_is_explicitly_modelled():
    d = json.loads((D8 / "metrics.json").read_text())
    assert d["status"] == "measured_inputs_modelled_future"
    assert d["source_year"] == 2021
    assert 49.7 <= d["2050_nature_first_pct_of_sampled_land"] <= 50.3
    assert d["modelled_added_km2_approx"] > 0
    assert d["named_river_ways"] >= 3
    assert d["former_rail_ways"] >= 3
    assert "NOT a forecast" in d["critical_note"]
    assert (D8 / "today.png").stat().st_size > 10000
    assert (D8 / "2050.png").stat().st_size > 10000


def test_generated_day9_is_measured_and_full_length():
    d = json.loads((D9 / "profile.json").read_text())
    assert d["status"] == "measured"
    assert d["date_of_source"] == 2021
    assert 30 < d["distance_km"] < 50
    assert len(d["samples"]) == 85
    assert d["sample_resolution_m"] == 40
    assert d["radius_m"] == 500
    assert abs(d["samples"][0]["lat"] - START[0]) < .0001
    assert abs(d["samples"][0]["lon"] - START[1]) < .0001
    assert abs(d["samples"][-1]["lat"] - END[0]) < .0001
    assert abs(d["samples"][-1]["lon"] - END[1]) < .0001
    assert (D9 / "transect.png").stat().st_size > 10000
    last = -1.0
    for item in d["samples"]:
        assert item["sample_count"] > 100
        assert item["distance_km"] > last
        last = item["distance_km"]
        assert abs(sum(item[k] for k in ("built", "trees", "cropland", "open", "other")) - 100) < .15


def test_two_dimensional_raster_sampling_preserves_map_geometry():
    """A map grid must stay 2D; rasterio.rowcol itself flattens arrays."""
    codes = np.array([[10, 20], [40, 50]], dtype=np.uint8)
    transform = from_origin(0, 80, 40, 40)
    xs = np.array([[20, 60], [20, 60]], dtype=float)
    ys = np.array([[60, 60], [20, 20]], dtype=float)
    measured = sample_landcover(codes, transform, xs, ys)
    assert measured.shape == (2, 2)
    np.testing.assert_array_equal(measured, codes)
    assert sample_landcover(codes, transform, np.array([20, 60]), np.array([60, 20])).tolist() == [10, 50]
