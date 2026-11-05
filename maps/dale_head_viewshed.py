"""Day 05 / Sight: reproducible *real* Dale Head terrain viewshed.

Builds a projected, metre-based DEM from Mapzen/Tilezen Terrarium tiles and
runs the published GDAL viewshed algorithm. It does not synthesise terrain.
Requires: pip install numpy Pillow rasterio requests pyproj ; gdal_viewshed CLI.

    python -m maps.dale_head_viewshed --output web/day05-dale-head/data

The output PNG is reprojected to EPSG:4326 for a map image overlay. The
original projected DEM/visibility GeoTIFFs are retained for inspection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine, array_bounds, from_origin
from rasterio.warp import calculate_default_transform, reproject
import requests

SUMMIT_LON, SUMMIT_LAT = -3.201936, 54.527271
DEFAULT_RADIUS_M = 20_000
EYE_HEIGHT_M = 1.7
TARGET_HEIGHT_M = 0.0
CURVATURE_COEFFICIENT = 6.0 / 7.0  # standard optical approximation
EARTH_RADIUS_M = 6_371_008.8
WEB_MERCATOR_HALF_M = 20_037_508.342789244
NODATA = -9999.0
TILE_SIZE = 256
TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
SOURCE = "Mapzen / Tilezen Terrain Tiles (AWS Open Data)"
BNG = "EPSG:27700"


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    if not (-180 <= lon <= 180 and -85.0511 < lat < 85.0511):
        raise ValueError("Coordinates outside Web Mercator coverage")
    n = 2 ** zoom
    x = min(n - 1, max(0, math.floor((lon + 180) / 360 * n)))
    y = min(n - 1, max(0, math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) * n / 2)))
    return x, y


def tile_range_for_bng_extent(
    west: float, south: float, east: float, north: float, zoom: int
) -> tuple[int, int, int, int]:
    inverse = Transformer.from_crs(BNG, "EPSG:4326", always_xy=True)
    # Include edge midpoints as a precaution against nonlinear projection edges.
    points = [
        (west, south), (west, north), (east, south), (east, north),
        ((west + east) / 2, south), ((west + east) / 2, north),
        (west, (south + north) / 2), (east, (south + north) / 2)
    ]
    tile_points = [lonlat_to_tile(*inverse.transform(e, n), zoom) for e, n in points]
    return (
        min(p[0] for p in tile_points), min(p[1] for p in tile_points),
        max(p[0] for p in tile_points), max(p[1] for p in tile_points)
    )


def decode_terrarium(tile: bytes) -> np.ndarray:
    image = Image.open(BytesIO(tile)).convert("RGB")
    if image.size != (TILE_SIZE, TILE_SIZE):
        raise ValueError(f"Unexpected Terrarium tile size {image.size}")
    rgb = np.asarray(image, dtype=np.float32)
    return rgb[:, :, 0] * 256 + rgb[:, :, 1] + rgb[:, :, 2] / 256 - 32768


def download_mosaic(
    zoom: int, bounds: tuple[float, float, float, float]
) -> tuple[np.ndarray, Affine, list[str]]:
    x0, y0, x1, y1 = tile_range_for_bng_extent(*bounds, zoom)
    width, height = (x1 - x0 + 1) * TILE_SIZE, (y1 - y0 + 1) * TILE_SIZE
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 160:
        raise ValueError("Too many elevation tiles; reduce radius or source zoom")
    mosaic = np.empty((height, width), dtype=np.float32)
    urls = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "30DayMaps-DaleHeadViewshed/1.0 (open educational mapping experiment)"})
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                url = TERRARIUM.format(z=zoom, x=x, y=y)
                response = session.get(url, timeout=35)
                response.raise_for_status()
                r0, c0 = (y - y0) * TILE_SIZE, (x - x0) * TILE_SIZE
                mosaic[r0:r0 + TILE_SIZE, c0:c0 + TILE_SIZE] = decode_terrarium(response.content)
                urls.append(url)
    metres_per_pixel = 2 * WEB_MERCATOR_HALF_M / (TILE_SIZE * 2 ** zoom)
    transform = Affine(
        metres_per_pixel, 0, -WEB_MERCATOR_HALF_M + x0 * TILE_SIZE * metres_per_pixel,
        0, -metres_per_pixel, WEB_MERCATOR_HALF_M - y0 * TILE_SIZE * metres_per_pixel
    )
    return mosaic, transform, urls


def build_projected_dem(
    summit_e: float, summit_n: float, radius_m: int,
    resolution_m: int, zoom: int, output_file: Path
) -> tuple[np.ndarray, Affine, list[str]]:
    padding = max(1000, resolution_m * 8)
    half = radius_m + padding
    size = math.ceil(2 * half / resolution_m)
    left, top = summit_e - half, summit_n + half
    transform = from_origin(left, top, resolution_m, resolution_m)
    src, src_transform, tile_urls = download_mosaic(
        zoom, (left, top - size * resolution_m, left + size * resolution_m, top)
    )
    dem = np.full((size, size), NODATA, dtype=np.float32)
    reproject(
        source=src, destination=dem,
        src_transform=src_transform, src_crs="EPSG:3857",
        dst_transform=transform, dst_crs=BNG,
        dst_nodata=NODATA, resampling=Resampling.bilinear
    )
    rows, cols = np.indices(dem.shape, dtype=np.float32)
    eastings = left + (cols + .5) * resolution_m
    northings = top - (rows + .5) * resolution_m
    inside = (eastings - summit_e) ** 2 + (northings - summit_n) ** 2 <= radius_m ** 2
    if np.any(inside & ((dem == NODATA) | (~np.isfinite(dem)))):
        raise RuntimeError("Elevation tiles are incomplete inside the requested analysis radius")
    with rasterio.open(
        output_file, "w", driver="GTiff", height=size, width=size,
        count=1, dtype="float32", crs=BNG, transform=transform,
        nodata=NODATA, compress="deflate", predictor=3
    ) as out:
        out.write(dem, 1)
    return dem, transform, tile_urls


def height_at(dem: np.ndarray, transform: Affine, e: float, n: float) -> float:
    col, row = (~transform) * (e, n)
    r, c = int(math.floor(row)), int(math.floor(col))
    if not (0 <= r < dem.shape[0] and 0 <= c < dem.shape[1]):
        raise ValueError("Sightline outside DEM")
    height = float(dem[r, c])
    if not math.isfinite(height) or height == NODATA:
        raise ValueError("Sightline intersects missing DEM data")
    return height


def line_of_sight(
    dem: np.ndarray, transform: Affine,
    origin: tuple[float, float], target: tuple[float, float],
    eye_height: float = EYE_HEIGHT_M, target_height: float = TARGET_HEIGHT_M,
    curvature: float = CURVATURE_COEFFICIENT
) -> bool:
    """Independent nearest-cell ray check for diagnostics and synthetic tests.

    The final full viewshed is GDAL's published implementation, not this
    slower point-to-point validator.
    """
    ox, oy = origin
    tx, ty = target
    distance = math.hypot(tx - ox, ty - oy)
    if distance == 0:
        return True
    z0 = height_at(dem, transform, ox, oy) + eye_height
    z1 = height_at(dem, transform, tx, ty) + target_height
    z1 -= curvature * distance ** 2 / (2 * EARTH_RADIUS_M)
    resolution = min(abs(transform.a), abs(transform.e))
    steps = max(2, math.ceil(distance / (resolution / 2)))
    for step in range(1, steps):
        frac = step / steps
        x, y = ox + frac * (tx - ox), oy + frac * (ty - oy)
        d = frac * distance
        ground = height_at(dem, transform, x, y)
        ground -= curvature * d ** 2 / (2 * EARTH_RADIUS_M)
        sightline = z0 + (z1 - z0) * frac
        if ground > sightline:
            return False
    return True


def run_gdal_viewshed(input_file: Path, output_file: Path,
                      observer_e: float, observer_n: float, radius_m: int) -> None:
    args = [
        "gdal_viewshed", "-of", "GTiff", "-ox", str(observer_e), "-oy", str(observer_n),
        "-oz", str(EYE_HEIGHT_M), "-tz", str(TARGET_HEIGHT_M),
        "-md", str(radius_m), "-cc", str(CURVATURE_COEFFICIENT),
        "-vv", "255", "-iv", "0", "-ov", "128", "-a_nodata", "128",
        "-co", "COMPRESS=DEFLATE", str(input_file), str(output_file)
    ]
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, timeout=240)
    except FileNotFoundError as exc:
        raise RuntimeError("gdal_viewshed executable missing; install gdal-bin") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"GDAL viewshed failed: {exc.stderr}") from exc


def export_overlay(
    visibility_file: Path, png_file: Path
) -> tuple[list[list[float]], dict[str, int], float]:
    with rasterio.open(visibility_file) as source:
        visibility = source.read(1)
        mask_visible = visibility == 255
        mask_hidden = visibility == 0
        if mask_visible.sum() == 0:
            raise RuntimeError("Viewshed has no visible cells; check the observer")
        rgba = np.zeros((4, source.height, source.width), dtype=np.uint8)
        # Visible land in green; hidden land in dark translucent slate.
        rgba[:, mask_visible] = np.array([43, 138, 99, 170], dtype=np.uint8)[:, None]
        rgba[:, mask_hidden] = np.array([44, 60, 59, 76], dtype=np.uint8)[:, None]
        transform, width, height = calculate_default_transform(
            source.crs, "EPSG:4326", source.width, source.height, *source.bounds
        )
        transformed = np.zeros((4, height, width), dtype=np.uint8)
        for band in range(4):
            reproject(
                source=rgba[band], destination=transformed[band],
                src_transform=source.transform, src_crs=source.crs,
                dst_transform=transform, dst_crs="EPSG:4326",
                resampling=Resampling.nearest
            )
        Image.fromarray(np.moveaxis(transformed, 0, -1), "RGBA").save(png_file, optimize=True)
        left, bottom, right, top = array_bounds(height, width, transform)
        corners = [[left, top], [right, top], [right, bottom], [left, bottom]]
        counts = {
            "visible": int(mask_visible.sum()),
            "hidden": int(mask_hidden.sum()),
            "outside_or_nodata": int(visibility.size - mask_visible.sum() - mask_hidden.sum())
        }
        # A metre-based local projected grid gives an approximate planar area.
        sq_km = counts["visible"] * abs(source.transform.a * source.transform.e) / 1_000_000
        return corners, counts, round(sq_km, 2)


def validate_rays(
    dem: np.ndarray, transform: Affine, visibility_file: Path,
    centre: tuple[float, float]
) -> dict:
    agreement = 0
    checked = 0
    disagreements = []
    with rasterio.open(visibility_file) as src:
        result = src.read(1)
        for bearing in range(0, 360, 30):
            angle = math.radians(bearing)
            for distance in [2_000, 5_000, 9_000, 14_000, 18_000]:
                x = centre[0] + math.sin(angle) * distance
                y = centre[1] + math.cos(angle) * distance
                row, col = rasterio.transform.rowcol(src.transform, x, y)
                if not (0 <= row < result.shape[0] and 0 <= col < result.shape[1]):
                    continue
                if result[row, col] not in (0, 255):
                    continue
                try:
                    verdict = line_of_sight(dem, transform, centre, (x, y))
                except ValueError:
                    continue
                checked += 1
                gdal_visible = result[row, col] == 255
                agreement += int(verdict == gdal_visible)
                if verdict != gdal_visible:
                    disagreements.append({
                        "grid_bearing_deg": bearing,
                        "distance_m": distance,
                        "target_easting": round(x, 2),
                        "target_northing": round(y, 2),
                        "gdal_visible": bool(gdal_visible),
                        "nearest_cell_ray_visible": bool(verdict),
                        "interpretation": "Algorithms sample pixels differently; inspect the terrain profile before asserting physical visibility."
                    })
    return {"checked": checked, "agreement": agreement,
            "agreement_fraction": round(agreement / checked, 3) if checked else None,
            "disagreements": disagreements}


def build(output: Path, radius_km: int, resolution_m: int, tile_zoom: int) -> dict:
    if not (5 <= radius_km <= 30 and 15 <= resolution_m <= 100 and 10 <= tile_zoom <= 13):
        raise ValueError("Use radius 5–30 km, resolution 15–100 m, tile zoom 10–13")
    output.mkdir(parents=True, exist_ok=True)
    centre = Transformer.from_crs("EPSG:4326", BNG, always_xy=True).transform(
        SUMMIT_LON, SUMMIT_LAT
    )
    radius_m = radius_km * 1000
    dem_file = output / "dale-head-dem-bng.tif"
    viewshed_file = output / "dale-head-viewshed-bng.tif"
    png_file = output / "viewshed-overlay.png"
    print("Downloading real elevation tiles and projecting DEM...", flush=True)
    dem, transform, tile_urls = build_projected_dem(
        *centre, radius_m, resolution_m, tile_zoom, dem_file
    )
    print("Calculating GDAL terrain viewshed...", flush=True)
    run_gdal_viewshed(dem_file, viewshed_file, *centre, radius_m)
    corners, counts, area = export_overlay(viewshed_file, png_file)
    validation = validate_rays(dem, transform, viewshed_file, centre)
    manifest = {
        "status": "computed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "observer": {
            "name": "Dale Head summit (approximate viewpoint)",
            "longitude": SUMMIT_LON, "latitude": SUMMIT_LAT,
            "easting": round(centre[0], 2), "northing": round(centre[1], 2),
            "eye_height_m_above_terrain": EYE_HEIGHT_M
        },
        "target_height_m_above_terrain": TARGET_HEIGHT_M,
        "analysis_radius_km": radius_km,
        "dem_resolution_m": resolution_m,
        "dem_crs": BNG,
        "algorithm": "GDAL gdal_viewshed",
        "curvature_coefficient": CURVATURE_COEFFICIENT,
        "optical_refraction_approximation": "standard 1/7 coefficient; not a meteorological forecast",
        "terrain_source": SOURCE,
        "terrain_source_url": "https://registry.opendata.aws/terrain-tiles/",
        "terrain_attribution": "https://github.com/tilezen/joerd/blob/master/docs/attribution.md",
        "terrarium_zoom": tile_zoom,
        "source_tile_urls": tile_urls,
        "overlay_png": "viewshed-overlay.png",
        "image_corners_lonlat": corners,
        "cell_counts": counts,
        "approx_visible_ground_area_km2": area,
        "independent_ray_diagnostic": validation,
        "interpretation": [
            "Ground-surface visibility from a single human-height observer.",
            "Bare-earth terrain only: trees, buildings, walls and weather are not included.",
            "Pixel-scale terrain visibility is not a guarantee of a recognisable real-world view.",
            "The source DEM is converted from Web Mercator terrain tiles into British National Grid metres.",
            "Output visibility is based on a finite-resolution DEM and standard optical refraction."
        ]
    }
    (output / "viewshed-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Viewshed result:", json.dumps({
        "visible_km2": area, "counts": counts, "tiles": len(tile_urls),
        "independent_rays": validation
    }), flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="web/day05-dale-head/data", type=Path)
    parser.add_argument("--radius-km", type=int, default=20)
    parser.add_argument("--resolution-m", type=int, default=40)
    parser.add_argument("--tile-zoom", type=int, default=12)
    args = parser.parse_args()
    build(args.output, args.radius_km, args.resolution_m, args.tile_zoom)


if __name__ == "__main__":
    main()
