"""Day 03 portrait motion: accessible mobile layout and a truthful Tees close-up.

Uses the exact woodland and Woodland Carbon Code polygons from woods_motion.
Small mapped shapes may receive a centred *symbol* for visibility; the
symbol is not to scale and is placed at a point inside the real geometry.
This is a four-layer editorial reveal, never a dated planting timelapse.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, MultiPolygon, LineString, box

from maps.woods_motion import (
    prepare, proximity_lines, font, PAPER, INK, HISTORIC, RETURNING,
    CONNECTION,
)

WIDTH, HEIGHT = 1080, 1920
MAP_RECT = (52, 445, 1028, 1458)
PAPER_RGB = PAPER
SOFT = (239, 243, 234)
GREY = (90, 108, 102)
TEES_VIEW = box(392000, 505000, 479000, 582000)


SCENES = (
    ("THE WOODS", "THAT REMEMBER",
     ("Ancient woodland fragments", "remain across the region.")),
    ("THE WOODS", "THAT ARE RETURNING",
     ("Woodland creation projects", "appear alongside older woods.")),
    ("A CHANGING", "LANDSCAPE",
     ("Both kinds of woodland area", "shown together — not over time.")),
    ("COULD WOODS", "RECONNECT?",
     ("Some projects are near ancient woods.", "Nearness is not a wildlife corridor.")),
)


def geographic_transform(view):
    """Convert EPSG:27700 metres into exact, aspect-preserving screen pixels."""
    xmin, ymin, xmax, ymax = view.bounds
    left, top, right, bottom = MAP_RECT
    centre_x, centre_y = (xmin+xmax)/2, (ymin+ymax)/2
    scale = min((right-left) / ((xmax-xmin)*1.09),
                (bottom-top) / ((ymax-ymin)*1.09))
    cx, cy = (left+right)/2, (top+bottom)/2
    return lambda x,y: (int(round(cx+(x-centre_x)*scale)),
                        int(round(cy-(y-centre_y)*scale)))


def clipped_geometries(geometries, view):
    """Do not draw features from outside the selected geographic window."""
    for g in geometries:
        if g is None or g.is_empty or not g.intersects(view):
            continue
        cropped = g.intersection(view)
        if cropped.geom_type == "Polygon":
            yield cropped
        elif cropped.geom_type == "MultiPolygon":
            for p in cropped.geoms:
                yield p
        elif cropped.geom_type == "GeometryCollection":
            for part in cropped.geoms:
                if part.geom_type == "Polygon":
                    yield part
                elif part.geom_type == "MultiPolygon":
                    yield from part.geoms


def polygon_overlay(geometries, xy, colour, view, *, min_symbol_px=4):
    """Draw true boundaries and emphasise subpixel patches at their actual sites."""
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0,0,0,0))
    draw = ImageDraw.Draw(canvas)
    symbols = 0
    for polygon in clipped_geometries(geometries, view):
        pts = [xy(x,y) for x,y in polygon.exterior.coords]
        if len(pts) < 3:
            continue
        draw.polygon(pts, fill=colour)
        for hole in polygon.interiors:
            draw.polygon([xy(x,y) for x,y in hole.coords], fill=(0,0,0,0))
        xs = [x for x,_ in pts]
        ys = [y for _,y in pts]
        # A very small genuine polygon may disappear when the 100km+ map is
        # rasterised. Put a dot at an interior point, never shift its location.
        if max(xs)-min(xs) < min_symbol_px or max(ys)-min(ys) < min_symbol_px:
            x,y = xy(*polygon.representative_point().coords[0])
            r = 4 if colour == HISTORIC else 5
            draw.ellipse((x-r-1,y-r-1,x+r+1,y+r+1),
                         fill=(255,255,255,245))
            draw.ellipse((x-r,y-r,x+r,y+r), fill=colour)
            symbols += 1
    return canvas, symbols


def connection_overlay(lines, xy, view):
    canvas=Image.new("RGBA",(WIDTH,HEIGHT),(0,0,0,0))
    draw=ImageDraw.Draw(canvas)
    included=0
    for line in lines:
        if not line.intersects(view):
            continue
        clipped=line.intersection(view)
        if clipped.geom_type!="LineString":
            continue
        x0,y0=xy(*clipped.coords[0]); x1,y1=xy(*clipped.coords[-1])
        for t in np.arange(0,1,.16):
            t2=min(1,t+.09)
            draw.line((int(x0+(x1-x0)*t),int(y0+(y1-y0)*t),
                       int(x0+(x1-x0)*t2),int(y0+(y1-y0)*t2)),
                      fill=CONNECTION,width=5)
        included += 1
    return canvas, included


def background(view, xy, *, actual_region=None):
    canvas=Image.new("RGBA",(WIDTH,HEIGHT),PAPER_RGB+(255,))
    draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((38,430,1042,1475),radius=30,
                           fill=(250,251,247),outline=(225,229,218),width=2)
    # Clip the *real* regional boundary. Don't draw the cut edge of an inset
    # rectangle as though it were the edge of County Durham or Tees Valley.
    actual = actual_region if actual_region is not None else view
    border = actual.boundary.intersection(view)
    def draw_real_lines(geom):
        if geom.is_empty:
            return
        if geom.geom_type == "LineString":
            if len(geom.coords)>1:
                draw.line([xy(x,y) for x,y in geom.coords],
                          fill=(159,175,162),width=4,joint="curve")
        elif hasattr(geom, "geoms"):
            for part in geom.geoms:
                draw_real_lines(part)
    draw_real_lines(border)
    return canvas


def _copy_faded(canvas, overlay, amount):
    if amount <= 0:
        return canvas
    opacity = max(0,min(1,amount))
    copied=overlay.copy()
    copied.putalpha(overlay.getchannel("A").point(lambda a:int(a*opacity)))
    return Image.alpha_composite(canvas,copied)


def labels(canvas, *, scene, area, counts, symbols, nearby):
    draw=ImageDraw.Draw(canvas)
    old_count,new_count=counts
    heading_a,heading_b,description=SCENES[scene]
    draw.text((60,45),"30 DAY MAPS   /   DAY 03: POLYGONS",
              font=font(26,bold=True), fill=(47,107,83))
    draw.text((60,113),heading_a,font=font(65,bold=True),fill=INK)
    draw.text((60,190),heading_b,font=font(61,bold=True),fill=INK)
    for i,part in enumerate(description):
        draw.text((60,292+i*44),part,font=font(32),fill=GREY)
    draw.rounded_rectangle((855,47,1020,107),radius=25,
                           fill=(226,236,225))
    draw.text((895,60),f"{scene+1:02d} / 04",
              font=font(26,bold=True),fill=(47,107,83))
    draw.text((62,402),area.upper(),font=font(27,bold=True),
              fill=(75,106,90))
    # Accessible, large legend. Same content every frame for visual stability.
    draw.rounded_rectangle((40,1500,1040,1860),radius=30,
                           fill=SOFT)
    for y,colour,title,detail in (
        (1540,HISTORIC,"Ancient woodland",f"{old_count:,} mapped patches"),
        (1635,RETURNING,"Woodland project areas",f"{new_count:,} polygon parts"),
        (1730,CONNECTION,"Nearby places",f"{nearby} illustrative pairs, not corridors"),
    ):
        draw.rounded_rectangle((65,y+10,95,y+40),radius=7,fill=colour)
        draw.text((119,y),title,font=font(34,bold=True),fill=INK)
        draw.text((119,y+41),detail,font=font(25),fill=GREY)
    footer=("Small sites marked at real coordinates; dots not to scale."
            if "detail crop" not in area.lower()
            else "Detail crop is not a boundary; site dots are not to scale.")
    draw.text((60,1882),footer,font=font(21),fill=GREY)


def compose(base, old_layer, new_layer, connection_layer, scene, progress,
            *, area, counts, symbols, nearby):
    visible=max(0,min(1,progress/.8))
    output=base.copy()
    output=_copy_faded(output,old_layer,visible if scene==0 else 1)
    if scene>0:
        output=_copy_faded(output,new_layer,visible if scene==1 else 1)
    if scene==3:
        output=_copy_faded(output,connection_layer,visible)
    labels(output,scene=scene,area=area,counts=counts,symbols=symbols,
           nearby=nearby)
    return output.convert("RGB")


def portrait(woods, projects, region, output, *, focus=False,
             fps=12, gif=True):
    """Write a portrait MP4, poster, and optional compressed GIF."""
    view=region.intersection(TEES_VIEW) if focus else region
    if view.is_empty:
        raise ValueError("Tees detail view does not intersect North East")
    area="County Durham & Tees Valley · detail crop" if focus else "North East England"
    suffix="tees-detail" if focus else "north-east"
    name=f"woods-returning-{suffix}-portrait"
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    xy=geographic_transform(view)
    ancient,ancient_dots=polygon_overlay(woods.geometry,xy,HISTORIC,view)
    planting,planting_dots=polygon_overlay(projects.geometry,xy,RETURNING,view)
    local_old = woods.loc[woods.geometry.intersects(view)]
    local_new = projects.loc[projects.geometry.intersects(view)]
    nearby_lines=proximity_lines(local_old,local_new,threshold_m=1500,limit=22)
    connections,nearby=connection_overlay(nearby_lines,xy,view)
    bg=background(view,xy,actual_region=region)
    # Count source features, not fragments produced by clipping a multipolygon.
    old_count=len(local_old)
    new_count=len(local_new)
    counts=(old_count,new_count)
    parts=(bg,ancient,planting,connections)
    poster=output/f"{name}-poster.png"
    compose(*parts,3,1,area=area,counts=counts,
            symbols=(ancient_dots,planting_dots),nearby=nearby).save(poster)
    video_path=output/f"{name}.mp4"
    frame_count=int(3.25*fps)
    gif_frames=[]
    with imageio.get_writer(video_path,format="FFMPEG",fps=fps,codec="libx264",
                            macro_block_size=2,quality=7,
                            output_params=["-pix_fmt","yuv420p"]) as writer:
        for scene in range(4):
            for f in range(frame_count):
                canvas=compose(*parts,scene,f/fps,area=area,counts=counts,
                               symbols=(ancient_dots,planting_dots),nearby=nearby)
                writer.append_data(np.asarray(canvas))
                if gif and f % 3 == 0:
                    gif_frames.append(canvas.resize((540,960),Image.Resampling.LANCZOS))
    if gif:
        gif_frames[0].save(output/f"{name}.gif",format="GIF",
                           save_all=True,append_images=gif_frames[1:],
                           duration=int(3000/fps),loop=0,optimize=True)
    details={
        "area":area,
        "format":"1080x1920, 9:16 portrait",
        "is_time_series":False,
        "project_boundaries_are_confirmed_tree_cover":False,
        "dots_are_to_scale":False,
        "small_ancient_site_symbols":ancient_dots,
        "small_project_site_symbols":planting_dots,
        "ancient_polygon_parts_visible":old_count,
        "project_polygon_parts_visible":new_count,
        "nearby_illustrative_pairs":nearby,
        "scene_order":["ancient","new project polygons","combined","nearby"],
        "provenance":"Natural England, Scottish Forestry Woodland Carbon Code, ONS region boundaries",
    }
    (output/f"{name}-manifest.json").write_text(json.dumps(details,indent=2))
    print(f"Created {video_path} and {poster}",flush=True)
    return video_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ancient",type=Path,required=True)
    parser.add_argument("--projects",type=Path,required=True)
    parser.add_argument("--boundaries",type=Path)
    parser.add_argument("--output",type=Path,
                        default=Path("challenges/03-polygons/outputs/motion"))
    parser.add_argument("--no-gif",action="store_true")
    parser.add_argument("--no-detail",action="store_true")
    args=parser.parse_args()
    woods,projects,region=prepare(args.ancient,args.projects,args.boundaries)
    portrait(woods,projects,region,args.output,gif=not args.no_gif)
    if not args.no_detail:
        portrait(woods,projects,region,args.output,focus=True,gif=False)


if __name__=="__main__":
    main()
