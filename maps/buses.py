"""England's geographically loneliest bus-stop locations (NaPTAN research).

An active NaPTAN stop is a mapped stop record, not proof of a running service.
The geographic ranking groups nearby opposite-side platforms with the same name,
and measures each group's shortest straight-line distance to a DIFFERENT group.
National GB reference points remain available across England's borders.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from maps.common import regions, download, NAPTAN_CSV

BOARDING_STOP_TYPES = {"BCT", "BCS", "BCQ"}


def clean_stops(data: pd.DataFrame) -> pd.DataFrame:
    """Retain bus boarding locations, excluding entrances/access nodes."""
    required = {"ATCOCode", "StopType", "Easting", "Northing", "Status"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing NaPTAN columns: {sorted(missing)}")
    data = data.copy()
    data["ATCOCode"] = data["ATCOCode"].astype(str).str.strip()
    data = data.loc[
        data.StopType.astype(str).str.upper().isin(BOARDING_STOP_TYPES)
        & data.Status.astype(str).str.casefold().eq("active")
        & data["ATCOCode"].ne("")
    ].copy()
    for column in ("Easting", "Northing"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["Easting", "Northing"]).drop_duplicates("ATCOCode")
    # British National Grid bounds; ignore invalid placeholder coordinates.
    data = data.loc[data.Easting.between(0, 700000) & data.Northing.between(0, 1250000)]
    for col in ("CommonName", "NptgLocalityCode", "LocalityName", "Street", "BusStopType"):
        if col not in data:
            data[col] = ""
        data[col] = data[col].fillna("").astype(str).str.strip()
    # A hail-and-ride area is not one uniquely defined boarding point.
    data = data.loc[~data.BusStopType.str.upper().isin(["HAR", "FLX"])].copy()
    return data.reset_index(drop=True)


def group_stop_locations(stops: pd.DataFrame, *, pair_radius_m: float = 75) -> pd.DataFrame:
    """Join close, like-named platforms while keeping unrelated locations apart.

    This is a reproducible working definition of 'one bus-stop place', not a
    canonical government grouping. Each member receives a stable group ID.
    """
    if stops.empty:
        return stops.assign(location_id=pd.Series(dtype="object"))
    coords = stops[["Easting", "Northing"]].to_numpy(dtype=float)
    tree = cKDTree(coords)
    parent = np.arange(len(stops))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return int(i)

    def merge(i, j):
        i, j = root(i), root(j)
        if i != j:
            parent[max(i, j)] = min(i, j)

    names = stops.CommonName.str.casefold().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip().to_numpy()
    localities = stops.NptgLocalityCode.to_numpy()
    stop_types = stops.StopType.to_numpy()
    for i, j in tree.query_pairs(pair_radius_m):
        # Pairing across a station can involve different bays: those are
        # distinct platforms but one place for this *geographic* ranking.
        same_name = bool(names[i]) and names[i] == names[j]
        same_locality_station = (stop_types[i] in {"BCS", "BCQ"}
                                 and stop_types[j] in {"BCS", "BCQ"}
                                 and bool(localities[i]) and localities[i] == localities[j])
        if same_name or same_locality_station:
            merge(i, j)
    result = stops.copy()
    result["location_id"] = [stops.iloc[root(i)].ATCOCode for i in range(len(stops))]
    return result


def rank_isolated_locations(stops: pd.DataFrame, *, england_geometry=None, top_n: int = 100,
                            nearby_metres: float = 75) -> pd.DataFrame:
    """Rank English boarding locations, using all GB locations as neighbours.

    A location's distance is the closest pair of individual stops across two
    different groups, rather than centroid distance between groups.
    """
    grouped = group_stop_locations(stops, pair_radius_m=nearby_metres)
    if grouped.location_id.nunique() < 2:
        raise ValueError("Need at least two distinct bus stop locations")
    coords = grouped[["Easting", "Northing"]].to_numpy(dtype=float)
    ids = grouped.location_id.to_numpy()
    tree = cKDTree(coords)
    # Start at k=2 and expand only if a group's own platforms fill the window.
    k = min(8, len(grouped))
    distances = np.full(len(grouped), np.inf)
    nearest_ids = np.full(len(grouped), "", dtype=object)
    unresolved = np.arange(len(grouped))
    while unresolved.size:
        d, j = tree.query(coords[unresolved], k=k)
        if k == 1:
            d, j = d[:, None], j[:, None]
        different = ids[j] != ids[unresolved, None]
        valid = different.any(axis=1)
        if valid.any():
            first = different.argmax(axis=1)
            selected = unresolved[valid]
            distances[selected] = d[valid, first[valid]]
            nearest_ids[selected] = ids[j[valid, first[valid]]]
        unresolved = unresolved[~valid]
        if k >= len(grouped):
            if len(unresolved):
                raise RuntimeError("Cannot find another distinct location for all stops")
            break
        k = min(k * 2, len(grouped))
    grouped["nearest_other_location_m"] = distances
    grouped["nearest_location_id"] = nearest_ids
    output = grouped.sort_values("nearest_other_location_m", kind="stable").drop_duplicates("location_id")
    sizes = grouped.groupby("location_id").size().rename("platforms_in_location")
    output = output.join(sizes, on="location_id")
    if england_geometry is not None:
        geoms = gpd.points_from_xy(output.Easting, output.Northing)
        output = output.loc[geoms.intersects(england_geometry)]
    output = output.sort_values(["nearest_other_location_m", "ATCOCode"], ascending=[False, True])
    return output.head(top_n).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="England's geographically isolated bus stop locations (provisional)")
    parser.add_argument("--csv", type=Path, help="Optional locally downloaded GB-wide NaPTAN CSV")
    parser.add_argument("--force", action="store_true", help="Refresh cached national stop data")
    parser.add_argument("--output", type=Path, default=Path("data/processed/england-bus-stop-geographical-top-100-candidates.csv"))
    parser.add_argument("--regions", type=Path, default=Path("data/raw/regions-2025.geojson"))
    parser.add_argument("--top", type=int, default=100)
    args = parser.parse_args()
    csv_path = args.csv or download(NAPTAN_CSV, Path("data/raw/naptan-gb.csv"), force=args.force)
    dataset = pd.read_csv(csv_path, low_memory=False, dtype={"ATCOCode":"string"})
    boundary = regions(args.regions).geometry.union_all()
    candidates = rank_isolated_locations(clean_stops(dataset), england_geometry=boundary, top_n=args.top)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(args.output, index=False)
    from maps.render import draw_bus_map
    draw_bus_map(candidates, boundary, args.output.with_suffix(".png"))
    print(f"Wrote {len(candidates)} England-only candidates to {args.output}; not a service-frequency ranking")


if __name__ == "__main__":
    main()