"""Day 01: English trig pillars, North East detail and private visit records."""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from maps.common import OS_TRIG_ARCHIVE, NORTH_EAST_CODE, download, regions
from maps.render import draw_trig_map


def archive_rows(path: Path) -> pd.DataFrame:
    """Read OS's zipped archive without assuming CSV filename or encoding."""
    with ZipFile(path) as archive:
        files = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(files) != 1:
            raise ValueError(f"Expected one CSV in the OS archive, found {files}")
        csv_bytes = archive.read(files[0])
    try:
        df = pd.read_csv(BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding="cp1252")
    df.columns = df.columns.str.strip()
    return df


def parse_pillars(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Only physical trig pillars, not every OS triangulation station."""
    required = ["TYPE OF MARK", "EASTING", "NORTHING", "HEIGHT", "DESTROYED MARK INDICATOR"]
    absent = [column for column in required if column not in df.columns]
    if absent:
        raise ValueError(f"OS archive missing fields: {absent}; found {list(df.columns)}")
    rows = df[df["TYPE OF MARK"].str.strip().str.lower().eq("pillar")].copy()
    if rows.empty:
        raise ValueError("No 'pillar' records found. Inspect TYPE OF MARK values before proceeding.")
    rows["easting"] = pd.to_numeric(rows["EASTING"], errors="coerce")
    rows["northing"] = pd.to_numeric(rows["NORTHING"], errors="coerce")
    rows["height_m"] = pd.to_numeric(rows["HEIGHT"], errors="coerce")
    rows = rows.dropna(subset=["easting", "northing"])
    rows["name"] = rows.get("Trig Name", pd.Series("", index=rows.index)).astype(str).str.strip()
    rows["name"] = rows["name"].mask(rows["name"].eq(""), rows.get("STATION NAME", "Unnamed pillar"))
    raw_id = rows.get("New Name", pd.Series("", index=rows.index)).astype(str).str.strip()
    # Stable fallback when OS's newer station identifier is blank.
    fallback = "OS-" + rows["easting"].round().astype(int).astype(str) + "-" + rows["northing"].round().astype(int).astype(str)
    rows["station_id"] = raw_id.mask(raw_id.eq(""), fallback)
    if rows["station_id"].duplicated().any():
        raise ValueError("Duplicate OS station identifiers. Review the archive rather than silently merging visits.")
    destroyed_raw = rows["DESTROYED MARK INDICATOR"].astype(str).str.strip().str.lower()
    rows["destroyed_in_archive"] = destroyed_raw.isin(["1", "y", "yes", "true"])
    rows["archive_status_unknown"] = ~destroyed_raw.isin(["0", "1", "y", "n", "yes", "no", "true", "false"])
    rows["destroyed_raw"] = rows["DESTROYED MARK INDICATOR"]
    return gpd.GeoDataFrame(
        rows[["station_id", "name", "easting", "northing", "height_m", "destroyed_in_archive", "archive_status_unknown", "destroyed_raw"]],
        geometry=gpd.points_from_xy(rows["easting"], rows["northing"]), crs="EPSG:27700"
    ).reset_index(drop=True)


def in_area(pillars: gpd.GeoDataFrame, area) -> gpd.GeoDataFrame:
    return pillars[pillars.geometry.intersects(area)].copy()


def read_visits(csv_path: Path | None) -> pd.DataFrame:
    if csv_path is None or not Path(csv_path).exists():
        return pd.DataFrame(columns=["station_id", "visited", "date", "notes"])
    visits = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if not {"station_id", "visited"}.issubset(visits.columns):
        raise ValueError("Visits CSV must include station_id,visited")
    visits["station_id"] = visits["station_id"].str.strip()
    if visits["station_id"].duplicated().any():
        raise ValueError("Duplicate station IDs in visits CSV")
    visits["visited"] = visits["visited"].str.strip().str.lower().isin(["true", "1", "yes", "y"])
    return visits


def add_visits(pillars: gpd.GeoDataFrame, visits: pd.DataFrame) -> gpd.GeoDataFrame:
    result = pillars.merge(visits[["station_id", "visited"]], how="left", on="station_id", validate="one_to_one")
    result["visited"] = result["visited"].map(lambda value: bool(value) if pd.notna(value) else False).astype(bool)
    return result


def rank_extremes(england: gpd.GeoDataFrame, all_gb: gpd.GeoDataFrame, n: int = 10):
    """England-only candidates; nearest surviving-in-archive pillar across all GB."""
    candidates = england.loc[~england["destroyed_in_archive"]].copy()
    standing_gb = all_gb.loc[~all_gb["destroyed_in_archive"]]
    if len(standing_gb) < 2:
        raise ValueError("Need at least two archive-standing pillars")
    tree = cKDTree(standing_gb[["easting", "northing"]].to_numpy())
    distances, indices = tree.query(candidates[["easting", "northing"]].to_numpy(), k=2)
    # A candidate exists in the GB reference: select its nearest OTHER station.
    ref_ids = standing_gb["station_id"].to_numpy()
    candidate_ids = candidates["station_id"].to_numpy()
    nearest_dist = np.where(ref_ids[indices[:, 0]] == candidate_ids, distances[:, 1], distances[:, 0])
    candidates["nearest_pillar_km"] = nearest_dist / 1000.0
    highest = candidates.dropna(subset=["height_m"]).sort_values("height_m", ascending=False).head(n)
    isolated = candidates.sort_values("nearest_pillar_km", ascending=False).head(n)
    return highest, isolated


def make_maps(archive: Path | None, output: Path, visits_path: Path | None, *, force: bool = False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    os_zip = Path(archive) if archive is not None else download(OS_TRIG_ARCHIVE, Path("data/raw/CompleteTrigArchive.zip"), force=force)
    all_gb = parse_pillars(archive_rows(os_zip))
    boundaries = regions(Path("data/raw/regions-2025.geojson"), force=force)
    english_geom = boundaries.geometry.union_all()
    ne_geom = boundaries.loc[boundaries.RGN25CD.eq(NORTH_EAST_CODE)].geometry.union_all()
    england = in_area(all_gb, english_geom)
    ne = in_area(england, ne_geom)
    visits = read_visits(visits_path)
    unknown_visits = set(visits.station_id) - set(all_gb.station_id)
    if unknown_visits:
        raise ValueError(f"Unknown visited trig IDs: {sorted(unknown_visits)[:10]}")
    england = add_visits(england, visits)
    ne = add_visits(ne, visits)
    highest, isolated = rank_extremes(england, all_gb)
    export_cols = ["station_id", "name", "height_m", "destroyed_in_archive", "archive_status_unknown", "visited", "easting", "northing"]
    england[export_cols].to_csv(output / "england-pillars.csv", index=False)
    ne[export_cols].to_csv(output / "north-east-pillars.csv", index=False)
    highest[export_cols].to_csv(output / "england-top-10-highest.csv", index=False)
    isolated[export_cols + ["nearest_pillar_km"]].to_csv(output / "england-top-10-isolated.csv", index=False)
    views = [
        ("england-overview", england, english_geom, "The points that mapped England", "elevation", None),
        ("england-visited", england, english_geom, "My trig points", "visited", None),
        ("england-highest", england, english_geom, "The ten highest trig pillars", "highlights", highest),
        ("england-isolated", england, english_geom, "The ten most isolated trig pillars", "highlights", isolated),
        ("england-lost", england, english_geom, "The lost pillars", "lost", None),
        ("north-east-detail", ne, ne_geom, "The points that mapped the North East", "elevation", None),
    ]
    for filename, points, outline, title, mode, highlighted in views:
        draw_trig_map(points, outline, title, output / f"{filename}.png", mode=mode, highlighted=highlighted)
    print(f"Saved {len(england):,} English and {len(ne):,} North East pillars to {output}")
    print(f"Visited (England): {int(england.visited.sum())} | England archival lost: {int(england.destroyed_in_archive.sum())}")


def main():
    parser = argparse.ArgumentParser(description="Build England and North East trig-point maps")
    parser.add_argument("--archive", type=Path, help="Local copy of the OS complete trig ZIP; otherwise download")
    parser.add_argument("--visits", type=Path, default=Path("data/private/visited.csv"))
    parser.add_argument("--output", type=Path, default=Path("challenges/01-points/outputs"))
    parser.add_argument("--force", action="store_true", help="Refresh cached public sources")
    args = parser.parse_args()
    make_maps(args.archive, args.output, args.visits, force=args.force)


if __name__ == "__main__":
    main()
