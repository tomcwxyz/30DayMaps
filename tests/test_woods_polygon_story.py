"""Regression tests: source polygons must remain polygons at every zoom level."""
import json

import geopandas as gpd
from PIL import Image
from shapely.geometry import box

from maps.woods_polygon_story import (
    WIDTH,HEIGHT,camera,actual_polygon_layer,choose_local_view,render,GREEN,GOLD,
)


def test_no_symbol_substitution_for_small_polygons():
    view=box(0,0,100000,100000)
    xy=camera(view.bounds)
    little=box(50000,50000,50001,50001)
    big=box(60000,60000,63000,65000)
    img=actual_polygon_layer([little,big],xy,GREEN,view=view)
    assert img.size==(WIDTH,HEIGHT)
    # A one-metre patch must not be inflated to the 9-pixel dots used before.
    x,y=xy(50000.5,50000.5)
    pixels=sum(img.getpixel((a,b))[3]>0
               for a in range(x-6,x+7) for b in range(y-6,y+7))
    assert pixels<=4
    # A properly sized site is still a real polygon with a visible area.
    bx,by=xy(61500,62500)
    assert img.getpixel((bx,by))[3]>0


def test_projection_preserves_orientation():
    xy=camera((0,0,1000,1000))
    assert xy(900,100)[0]>xy(100,100)[0]
    assert xy(100,900)[1]<xy(100,100)[1]


def test_local_zoom_selects_actual_neighbouring_polygons():
    ancient=gpd.GeoDataFrame(geometry=[box(420000,535000,420400,535800)],crs=27700)
    projects=gpd.GeoDataFrame(geometry=[box(421000,535000,421800,535800)],crs=27700)
    window, distance=choose_local_view(ancient,projects,box(410000,525000,430000,545000))
    assert distance==600
    assert window.intersects(ancient.geometry.iloc[0])
    assert window.intersects(projects.geometry.iloc[0])


def test_full_three_chapter_portrait_video_and_manifest(monkeypatch,tmp_path):
    # Three tiny nationally located test polygons, and nearby Tees sites.
    ancient=gpd.GeoDataFrame(
        {"nation":["England","Scotland","Wales","England"]},
        geometry=[box(420000,535000,420400,535800),
                  box(300000,900000,306000,904000),
                  box(220000,290000,226000,295000),
                  box(425000,535000,425800,535800)], crs=27700)
    projects=gpd.GeoDataFrame(geometry=[
        box(421000,535000,421800,535800),
        box(320000,905000,322000,906000),
    ],crs=27700)
    ne=gpd.GeoDataFrame({"RGN25CD":["E12000001"]},
                        geometry=[box(390000,505000,480000,660000)],crs=27700)
    import maps.woods_polygon_story as story
    monkeypatch.setattr(story,"regions",lambda _:ne)
    out=tmp_path/"outputs"
    master=render(ancient,projects,None,out,fps=1,gif=False)
    assert master.stat().st_size>1000
    for n in ("great-britain","north-east","tees-valley"):
        filename=next(out.glob(f"woods-returning-*-{n}.mp4"))
        assert filename.stat().st_size>1000
        assert Image.open(filename.with_suffix(".png")).size==(WIDTH,HEIGHT)
    import imageio.v2 as imageio
    with imageio.get_reader(master,format="FFMPEG") as reader:
        assert tuple(reader.get_meta_data()["size"])==(WIDTH,HEIGHT)
    manifest=json.loads((out/"actual-polygons-manifest.json").read_text())
    assert not manifest["symbols_replacing_polygons"]
    assert not manifest["is_chronological"]
    assert not manifest["northern_ireland_included"]
    assert manifest["chapters"][2]["contains_local_polygon_zoom"]
