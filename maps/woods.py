"""Day 03 — Polygons: ancient woodland inventories across Great Britain.

The three national inventories are comparable as *mapped historic woodland sites*,
not as equivalent surveys. Northern Ireland is intentionally excluded pending
permission from the Woodland Trust. Don't infer missing areas are woodland-free.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from shapely.strtree import STRtree

from maps.common import download, regions, NORTH_EAST_CODE

# Verified publisher-hosted archives; GB processing works offline with --england,
# --scotland and --wales local dataset paths as well.
ENGLAND_URL = ("https://environment.data.gov.uk/api/file/download?"
    "fileDataSetId=008cdfcf-893b-48f6-937a-3891a2a698c9"
    "&fileName=Ancient_Woodland_England.gpkg.zip")
SCOTLAND_URL = "https://gis-downloads.nature.scot/AWI_SCOTLAND_GPKG_27700.zip"
WALES_WFS = ("https://datamap.gov.wales/geoserver/inspire-nrw/ows?"
    "service=WFS&version=2.0.0&request=GetFeature"
    "&typeNames=inspire-nrw:NRW_ANCIENT_WOODLAND_INVENTORY_2021"
    "&outputFormat=application/json")

INK = "#1E353B"
PAPER = "#F7F6F0"
GREEN = "#306852"
PALE = "#A3BFA7"
GOLD = "#C18E46"
NATION_COLOURS = {"England": "#387159", "Scotland": "#679D88", "Wales": "#C08E4E"}


def read_polygons(path: Path) -> gpd.GeoDataFrame:
    """Load publisher GeoPackage, GeoJSON or archive; require declared CRS."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        # Explicitly select a vector file, not an arbitrary CSV/metadata resource.
        with ZipFile(path) as archive:
            entries = [n for n in archive.namelist()
                       if not n.startswith("__MACOSX/")
                       and n.lower().endswith((".gpkg", ".geojson", ".json"))]
            if len(entries) != 1:
                raise ValueError(f"Expected one GeoPackage/GeoJSON in {path}; found {entries}")
            import tempfile
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / Path(entries[0]).name
                with archive.open(entries[0]) as src, target.open("wb") as dest:
                    shutil.copyfileobj(src, dest)
                return read_polygons(target)
    data = gpd.read_file(path)
    if data.crs is None:
        raise ValueError(f"Source has no defined coordinate reference system: {path}")
    if data.empty:
        raise ValueError(f"Empty ancient woodland dataset: {path}")
    polygons = data.loc[data.geometry.notna() &
                        data.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if polygons.empty:
        raise ValueError(f"No polygon geometries in {path}")
    return polygons.to_crs(27700)


def classify_site(row) -> str:
    """Retain conservative cross-inventory types, never invent categories."""
    keys = [k for k in row.index if k != "geometry" and
            any(t in str(k).lower() for t in ("category", "catagory", "type", "class"))]
    terms = " ".join(str(row[k]) for k in keys if pd.notna(row[k])).lower()
    if "paws" in terms or "plantation on ancient" in terms or "replanted" in terms:
        return "plantation"
    if "asnw" in terms or "ancient semi" in terms:
        return "semi-natural"
    return "other-inventory-category"


def normalise(data: gpd.GeoDataFrame, nation: str) -> gpd.GeoDataFrame:
    if nation not in NATION_COLOURS:
        raise ValueError(f"Unexpected nation {nation}")
    result = gpd.GeoDataFrame({
        "nation": [nation] * len(data),
        "source_row": [str(x) for x in data.index],
        "site_type": [classify_site(row) for _, row in data.iterrows()],
    }, geometry=list(data.geometry), crs=data.crs).to_crs(27700)
    result["area_ha"] = result.geometry.area / 10_000
    return result.loc[result.area_ha.gt(0)].reset_index(drop=True)


def combine_inventories(inputs: dict[str, Path]) -> gpd.GeoDataFrame:
    """Never silently label England-only output as Great Britain."""
    if not inputs:
        raise ValueError("At least one national source is required")
    combined = pd.concat(
        [normalise(read_polygons(path), nation) for nation, path in inputs.items()],
        ignore_index=True,
    )
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=27700)


def england_with_revisions(base: gpd.GeoDataFrame,
                           revised: gpd.GeoDataFrame | None,
                           completed_counties: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    """Supersede *whole completed counties*, not just revised polygon footprints.

    Without the official completed-county geography, retain baseline rather than
    double-counting sites or wrongly removing old woodland only where polygons overlap.
    """
    if revised is None and completed_counties is None:
        return base
    if revised is None or completed_counties is None:
        raise ValueError("Revised woodland requires completed-county coverage polygons")
    if base.crs is None or revised.crs is None or completed_counties.crs is None:
        raise ValueError("All layers require a CRS")
    base = base.to_crs(27700)
    revised = revised.to_crs(27700)
    coverage = completed_counties.to_crs(27700).geometry.union_all()
    old = base.loc[~base.geometry.representative_point().intersects(coverage)]
    newer = revised.loc[revised.geometry.representative_point().intersects(coverage)]
    return gpd.GeoDataFrame(pd.concat([old, newer], ignore_index=True), crs=27700)


def nearest_patch_distance(patches: gpd.GeoDataFrame,
                           reference: gpd.GeoDataFrame | None = None) -> gpd.GeoDataFrame:
    """Polygon-edge separation in metres; zero means touches/overlaps.

    Reference must include the candidate patches. STRtree exclusive=True avoids
    counting each geometry itself as a neighbour. This is geometric isolation,
    not a measure of ecological connectivity or fragmented habitat quality.
    """
    result = patches.copy()
    all_sites = reference if reference is not None else patches
    if len(all_sites) < 2:
        result["nearest_patch_m"] = float("nan")
        return result
    tree = STRtree(list(all_sites.geometry))
    distances = np.asarray(tree.query_nearest(
        list(result.geometry), return_distance=True,
        all_matches=False, exclusive=True)[1], dtype=float)
    if len(distances) != len(result):
        raise ValueError("Nearest woodland query returned unexpected dimensions")
    result["nearest_patch_m"] = distances
    return result


def woodland_summary(sites: gpd.GeoDataFrame) -> pd.DataFrame:
    return (sites.groupby("nation").agg(
        polygons=("nation", "size"), mapped_area_ha=("area_ha", "sum"),
        median_patch_ha=("area_ha", "median")
    ).reset_index().sort_values("nation"))


def render_woods(sites: gpd.GeoDataFrame, output: Path, *,
                 area: str, boundary=None) -> None:
    """Static cartography; all patch polygons drawn in their actual coordinates."""
    if area not in {"great-britain", "england", "north-east"}:
        raise ValueError(f"Invalid map area: {area}")
    fig = plt.figure(figsize=(10, 12), facecolor=PAPER)
    ax = fig.add_axes([0.075, 0.175, 0.85, 0.68], facecolor=PAPER)
    if boundary is not None:
        gpd.GeoSeries([boundary], crs=27700).boundary.plot(
            ax=ax, color="#93A4A0", linewidth=0.5, zorder=1)
    for nation in ("Scotland", "England", "Wales"):
        part = sites.loc[sites.nation.eq(nation)]
        if not part.empty:
            part.plot(ax=ax, color=NATION_COLOURS[nation], linewidth=0,
                      edgecolor="none", alpha=.95, rasterized=True, zorder=2)
    if boundary is not None:
        xmin, ymin, xmax, ymax = boundary.bounds
    else:
        xmin, ymin, xmax, ymax = sites.total_bounds
    dx, dy = xmax-xmin, ymax-ymin
    ax.set_xlim(xmin - dx*.035, xmax + dx*.035)
    ax.set_ylim(ymin - dy*.035, ymax + dy*.035)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    heading = {
        "great-britain": "The Woods That Remember",
        "england": "The Woods That Remember",
        "north-east": "Ancient Woodland · North East",
    }[area]
    fig.text(.075, .955, "30 DAY MAP CHALLENGE  /  DAY 03: POLYGONS",
             fontsize=10, weight="bold", color=GREEN)
    fig.text(.075, .914, heading, fontsize=24, weight="bold", color=INK)
    fig.text(.075, .883, "Historic woodland fragments, mapped from national inventories",
             fontsize=10, color=INK)
    legends = [Line2D([0],[0],marker="s",markersize=8,linestyle="",
                      markerfacecolor=NATION_COLOURS[n],markeredgecolor="none",label=n)
               for n in ("Scotland", "England", "Wales") if n in set(sites.nation)]
    fig.legend(handles=legends, loc="lower left", bbox_to_anchor=(.075, .112),
               frameon=False, fontsize=9, ncol=3)
    fig.text(.075, .085, "Mapped ancient woodland polygons; inventories differ in dates, coverage and definitions.",
             fontsize=8.3, color=INK)
    fig.text(.075, .063, "Small patches may be invisible at this scale. Not a complete inventory of all trees.",
             fontsize=8.0, color=INK)
    fig.text(.075, .042, "© Natural England; Copyright NatureScot, contains OS data © Crown copyright;",
             fontsize=7.2, color="#778782")
    fig.text(.075, .028, "© Natural Resources Wales and database right; ONS boundaries · see README for licences.",
             fontsize=7.2, color="#778782")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=190, bbox_inches="tight", pad_inches=.14, facecolor=PAPER)
    plt.close(fig)


def publish(sites: gpd.GeoDataFrame, output: Path, *,
            boundaries: gpd.GeoDataFrame | None = None,
            export_gpkg: bool = True) -> list[Path]:
    """Produce only honest, explicitly named geographies."""
    output.mkdir(parents=True, exist_ok=True)
    produced = []
    complete = set(sites.nation) == {"England", "Scotland", "Wales"}
    if complete:
        target = output / "great-britain-ancient-woodland.png"
        render_woods(sites, target, area="great-britain")
        produced.append(target)
    if "England" in set(sites.nation):
        if boundaries is None:
            boundaries = regions(Path("data/raw/regions-2025.geojson"))
        boundaries = boundaries.to_crs(27700)
        england = sites.loc[sites.nation.eq("England")]
        ne = boundaries.loc[boundaries.RGN25CD.eq(NORTH_EAST_CODE)]
        if ne.empty:
            raise ValueError("North East region missing from ONS boundaries")
        ne_poly = ne.geometry.union_all()
        ne_woods = england.loc[england.geometry.intersects(ne_poly)].copy()
        if not ne_woods.empty:
            ne_woods = gpd.clip(ne_woods, ne_poly)
            ne_woods["area_ha"] = ne_woods.geometry.area / 10_000
            target = output / "north-east-ancient-woodland.png"
            render_woods(ne_woods, target, area="north-east", boundary=ne_poly)
            produced.append(target)
            if export_gpkg:
                ne_woods.to_file(output / "north-east-ancient-woodland.gpkg",
                                 layer="ancient_woodland", driver="GPKG", index=False)
            # Limit nearest-distance calculation to North East inventory:
            # don't misrepresent it as an all-GB isolation measure.
            neighbours = nearest_patch_distance(ne_woods)
            neighbours[["nation", "site_type", "area_ha", "nearest_patch_m"]].to_csv(
                output / "north-east-fragmentation.csv", index=False)
        target = output / "england-ancient-woodland.png"
        render_woods(england, target, area="england",
                     boundary=boundaries.geometry.union_all())
        produced.append(target)
    woodland_summary(sites).to_csv(output / "woodland-summary.csv", index=False)
    (output / "source-manifest.json").write_text(json.dumps(
        {"included_nations": sorted(set(sites.nation)),
         "great_britain_complete": complete,
         "northern_ireland_included": False,
         "england_revised_inventory": False,
         "distance_method": "nearest other polygon within North East inventory, metres"},
        indent=2), encoding="utf-8")
    return produced


def main():
    parser = argparse.ArgumentParser(description="The Woods That Remember — Day 03")
    parser.add_argument("--england", type=Path, help="Official England GeoPackage or zipped GeoPackage")
    parser.add_argument("--scotland", type=Path, help="Official Scotland inventory")
    parser.add_argument("--wales", type=Path, help="Official Wales inventory")
    parser.add_argument("--download", action="store_true",
                        help="Download publisher-hosted England and Scotland archives")
    parser.add_argument("--output", type=Path, default=Path("challenges/03-polygons/outputs"))
    args = parser.parse_args()
    inputs = {}
    if args.download:
        inputs["England"] = download(ENGLAND_URL, Path("data/raw/england-ancient-woodland.gpkg.zip"))
        inputs["Scotland"] = download(SCOTLAND_URL, Path("data/raw/scotland-ancient-woodland.gpkg.zip"))
    for nation, path in (("England",args.england),("Scotland",args.scotland),("Wales",args.wales)):
        if path is not None:
            inputs[nation] = path
    if not inputs:
        parser.error("Pass --england, --scotland, --wales and/or --download")
    print("Loading", sorted(inputs), flush=True)
    sites = combine_inventories(inputs)
    print(f"Loaded {len(sites):,} woodland polygons", flush=True)
    maps = publish(sites, args.output)
    print("Created:", *(str(p) for p in maps), sep="\n", flush=True)


if __name__ == "__main__":
    main()
