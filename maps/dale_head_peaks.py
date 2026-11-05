"""Attach source-verified summit names and modelled visibility to Dale Head.

Use:
    python -m maps.dale_head_peaks --data-dir web/day05-dale-head/data

Requires a completed and validated real terrain viewshed. Candidate names and
coordinates come from OpenStreetMap natural=peak nodes via Overpass. For each
candidate, GDAL's computed terrain cell is compared to an independent
line-of-sight ray. A disagreement becomes "uncertain", never "visible".

No fallback/fabricated summits are ever supplied if Overpass is unavailable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from pyproj import Geod, Transformer
import rasterio
import requests

from maps.dale_head_viewshed import (
    SUMMIT_LON, SUMMIT_LAT, EYE_HEIGHT_M, line_of_sight, NODATA
)

SOURCE_ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
GEOD = Geod(ellps="WGS84")
QUERY_RADIUS_M = 20_000
MIN_DISTANCE_M = 600
MIN_ELEVATION_M = 440
MAX_LABELS = 22
SUMMIT_POINT = (SUMMIT_LON, SUMMIT_LAT)


def overpass_query(radius_m: int) -> str:
    return (
        '[out:json][timeout:40];'
        f'node(around:{radius_m},{SUMMIT_LAT},{SUMMIT_LON})'
        '["natural"="peak"]["name"];out body;'
    )


def fetch_peak_nodes(session: requests.Session, radius_m: int) -> tuple[list[dict], str]:
    problems = []
    query = overpass_query(radius_m)
    for endpoint in SOURCE_ENDPOINTS:
        try:
            response = session.post(
                endpoint, data={"data": query}, timeout=65,
                headers={"User-Agent": "30DayMaps/1.0 (public mapping experiment; source attribution in repo)"}
            )
            response.raise_for_status()
            payload = response.json()
            elements = payload.get("elements")
            if not isinstance(elements, list):
                raise ValueError("Overpass returned no elements array")
            return elements, endpoint
        except (requests.RequestException, ValueError) as exc:
            problems.append(f"{endpoint}: {type(exc).__name__}: {str(exc)[:160]}")
    raise RuntimeError("Unable to retrieve peak names from OpenStreetMap: " + " | ".join(problems))


def parse_height(value: object) -> float | None:
    """Read an OSM height in metres; don't guess on non-metric/compound values."""
    if value is None:
        return None
    match = re.fullmatch(r"\s*(\d{1,4}(?:\.\d+)?)\s*(?:m|metres|meters)?\s*", str(value))
    if not match:
        return None
    height = float(match.group(1))
    return height if 0 < height < 2000 else None


def source_candidates(elements: list[dict], radius_m: int) -> list[dict]:
    nodes = []
    seen = set()
    for item in elements:
        if item.get("type") != "node" or not isinstance(item.get("id"), int):
            continue
        tags = item.get("tags") or {}
        name = str(tags.get("name") or "").strip()
        if not (1 <= len(name) <= 65) or not (-8 <= item.get("lon", 1000) <= 3) or not (49 <= item.get("lat", 1000) <= 61):
            continue
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        longitude, latitude = float(item["lon"]), float(item["lat"])
        bearing, _, distance_m = GEOD.inv(SUMMIT_LON, SUMMIT_LAT, longitude, latitude)
        if distance_m < MIN_DISTANCE_M or distance_m >= radius_m - 60:
            continue
        nodes.append({
            "name": name, "longitude": longitude, "latitude": latitude,
            "distance_km": round(distance_m / 1000, 2),
            "bearing_deg": round(bearing % 360, 1),
            "osm_height_m": parse_height(tags.get("ele")),
            "osm_node_id": item["id"],
            "source_url": f"https://www.openstreetmap.org/node/{item['id']}",
        })
    return nodes


def classify_candidates(candidates: list[dict], dem_file: Path, viewshed_file: Path,
                        observer: tuple[float, float]) -> list[dict]:
    projector = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    records = []
    with rasterio.open(dem_file) as dem_src, rasterio.open(viewshed_file) as view_src:
        dem = dem_src.read(1)
        visibility = view_src.read(1)
        for row in candidates:
            e, n = projector.transform(row["longitude"], row["latitude"])
            try:
                dem_row, dem_col = rasterio.transform.rowcol(dem_src.transform, e, n)
                view_row, view_col = rasterio.transform.rowcol(view_src.transform, e, n)
                if not (0 <= dem_row < dem.shape[0] and 0 <= dem_col < dem.shape[1]
                        and 0 <= view_row < visibility.shape[0] and 0 <= view_col < visibility.shape[1]):
                    continue
                height = float(dem[dem_row, dem_col])
                if not math.isfinite(height) or height == NODATA:
                    continue
                source_height = row["osm_height_m"]
                if (source_height is not None and source_height < MIN_ELEVATION_M and height < MIN_ELEVATION_M):
                    continue
                if source_height is None and height < MIN_ELEVATION_M:
                    continue
                classification = int(visibility[view_row, view_col])
                if classification not in (0, 255):
                    continue
                ray_visible = line_of_sight(
                    dem, dem_src.transform, observer, (e, n), eye_height=EYE_HEIGHT_M
                )
                visible_by_gdal = classification == 255
                status = ("uncertain" if ray_visible != visible_by_gdal
                          else "visible" if visible_by_gdal else "hidden")
                records.append({
                    **row, "dem_height_m": round(height, 1),
                    "visibility": status, "gdal_visible": visible_by_gdal,
                    "independent_ray_visible": ray_visible
                })
            except (ValueError, IndexError):
                continue
    return records


def pick_labels(peaks: list[dict], max_labels: int = MAX_LABELS,
                min_angle_deg: float = 5.5) -> list[dict]:
    """Choose recognisable, well-spaced hills for uncluttered cartography.

    Visibility is a prerequisite. Preference is for higher and reasonably
    close hills, balanced by angular separation across the horizon.
    """
    visible = [p for p in peaks if p["visibility"] == "visible"]
    visible.sort(key=lambda p: (
        -(p["osm_height_m"] or p["dem_height_m"]) + 8 * p["distance_km"],
        p["distance_km"], p["name"].lower()
    ))
    chosen = []
    seen_names = set()
    for peak in visible:
        name_key = peak["name"].casefold()
        if name_key in seen_names:
            continue
        if any(min(abs(peak["bearing_deg"] - p["bearing_deg"]),
                   360 - abs(peak["bearing_deg"] - p["bearing_deg"])) < min_angle_deg
               for p in chosen):
            continue
        chosen.append(peak)
        seen_names.add(name_key)
        if len(chosen) >= max_labels:
            break
    return sorted(chosen, key=lambda p: (p["bearing_deg"], p["distance_km"]))


def build(data_dir: Path, radius_m: int = QUERY_RADIUS_M) -> dict:
    manifest_file = data_dir / "viewshed-manifest.json"
    manifest = json.loads(manifest_file.read_text())
    if manifest.get("status") != "computed" or not (data_dir / "dale-head-viewshed-bng.tif").exists():
        raise RuntimeError("Run maps.dale_head_viewshed first; this tool never infers an uncomputed view")
    if radius_m > float(manifest["analysis_radius_km"]) * 1000:
        raise ValueError("Summit search radius must not exceed the computed viewshed")
    observer_meta = manifest["observer"]
    centre = (float(observer_meta["easting"]), float(observer_meta["northing"]))
    with requests.Session() as session:
        elements, endpoint = fetch_peak_nodes(session, radius_m)
    source = source_candidates(elements, radius_m)
    classified = classify_candidates(
        source, data_dir / "dale-head-dem-bng.tif",
        data_dir / "dale-head-viewshed-bng.tif", centre
    )
    labelled = pick_labels(classified)
    output = {
        "status": "computed_from_real_data",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "viewpoint": {"latitude": SUMMIT_LAT, "longitude": SUMMIT_LON},
        "source": "OpenStreetMap mapped summit nodes (natural=peak, name)",
        "source_licence": "Open Database Licence (ODbL), © OpenStreetMap contributors",
        "source_reference": "https://www.openstreetmap.org/copyright",
        "source_query": overpass_query(radius_m),
        "source_endpoint": endpoint,
        "raw_source_nodes": len(elements),
        "candidate_nodes": len(source),
        "modelled_peaks": len(classified),
        "visible_count": sum(p["visibility"] == "visible" for p in classified),
        "hidden_count": sum(p["visibility"] == "hidden" for p in classified),
        "uncertain_count": sum(p["visibility"] == "uncertain" for p in classified),
        "selected_label_count": len(labelled),
        "labelled_peaks": labelled,
        "method": "GDAL terrain viewshed at mapped summit point, independently checked with sampled terrain ray",
        "caveat": "A mapped summit point is an approximation, and a 40 m DEM cannot show every small ridge. This is modelled bare-ground visibility, not independently observed panorama. Disagreements are excluded from visible labels.",
    }
    outfile = data_dir / "peaks.json"
    outfile.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: output[key] for key in
                      ("raw_source_nodes", "candidate_nodes", "modelled_peaks",
                       "visible_count", "hidden_count", "uncertain_count",
                       "selected_label_count")}, indent=2), flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("web/day05-dale-head/data"))
    parser.add_argument("--radius-km", type=int, default=20)
    args = parser.parse_args()
    if not 3 <= args.radius_km <= 30:
        parser.error("Use a summit query radius of 3–30 km")
    build(args.data_dir, args.radius_km * 1000)


if __name__ == "__main__":
    main()
