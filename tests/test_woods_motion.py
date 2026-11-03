"""Day 03 motion tests: real geometry, invented tiny test fixtures."""
import json

import geopandas as gpd
import pytest
from shapely.geometry import box

from maps.woods_motion import (
    prepare, proximity_lines, transform, polygon_layer, frame, base_layer,
    read_projects, read_woodlands, animate, NORTH_EAST_CODE,
)
from maps.woods_wcc import find_project_layer


def fixture_layers(tmp_path):
    old=gpd.GeoDataFrame({"site":["ancient"]},
        geometry=[box(420000,530000,420500,530500)],crs="EPSG:27700")
    new=gpd.GeoDataFrame({"status":["Validated"]},
        geometry=[box(421000,530100,421400,530500)],crs="EPSG:27700")
    regions=gpd.GeoDataFrame({"RGN25CD":[NORTH_EAST_CODE]},
        geometry=[box(400000,510000,470000,650000)],crs="EPSG:27700")
    old_path=tmp_path/"old.gpkg";new_path=tmp_path/"projects.gpkg"
    boundary_path=tmp_path/"region.geojson"
    old.to_file(old_path,driver="GPKG")
    new.to_file(new_path,driver="GPKG")
    regions.to_file(boundary_path,driver="GeoJSON")
    return old_path,new_path,boundary_path


def test_data_clipped_in_projected_coordinates(tmp_path):
    old,new,region=fixture_layers(tmp_path)
    woods,projects,boundary=prepare(old,new,region)
    assert woods.crs.to_epsg()==27700
    assert projects.crs.to_epsg()==27700
    assert len(woods)==len(projects)==1
    assert len(proximity_lines(woods,projects))==1


def test_proximity_not_invented_corridor():
    a=gpd.GeoDataFrame(geometry=[box(0,0,10,10)],crs=27700)
    b=gpd.GeoDataFrame(geometry=[box(510,0,520,10)],crs=27700)
    assert len(proximity_lines(a,b,threshold_m=1000))==1
    assert len(proximity_lines(a,b,threshold_m=250))==0


def test_render_creates_real_mp4_and_poster(tmp_path):
    old,new,region=fixture_layers(tmp_path)
    woods,projects,boundary=prepare(old,new,region)
    out=tmp_path/"motion"
    video=animate(woods,projects,boundary,out,fps=2,gif=False)
    assert video.stat().st_size>10000
    assert (out/"woods-returning-north-east-poster.png").stat().st_size>1000
    stats=json.loads((out/"motion-manifest.json").read_text())
    assert stats["is_time_series"] is False
    assert stats["projects_are_completed_planting"] is False


class Response:
    def __init__(self,payload): self.payload=payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class FakeDiscovery:
    def get(self,url,*,params,timeout):
        return Response({"results":[{"title":"Woodland Carbon Code Projects",
            "url":"https://services1.arcgis.com/example/arcgis/rest/services/WCC/FeatureServer",
            "owner":"ScottishForestry"}]})


def test_discovery_targets_named_project_polygons():
    assert find_project_layer(FakeDiscovery()).endswith("/FeatureServer")


class Ambiguous:
    def get(self,url,*,params,timeout):
        return Response({"results":[
            {"title":"Woodland Carbon Code Projects","url":"https://services1.arcgis.com/a/rest/services/A/FeatureServer"},
            {"title":"Woodland Carbon Code Projects","url":"https://services1.arcgis.com/b/rest/services/B/FeatureServer"},
        ]})


def test_ambiguous_service_fails_closed():
    with pytest.raises(RuntimeError,match="Ambiguous"):
        find_project_layer(Ambiguous())
