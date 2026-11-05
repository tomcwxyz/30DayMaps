"""Offline tests for the real-DEM panoramic skyline computation."""
import numpy as np
import pytest
from rasterio.transform import from_origin
from maps.dale_head_panorama import angular_profiles, bilinear_height


def test_bilinear_height_uses_pixel_centres():
    dem = np.array([[0, 10], [20, 30]], dtype=np.float32)
    transform = from_origin(0, 2, 1, 1)
    z = bilinear_height(dem, transform, np.array([[1.0]]), np.array([[1.0]]))
    assert z[0, 0] == pytest.approx(15)


def test_360_degree_panorama_is_real_elevation_profile():
    dem = np.full((400, 400), 750.0, dtype=np.float32)
    transform = from_origin(0, 16_000, 40, 40)
    # Terrain north of the centre rises to a high ridge.
    dem[72:78, 185:215] = 900
    result = angular_profiles(dem, transform, (8_000, 8_000), 754.7, 5)
    assert result["samples_per_revolution"] == 720
    assert len(result["skyline_angles_deg"]) == 720
    assert len(result["horizon_distance_km"]) == 720
    assert all(len(b["angles_deg"]) == 720 for b in result["bands_near_to_far"])
    assert result["skyline_angles_deg"][0] > result["skyline_angles_deg"][360]
    assert result["max_skyline_angle_deg"] < 90
    assert result["min_skyline_angle_deg"] > -90


def test_bad_radius_and_missing_data_are_rejected():
    dem = np.full((400, 400), 750.0, dtype=np.float32)
    transform = from_origin(0, 16_000, 40, 40)
    with pytest.raises(ValueError):
        angular_profiles(dem, transform, (8_000, 8_000), 754.7, 2)
    dem[200, 200] = -9999.0
    with pytest.raises(ValueError):
        angular_profiles(dem, transform, (8_000, 8_000), 754.7, 5)
