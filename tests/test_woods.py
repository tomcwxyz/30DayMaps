"""Day 03 contract tests, using invented geometries; no network required."""
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

from maps.woods import (read_polygons, normalise, combine_inventories,
    nearest_patch_distance, england_with_revisions, publish, woodland_summary)


def sample(nation: str):
    offsets = {"England": (400000, 530000), "Scotland": (250000, 780000),
               "Wales": (260000, 280000)}
    x, y = offsets[nation]
    return gpd.GeoDataFrame({"CATEGORY": ["ASNW", "PAWS"]},
        geometry=[box(x,y,x+120,y+120),
                  box(x+500,y,x+600,y+100)], crs="EPSG:27700")


def test_normalisation_keeps_source_nation_types_and_metric_area():
    result = normalise(sample("England"), "England")
    assert result.crs.to_epsg() == 27700
    assert list(result.site_type) == ["semi-natural", "plantation"]
    assert result.area_ha.iloc[0] == pytest.approx(1.44)
    assert set(result.nation) == {"England"}


def test_zip_with_geopackage_is_read(tmp_path):
    gpkg = tmp_path / "woods.gpkg"
    sample("Scotland").to_file(gpkg, driver="GPKG")
    zipped = tmp_path / "woods.zip"
    with ZipFile(zipped, "w") as f:
        f.write(gpkg, arcname="nested/woods.gpkg")
    assert len(read_polygons(zipped)) == 2


def test_nearest_distance_is_polygon_edge_distance_not_centroid():
    sample_sites = normalise(sample("England"), "England")
    result = nearest_patch_distance(sample_sites)
    assert list(result.nearest_patch_m) == pytest.approx([380, 380])


def test_revisions_need_completed_county_mask():
    base = sample("England")
    revised = gpd.GeoDataFrame({"CATEGORY":["ASNW"]},
        geometry=[box(400040,530040,400130,530130)], crs=27700)
    with pytest.raises(ValueError, match="completed-county"):
        england_with_revisions(base, revised, None)
    county = gpd.GeoDataFrame(geometry=[box(399999,529999,400200,530200)],crs=27700)
    out = england_with_revisions(base, revised, county)
    assert len(out) == 2
    assert out.geometry.iloc[0].equals(base.geometry.iloc[1])
    assert out.geometry.iloc[1].equals(revised.geometry.iloc[0])


def test_exports_only_verified_geographies(tmp_path):
    paths={}
    for nation in ("England","Scotland","Wales"):
        p=tmp_path/f"{nation}.gpkg"
        sample(nation).to_file(p,driver="GPKG")
        paths[nation]=p
    all_sites=combine_inventories(paths)
    boundaries = gpd.GeoDataFrame({"RGN25CD":["E12000001"]},
       geometry=[box(390000,520000,420000,550000)], crs=27700)
    output=tmp_path/"out"
    files=publish(all_sites,output,boundaries=boundaries)
    assert {p.name for p in files} == {
        "england-ancient-woodland.png", "north-east-ancient-woodland.png",
        "great-britain-ancient-woodland.png"}
    assert (output/"north-east-fragmentation.csv").exists()
    assert (output/"north-east-ancient-woodland.gpkg").exists()
    import json
    manifest=json.loads((output/"source-manifest.json").read_text())
    assert manifest["great_britain_complete"]
    assert not manifest["northern_ireland_included"]
    assert len(woodland_summary(all_sites)) == 3


def test_partial_coverage_cannot_claim_great_britain(tmp_path):
    england = normalise(sample("England"),"England")
    boundaries=gpd.GeoDataFrame({"RGN25CD":["E12000001"]},
        geometry=[box(390000,520000,420000,550000)],crs=27700)
    output=tmp_path/"partial"
    produced=publish(england,output,boundaries=boundaries)
    assert not any("great-britain" in str(f) for f in produced)
    assert not (output/"great-britain-ancient-woodland.png").exists()
