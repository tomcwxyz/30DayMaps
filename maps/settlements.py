"""England's bus stops furthest from a *defined built-up area*.

This is one distinct measure of remoteness, not an assertion that no nearby
houses, hamlets, residents or transport services exist. ONS 2022 built-up areas
are generalised polygons and explicitly omit some small settlements.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.strtree import STRtree

from maps.buses import clean_stops, group_stop_locations
from maps.common import NAPTAN_CSV, download, regions
from maps.render import draw_bus_map

ONS_BUILT_UP = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "BUA_2022_GB/FeatureServer/0/query"
)


def load_built_up_areas(cache: Path, *, force: bool = False, chunk_size: int = 300) -> gpd.GeoDataFrame:
    """Query ONS's source by OBJECTID, avoiding ArcGIS's 1000-record pagination cap.

    Cache GeoJSON locally; do not commit bulk source data to the repo.
    """
    cache = Path(cache)
    if cache.exists() and not force:
        areas = gpd.read_file(cache)
    else:
        session = requests.Session()
        session.headers.update({"User-Agent": "30DayMaps/0.2 (open data research)"})
        response = session.get(ONS_BUILT_UP, params={"where": "1=1", "returnIdsOnly": "true", "f": "json"}, timeout=(15, 120))
        response.raise_for_status()
        index = response.json()
        ids = sorted(index.get("objectIds") or [])
        if "error" in index or not ids:
            raise RuntimeError(f"ONS BUA query returned no object IDs: {str(index)[:250]}")
        def get_batch(batch: list[int]) -> list[dict]:
            """Use POST to avoid giant URLs, bisecting batches rejected upstream."""
            params = {
                "objectIds": ",".join(map(str, batch)), "outFields": "BUA22CD,BUA22NM",
                "returnGeometry": "true", "outSR": "4326", "f": "geojson",
            }
            errors = []
            for method in ("post", "get"):
                try:
                    if method == "post":
                        result = session.post(ONS_BUILT_UP, data=params, timeout=(15, 150))
                    else:
                        result = session.get(ONS_BUILT_UP, params=params, timeout=(15, 150))
                    result.raise_for_status()
                    payload = result.json()
                    if "error" in payload:
                        raise RuntimeError(str(payload["error"]))
                    features = payload.get("features") or []
                    if len(features) != len(batch):
                        raise RuntimeError(f"Incomplete ONS batch: {len(features)} of {len(batch)}")
                    return features
                except (requests.RequestException, ValueError, RuntimeError) as error:
                    errors.append(f"{method}: {error}")
            if len(batch) == 1:
                raise RuntimeError(f"ONS BUA request failed for OBJECTID {batch[0]}: {'; '.join(errors)}")
            middle = len(batch) // 2
            return get_batch(batch[:middle]) + get_batch(batch[middle:])

        features = []
        for start in range(0, len(ids), chunk_size):
            batch = ids[start:start + chunk_size]
            features.extend(get_batch(batch))
            if (start // chunk_size + 1) % 10 == 0:
                print(f"Retrieved {len(features):,}/{len(ids):,} built-up area polygons", flush=True)
        areas = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        if not {"BUA22CD", "BUA22NM"}.issubset(areas.columns):
            raise ValueError("ONS BUA code/name fields are missing")
        areas = areas[["BUA22CD", "BUA22NM", "geometry"]].to_crs("EPSG:27700")
        if areas.geometry.is_empty.any() or areas.geometry.isna().any():
            raise ValueError("ONS BUA returned empty geometries")
        cache.parent.mkdir(parents=True, exist_ok=True)
        areas.to_file(cache, driver="GeoJSON")
    if areas.crs is None:
        raise ValueError("Built-up area source must include a coordinate reference system")
    areas = areas.to_crs("EPSG:27700")
    if areas.empty:
        raise ValueError("No built-up areas available")
    return areas


def rank_far_from_built_up(stops: pd.DataFrame, areas: gpd.GeoDataFrame, *, england_geometry=None,
                           top_n: int = 100, pair_radius_m: float = 75) -> pd.DataFrame:
    """Rank English stop locations by the distance of their nearest platform to any GB BUA edge.

    A platform within a built-up polygon is distance zero. Geographical grouping
    is the same as maps.buses, and the nearest boundary may be in Wales/Scotland.
    """
    if stops.empty or areas.empty:
        raise ValueError("Stops and built-up areas must not be empty")
    if areas.crs is None or areas.crs.to_epsg() != 27700:
        areas = areas.to_crs("EPSG:27700")
    grouped = group_stop_locations(stops, pair_radius_m=pair_radius_m)
    points = gpd.points_from_xy(grouped.Easting, grouped.Northing)
    geometries = areas.geometry.to_numpy()
    tree = STRtree(geometries)
    pairs, distances = tree.query_nearest(np.asarray(points, dtype=object),
                                         return_distance=True, all_matches=False)
    # pairs[0] indexes input points; pairs[1] indexes built-up polygons.
    result = grouped.copy()
    result["distance_to_built_up_m"] = np.nan
    result["nearest_built_up_name"] = ""
    result.loc[pairs[0], "distance_to_built_up_m"] = distances
    names = areas["BUA22NM"].fillna("Unnamed built-up area").to_numpy()
    result.loc[pairs[0], "nearest_built_up_name"] = names[pairs[1]]
    result = result.sort_values(["distance_to_built_up_m", "ATCOCode"], ascending=[True, True])
    # The closest platform in the same station group represents its proximity.
    result = result.drop_duplicates("location_id").copy()
    if england_geometry is not None:
        # Filter England using *any* platform in the group, not the group's representative.
        inside = gpd.points_from_xy(grouped.Easting, grouped.Northing).intersects(england_geometry)
        english_ids = set(grouped.loc[inside, "location_id"])
        result = result.loc[result.location_id.isin(english_ids)].copy()
    sizes = grouped.groupby("location_id").size().rename("platforms_in_location")
    result = result.join(sizes, on="location_id")
    return result.sort_values(["distance_to_built_up_m", "ATCOCode"], ascending=[False, True]).head(top_n).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="England's bus stops furthest from an ONS 2022 built-up area")
    parser.add_argument("--csv", type=Path, help="A locally downloaded national NaPTAN CSV")
    parser.add_argument("--built-up", type=Path, help="Local GeoJSON or GeoPackage containing BUA22NM and polygons")
    parser.add_argument("--regions", type=Path, default=Path("data/raw/regions-2025.geojson"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("explorations/loneliest-bus-stops/outputs/furthest-from-settlement.csv"))
    args = parser.parse_args()
    naptan = args.csv or download(NAPTAN_CSV, Path("data/raw/naptan-gb.csv"), force=args.force)
    stops = clean_stops(pd.read_csv(naptan, dtype={"ATCOCode": "string"}, low_memory=False))
    areas = gpd.read_file(args.built_up) if args.built_up else load_built_up_areas(Path("data/raw/ons-bua-2022.geojson"), force=args.force)
    boundary = regions(args.regions).geometry.union_all()
    ranked = rank_far_from_built_up(stops, areas, england_geometry=boundary, top_n=args.top)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(args.output, index=False)
    draw_bus_map(ranked, boundary, args.output.with_suffix(".png"),
                 title="Furthest from a mapped settlement",
                 description="England · distance to a mapped 2022 built-up area")
    print(f"Ranked {len(ranked)} English stop locations by distance to a 2022 built-up-area boundary")


if __name__ == "__main__":
    main()