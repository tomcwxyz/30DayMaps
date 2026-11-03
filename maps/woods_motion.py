"""Day 03 motion: four truthful frames of historic woods and new projects.

This is NOT a chronological animation or evidence that the areas are fully
planted. WCC shows independently validated/verified project footprints.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from maps.common import NORTH_EAST_CODE, regions

WIDTH, HEIGHT = 1440, 900
FPS = 12
PAPER = (248, 247, 241)
INK = (30, 52, 55)
HISTORIC = (46, 107, 80, 255)
RETURNING = (185, 145, 53, 250)
CONNECTION = (98, 128, 121, 200)
MAP_RECT = (550, 86, 1395, 810)


def font(size: int, *, bold: bool = False):
    candidates = [
        "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf" if bold
        else "/usr/share/fonts/opentype/inter/InterDisplay-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def read_woodlands(path: Path) -> gpd.GeoDataFrame:
    data = gpd.read_file(path)
    if data.crs is None or data.empty:
        raise ValueError("Missing CRS or empty ancient woodland file")
    return data.loc[data.geometry.geom_type.isin(("Polygon", "MultiPolygon"))].to_crs(27700)


def read_projects(path: Path, region) -> gpd.GeoDataFrame:
    """Source must be validated/verified WCC polygon layer, not all planning sites."""
    data = gpd.read_file(path)
    if data.crs is None or data.empty:
        raise ValueError("Missing CRS or empty WCC project polygon layer")
    data = data.loc[data.geometry.geom_type.isin(("Polygon", "MultiPolygon"))].to_crs(27700)
    data = data.loc[data.geometry.intersects(region)].copy()
    if data.empty:
        raise ValueError("No WCC project polygons intersect the North East region")
    data = gpd.clip(data, region)
    if data.empty:
        raise ValueError("No WCC polygons remain after clipping")
    return data


def prepare(ancient_path: Path, projects_path: Path, boundary_path: Path | None = None):
    woods = read_woodlands(ancient_path)
    boundary = (gpd.read_file(boundary_path).to_crs(27700) if boundary_path
                else regions(Path("data/raw/regions-2025.geojson")))
    if "RGN25CD" not in boundary.columns:
        raise ValueError("Official North East boundary requires RGN25CD")
    ne = boundary.loc[boundary.RGN25CD.eq(NORTH_EAST_CODE)]
    if ne.empty:
        raise ValueError("North East region missing from boundaries")
    region = ne.geometry.union_all()
    woods = gpd.clip(woods.loc[woods.geometry.intersects(region)].copy(), region)
    projects = read_projects(projects_path, region)
    if woods.empty:
        raise ValueError("No ancient woodland polygons intersect North East region")
    return woods, projects, region


def proximity_lines(old: gpd.GeoDataFrame, new: gpd.GeoDataFrame,
                    *, threshold_m: float = 1500, limit: int = 22):
    """Illustrative nearest-edge proximity; never modelled ecological corridors."""
    tree = STRtree(list(old.geometry))
    candidates = []
    for polygon in new.geometry:
        idx = int(tree.nearest(polygon))
        old_poly = old.geometry.iloc[idx]
        separation = float(polygon.distance(old_poly))
        if 30 < separation <= threshold_m:
            a, b = nearest_points(polygon, old_poly)
            candidates.append((separation, LineString([a, b])))
    candidates.sort(key=lambda record: record[0])
    return [line for _, line in candidates[:limit]]


def transform(region):
    x0, y0, x1, y1 = region.bounds
    left, top, right, bottom = MAP_RECT
    span_x, span_y = (x1-x0)*1.08, (y1-y0)*1.08
    centre_x, centre_y = (x0+x1)/2, (y0+y1)/2
    scale = min((right-left)/span_x, (bottom-top)/span_y)
    px, py = (left+right)/2, (top+bottom)/2
    return lambda x,y: (round(px+(x-centre_x)*scale),
                         round(py-(y-centre_y)*scale))


def polygon_layer(geoms, xy, color):
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0,0,0,0))
    draw = ImageDraw.Draw(image)
    for geom in geoms:
        shapes = (geom.geoms if isinstance(geom, MultiPolygon) else [geom])
        for poly in shapes:
            if not isinstance(poly, Polygon) or poly.is_empty:
                continue
            pts = [xy(x,y) for x,y in poly.exterior.coords]
            if len(pts) >= 3:
                draw.polygon(pts, fill=color)
                for hole in poly.interiors:
                    draw.polygon([xy(x,y) for x,y in hole.coords], fill=(0,0,0,0))
    return image


def connection_layer(lines, xy):
    image=Image.new("RGBA", (WIDTH, HEIGHT), (0,0,0,0))
    draw=ImageDraw.Draw(image)
    for line in lines:
        start,end=line.coords[0],line.coords[-1]
        x0,y0=xy(*start);x1,y1=xy(*end)
        for t in np.arange(0, 1, .13):
            a=min(1,t+.065)
            draw.line((int(x0+(x1-x0)*t),int(y0+(y1-y0)*t),
                       int(x0+(x1-x0)*a),int(y0+(y1-y0)*a)),
                      fill=CONNECTION,width=3)
    return image


def base_layer(region, xy):
    base=Image.new("RGBA",(WIDTH,HEIGHT),PAPER+(255,))
    draw=ImageDraw.Draw(base)
    for geom in ([region] if isinstance(region,Polygon) else region.geoms):
        pts=[xy(x,y) for x,y in geom.exterior.coords]
        draw.line(pts,fill=(144,158,151,255),width=3,joint="curve")
    draw.rectangle((0,0, 518,HEIGHT),fill=(240,243,236,255))
    draw.line((516,70,516,825),fill=(210,218,209,255),width=1)
    draw.text((54,48),"30 DAY MAP CHALLENGE  /  03",font=font(19,bold=True),fill=(54,104,84))
    draw.text((54,835),"North East England · mapped polygons in British National Grid",
              font=font(15),fill=(92,110,105))
    draw.text((54,860),"Natural England · Woodland Carbon Code · ONS regional boundaries",
              font=font(13),fill=(112,122,117))
    return base


SCENES = (
    ("THE WOODS", "THAT REMEMBER",
     "Ancient woodland fragments still exist\nacross the North East.",
     "Ancient woodland inventory"),
    ("THE WOODS", "THAT ARE RETURNING",
     "Validated woodland creation projects\nappear alongside older woods.",
     "Woodland Carbon Code project areas"),
    ("A LANDSCAPE", "IN TRANSITION",
     "A picture of both what persists\nand where new woodland is planned or growing.",
     "Not a chronological timelapse"),
    ("WHERE WOODS", "COME CLOSE",
     "Some projects sit near ancient woodland.\nProximity is not ecological connectivity.",
     "Lines show gaps of 30 m–1.5 km only"),
)


def draw_overlay(canvas, index, progress, old_n, new_n, gap_n):
    draw=ImageDraw.Draw(canvas)
    first, second, description, note=SCENES[index]
    draw.text((54,170), first,font=font(38,bold=True),fill=INK)
    draw.text((54,218), second,font=font(35,bold=True),fill=INK)
    for i,line in enumerate(description.split("\n")):
        draw.text((54,311+i*31),line,font=font(19),fill=(76,99,91))
    draw.rounded_rectangle((54,445,468,507),radius=13,fill=(255,255,255),
                           outline=(218,225,213),width=1)
    draw.text((73,459),note,font=font(16),fill=(45,87,72))
    draw.text((54,566),f"{old_n:,} ancient woodland polygons",font=font(19,bold=True),fill=HISTORIC)
    draw.text((54,602),f"{new_n:,} mapped new-woodland project areas",
              font=font(18,bold=True),fill=(158,111,39))
    if index==3:
        draw.text((54,644),f"{gap_n} illustrative nearby pairs",
                  font=font(18,bold=True),fill=(89,123,112))
    draw.text((54,745),"Four perspectives, not four years",font=font(17,bold=True),fill=INK)
    draw.text((54,775),"Project boundaries are not evidence that every\npart is already wooded.",
              font=font(15),fill=(92,110,105),spacing=5)
    for i in range(4):
        draw.rounded_rectangle((54+i*107, 114, 144+i*107, 120),
                               radius=3,fill=(38,105,81) if i==index else (193,208,196))


def fade_layer(base, overlay, alpha):
    if alpha<=0:
        return base
    mask=overlay.getchannel("A").point(lambda x:int(x*min(1,alpha)))
    result=overlay.copy()
    result.putalpha(mask)
    return Image.alpha_composite(base,result)


def frame(base, woods, projects, links, index, t, *, counts):
    # Quiet fades between sections; no invented growth or timescale.
    visibility = max(0,min(1,t/.7))
    img=base.copy()
    if index==0:
        img=fade_layer(img,woods,visibility)
    else:
        img=fade_layer(img,woods,1)
        img=fade_layer(img,projects,visibility if index==1 else 1)
    if index==3:
        img=fade_layer(img,links,visibility)
    draw_overlay(img,index,t,*counts)
    return img.convert("RGB")


def animate(woods, projects, region, output: Path, *, fps: int = FPS, gif: bool = True):
    import imageio.v2 as imageio
    output.mkdir(parents=True,exist_ok=True)
    xy=transform(region)
    old_layer=polygon_layer(woods.geometry,xy,HISTORIC)
    new_layer=polygon_layer(projects.geometry,xy,RETURNING)
    lines=proximity_lines(woods,projects)
    link_layer=connection_layer(lines,xy)
    background=base_layer(region,xy)
    counts=(len(woods),len(projects),len(lines))
    mp4=output/"woods-returning-north-east.mp4"
    gif_path=output/"woods-returning-north-east.gif"
    poster=output/"woods-returning-north-east-poster.png"
    frame(background,old_layer,new_layer,link_layer,3,1,counts=counts).save(poster)
    loops=[]
    with imageio.get_writer(mp4,format="FFMPEG",fps=fps,codec="libx264",
                            macro_block_size=16,quality=7,
                            output_params=["-pix_fmt","yuv420p"]) as video:
        for index in range(4):
            for fi in range(int(3.25*fps)):
                image=frame(background,old_layer,new_layer,link_layer,index,
                            fi/fps,counts=counts)
                video.append_data(np.asarray(image))
                # A smaller GIF is suitable for mobile; MP4 is the primary version.
                if gif and fi%2==0:
                    loops.append(image.resize((720,450),Image.Resampling.LANCZOS))
    if gif:
        loops[0].save(gif_path,format="GIF",save_all=True,append_images=loops[1:],
                      duration=int(2000/fps),loop=0,optimize=True)
    meta={"ancient_woodland_polygons": len(woods),
          "woodland_carbon_code_polygon_parts": len(projects),
          "illustrative_pairs_below_1_5km": len(lines),
          "is_time_series": False,
          "projects_are_completed_planting": False,
          "method": "Four editorial layers; project footprints are validation-stage or later; gaps 30-1500m are illustrative, not ecological corridors."}
    (output/"motion-manifest.json").write_text(json.dumps(meta,indent=2))
    print("Created",mp4,gif_path,poster,meta,flush=True)
    return mp4


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ancient",type=Path,required=True)
    parser.add_argument("--projects",type=Path,required=True)
    parser.add_argument("--boundaries",type=Path)
    parser.add_argument("--output",type=Path,default=Path("challenges/03-polygons/outputs/motion"))
    parser.add_argument("--no-gif",action="store_true")
    args=parser.parse_args()
    woods,projects,region=prepare(args.ancient,args.projects,args.boundaries)
    animate(woods,projects,region,args.output,gif=not args.no_gif)


if __name__=="__main__":
    main()
