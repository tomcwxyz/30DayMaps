"""Loneliest bus stops: national stop-location nearest-neighbour research prototype.

This intentionally does NOT call a low-frequency stop 'unserved' or 'lonely' until
we have inspected duplicate platforms, stops without service and dataset quality.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
from scipy.spatial import cKDTree


STOP_TYPES = {"BCT", "BCS", "BCQ", "BCE", "BST", "BCM", "BCP"}


def clean_stops(data: pd.DataFrame) -> pd.DataFrame:
    required = {"ATCOCode", "StopType", "Easting", "Northing", "Status"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing NaPTAN columns: {sorted(missing)}")
    data = data.copy()
    data = data.loc[data.StopType.isin(STOP_TYPES) & data.Status.astype(str).str.lower().eq("active")]
    data["Easting"] = pd.to_numeric(data.Easting, errors="coerce")
    data["Northing"] = pd.to_numeric(data.Northing, errors="coerce")
    data = data.dropna(subset=["Easting", "Northing"]).drop_duplicates("ATCOCode")
    return data


def rank_isolated_locations(stops: pd.DataFrame, *, nearby_metres: int = 75, top_n: int = 100) -> pd.DataFrame:
    """Naive nearest stop baseline for quality audit. A later stage will cluster platforms."""
    if len(stops) < 2:
        raise ValueError("Need at least two stops")
    coords = stops[["Easting", "Northing"]].to_numpy()
    tree = cKDTree(coords)
    distances, _ = tree.query(coords, k=2)
    ranked = stops.copy()
    ranked["nearest_other_stop_m"] = distances[:, 1]
    ranked["opposite_side_pair_possible"] = ranked.nearest_other_stop_m.le(nearby_metres)
    return ranked.sort_values("nearest_other_stop_m", ascending=False).head(top_n)


def main():
    parser = argparse.ArgumentParser(description="Initial bus stop isolation audit — NOT a final top-100 ranking")
    parser.add_argument("--csv", type=Path, required=True, help="Downloaded national NaPTAN CSV")
    parser.add_argument("--output", type=Path, default=Path("data/processed/bus-stop-isolation-audit.csv"))
    args = parser.parse_args()
    df = pd.read_csv(args.csv, low_memory=False)
    ranked = rank_isolated_locations(clean_stops(df))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(args.output, index=False)
    print(f"Wrote {len(ranked)} candidate stops to {args.output}. Not yet an England-only verified ranking.")


if __name__ == "__main__":
    main()
