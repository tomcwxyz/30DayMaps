"""Portrait cartography regression checks: no synthetic real-world output."""
import json

import geopandas as gpd
from PIL import Image
from shapely.geometry import box

from maps.woods_motion_mobile import (
    WIDTH, HEIGHT, MAP_RECT, TEES_VIEW, geographic_transform,
    polygon_overlay, portrait,
)
from maps.woods_motion import HISTORIC, RETURNING


def tiny_fixtures():
    # Deliberately tiny synthetic polygons within both NE and Tees extent.
    old=gpd.GeoDataFrame(geometry=[
        box(427000,545000,427020,545020),
        box(425000,530000,425800,530700),
    ],crs=27700)
    newer=gpd.GeoDataFrame(geometry=[
        box(428000,545000,428040,545040),
        box(428000,531000,428600,531900),
    ],crs=27700)
    ne=box(390000,505000,475000,660000)
    return old,newer,ne


def test_portrait_map_coordinates_are_geographic_and_on_canvas():
    old,new,region=tiny_fixtures()
    xy=geographic_transform(region)
    xmin,ymin,xmax,ymax=MAP_RECT
    for poly in list(old.geometry)+list(new.geometry):
        x,y=xy(poly.representative_point().x,poly.representative_point().y)
        assert xmin<=x<=xmax
        assert ymin<=y<=ymax
    assert xy(428000,545000)[1] < xy(428000,530000)[1]
    assert xy(428000,545000)[0] > xy(425000,545000)[0]


def test_small_polygons_are_highlighted_at_real_sites_not_moved():
    old,_,region=tiny_fixtures()
    overlay,count=polygon_overlay(old.geometry,geographic_transform(region),
                                  HISTORIC,region,min_symbol_px=9)
    assert overlay.size==(WIDTH,HEIGHT)
    assert count>=1
    point=old.geometry.iloc[0].representative_point()
    x,y=geographic_transform(region)(point.x,point.y)
    assert overlay.getpixel((x,y))[3]>0


def test_portrait_video_and_teesside_detail_keep_provenance(tmp_path):
    old,new,region=tiny_fixtures()
    output=tmp_path/"mobile"
    for detail in (False,True):
        path=portrait(old,new,region,output,focus=detail,fps=1,gif=False)
        assert path.stat().st_size>5000
        import imageio.v2 as imageio
        with imageio.get_reader(path, format="FFMPEG") as reader:
            assert tuple(reader.get_meta_data()["size"]) == (WIDTH, HEIGHT)
        assert Image.open(output/f"{path.stem}-poster.png").size==(WIDTH,HEIGHT)
        data=json.loads((output/f"{path.stem}-manifest.json").read_text())
        assert data["is_time_series"] is False
        assert data["dots_are_to_scale"] is False
        assert data["project_boundaries_are_confirmed_tree_cover"] is False
        assert data["project_polygon_parts_visible"] >= 1
    assert TEES_VIEW.area>0
