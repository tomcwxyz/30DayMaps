"""Day 05 Sight — compute a truthful summit panorama from the same DEM.

The result is an angular landscape profile: each half-degree bearing contains
the greatest vertical angle of terrain in four distance bands. Rendering far
bands first and nearer bands over them creates correctly depth-ordered,
terrain-derived silhouettes rather than pretending to be a photograph.

Run after maps.dale_head_viewshed:
    python -m maps.dale_head_panorama --data-dir web/day05-dale-head/data
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import numpy as np
import rasterio

from maps.dale_head_viewshed import (
    CURVATURE_COEFFICIENT, EARTH_RADIUS_M, NODATA
)

STEP_DEG = 0.5
STEP_METRES = 40
BANDS_KM = [(0.04, 2), (2, 5), (5, 10), (10, 20)]


def bilinear_height(dem: np.ndarray, transform, eastings, northings):
    """Interpolate terrain at BNG positions using pixel-centre coordinates."""
    inverse = ~transform
    col, row = inverse * (eastings, northings)
    col = np.asarray(col) - .5
    row = np.asarray(row) - .5
    c0 = np.floor(col).astype(np.int32)
    r0 = np.floor(row).astype(np.int32)
    c1, r1 = c0 + 1, r0 + 1
    if (r0.min() < 0 or c0.min() < 0 or
            r1.max() >= dem.shape[0] or c1.max() >= dem.shape[1]):
        raise ValueError("Panorama ray intersects pixels beyond downloaded DEM")
    fx, fy = col - c0, row - r0
    a, b = dem[r0, c0], dem[r0, c1]
    c, d = dem[r1, c0], dem[r1, c1]
    if any(np.any(~np.isfinite(grid) | (grid == NODATA)) for grid in (a,b,c,d)):
        raise ValueError("Panorama cannot be computed where elevation is missing")
    return ((1 - fx) * (1 - fy) * a + fx * (1 - fy) * b +
            (1 - fx) * fy * c + fx * fy * d)


def angular_profiles(dem: np.ndarray, transform, centre: tuple[float, float],
                     observer_z: float, radius_km: int):
    if radius_km < 5 or radius_km > 30:
        raise ValueError("Use a terrain radius between 5 and 30 km")
    bearings = np.arange(0, 360, STEP_DEG, dtype=np.float64)
    distances = np.arange(STEP_METRES, radius_km * 1000 + 1, STEP_METRES, dtype=np.float64)
    radians = np.deg2rad(bearings)[:, None]
    eastings = centre[0] + np.sin(radians) * distances[None, :]
    northings = centre[1] + np.cos(radians) * distances[None, :]
    heights = bilinear_height(dem, transform, eastings, northings)
    curvature = CURVATURE_COEFFICIENT * distances ** 2 / (2 * EARTH_RADIUS_M)
    angles = np.degrees(np.arctan2(heights - observer_z - curvature[None, :], distances[None, :]))
    profiles = []
    for low_km, high_km in BANDS_KM:
        if low_km > radius_km:
            break
        idx = (distances >= low_km * 1000) & (distances <= min(high_km, radius_km) * 1000)
        if not np.any(idx):
            continue
        candidate = angles[:, idx]
        values = np.max(candidate, axis=1)
        profiles.append({
            "near_km": low_km, "far_km": min(high_km, radius_km),
            "angles_deg": np.round(values, 2).tolist()
        })
    if not profiles:
        raise RuntimeError("No sampled landscape bands")
    skyline = np.max(angles, axis=1)
    farthest = distances[np.argmax(angles, axis=1)]
    return {
        "step_deg": STEP_DEG,
        "samples_per_revolution": len(bearings),
        "max_distance_km": radius_km,
        "bands_near_to_far": profiles,
        "skyline_angles_deg": np.round(skyline, 2).tolist(),
        "horizon_distance_km": np.round(farthest / 1000, 2).tolist(),
        "min_skyline_angle_deg": round(float(np.min(skyline)), 2),
        "max_skyline_angle_deg": round(float(np.max(skyline)), 2)
    }


def build(data_dir: Path) -> dict:
    meta = json.loads((data_dir / "viewshed-manifest.json").read_text())
    observer = meta["observer"]
    if meta["status"] != "computed" or "surveyed_summit_height_m" not in observer:
        raise ValueError("A completed, height-calibrated real viewshed is required")
    radius = int(meta["analysis_radius_km"])
    with rasterio.open(data_dir / "dale-head-dem-bng.tif") as src:
        dem = src.read(1)
        centre = (float(observer["easting"]), float(observer["northing"]))
        z = (float(observer["surveyed_summit_height_m"]) +
             float(observer["eye_height_m_above_surveyed_summit"]))
        profiles = angular_profiles(dem, src.transform, centre, z, radius)
    output = {
        "status": "computed_from_real_dem",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "observer": observer,
        "observer_eye_altitude_m": round(z, 2),
        "terrain_source": meta["terrain_source"],
        "dem_resolution_m": meta["dem_resolution_m"],
        "derived_from": "dale-head-dem-bng.tif",
        "method": "Bilinear elevation sampling along 720 radial sightlines, corrected for earth curvature and standard refraction; distance-banded maximum elevation angles.",
        "curvature_coefficient": CURVATURE_COEFFICIENT,
        "representation": "Analytical horizon silhouettes, not a photorealistic panorama. Colours differentiate distance bands, not terrain cover or measured atmosphere.",
        "profile": profiles
    }
    (data_dir / "panorama.json").write_text(json.dumps(output, separators=(",", ":")) + "\n")
    print(json.dumps({
        "status": output["status"], "radius_km": radius,
        "observer_eye_altitude_m": z,
        "samples_per_revolution": profiles["samples_per_revolution"],
        "skyline_angle_range_deg": [
            profiles["min_skyline_angle_deg"], profiles["max_skyline_angle_deg"]
        ]
    }), flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("web/day05-dale-head/data"))
    args = parser.parse_args()
    build(args.data_dir)


if __name__ == "__main__":
    main()
