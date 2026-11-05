"""Offline tests for the Day 05 real DEM/visibility pipeline."""
from io import BytesIO
import math

import numpy as np
from PIL import Image
import pytest
from rasterio.transform import from_origin
import rasterio

from maps.dale_head_viewshed import (
    NODATA, decode_terrarium, height_at, line_of_sight,
    lonlat_to_tile, tile_range_for_bng_extent, export_overlay,
)


def fixture_dem(size=100, cell_m=10):
    return np.zeros((size, size), dtype=np.float32), from_origin(0, size * cell_m, cell_m, cell_m)


def test_terrarium_decodes_real_rgb_height_encoding():
    # Height = (red * 256 + green + blue / 256) - 32768.
    array = np.zeros((256, 256, 3), dtype=np.uint8)
    array[:, :, :] = (128, 0, 0)      # 0 m
    array[0, 0, :] = (128, 100, 128) # 100.5 m
    array[0, 1, :] = (127, 255, 0)   # -1 m
    png = BytesIO()
    Image.fromarray(array, "RGB").save(png, format="PNG")
    decoded = decode_terrarium(png.getvalue())
    assert decoded.shape == (256, 256)
    assert decoded[5, 5] == 0.0
    assert decoded[0, 0] == pytest.approx(100.5)
    assert decoded[0, 1] == -1


def test_tile_index_from_lon_lat():
    assert lonlat_to_tile(0, 0, 0) == (0, 0)
    assert lonlat_to_tile(0, 0, 1) == (1, 1)
    with pytest.raises(ValueError):
        lonlat_to_tile(0, 90, 12)


def test_dale_head_tile_coverage_is_nonempty():
    from pyproj import Transformer
    e, n = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(
        -3.201936, 54.527271
    )
    x0, y0, x1, y1 = tile_range_for_bng_extent(
        e - 20000, n - 20000, e + 20000, n + 20000, 12
    )
    assert x1 >= x0 and y1 >= y0
    assert (x1 - x0 + 1) * (y1 - y0 + 1) < 160


def test_flat_ground_nearby_is_visible():
    dem, transform = fixture_dem()
    assert line_of_sight(dem, transform, (155, 455), (455, 455))


def test_ridge_blocks_the_view():
    dem, transform = fixture_dem()
    dem[:, 50] = 60
    assert not line_of_sight(dem, transform, (155, 455), (855, 455))


def test_observer_height_can_overcome_very_low_ridge():
    dem, transform = fixture_dem()
    dem[:, 50] = 1.0
    assert line_of_sight(dem, transform, (155, 455), (855, 455), eye_height=30)


def test_missing_elevation_is_an_error():
    dem, transform = fixture_dem()
    dem[50, 50] = NODATA
    with pytest.raises(ValueError):
        height_at(dem, transform, 505, 495)


def test_curvature_hides_distant_flat_ground():
    # Over ~20 km a ground target is beyond the horizon for a 1.7m observer.
    dem, transform = fixture_dem(size=420, cell_m=50)
    assert not line_of_sight(dem, transform, (75, 10075), (20075, 10075))


def test_overlay_preserves_visible_hidden_and_outside(tmp_path):
    raster_path = tmp_path / "test-visibility.tif"
    image_path = tmp_path / "test-overlay.png"
    arr = np.array(
        [[128, 255, 0, 128], [128, 255, 0, 128], [128, 255, 0, 128]],
        dtype=np.uint8
    )
    with rasterio.open(
        raster_path, "w", driver="GTiff", width=4, height=3,
        count=1, dtype="uint8", crs="EPSG:27700",
        transform=from_origin(350000, 530000, 100, 100), nodata=128
    ) as output:
        output.write(arr, 1)
    corners, counts, area = export_overlay(raster_path, image_path)
    assert counts == {"visible": 3, "hidden": 3, "outside_or_nodata": 6}
    assert area == pytest.approx(.03)
    assert len(corners) == 4
    assert image_path.exists()
    with Image.open(image_path) as img:
        assert img.mode == "RGBA"
        assert np.asarray(img)[:, :, 3].max() > 0
