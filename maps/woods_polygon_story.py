"""Day 03: three-chapter *polygon* film across Great Britain, North East and Tees.

All mapped woodland features are actual source polygon geometries transformed
to screen coordinates. No centroid markers, enlarged dots, fake boundaries or
AI-drawn geography. Small sites can become subpixels at national scale; the
story zooms in specifically so viewers can finally see their true shapes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from maps.woods import combine_inventories
from maps.woods_motion import read_projects
from maps.common import NORTH_EAST_CODE, regions
from maps.woods_motion import font

WIDTH, HEIGHT = 1080, 1920
MAP_RECT = (44, 391, 1036, 1492)
PAPER = (247, 247, 240)
MAP_BG = (252, 252, 248)
INK = (24, 50, 44)
MUTED = (91, 112, 102)
GREEN = (35, 104, 78, 255)
GOLD = (186, 136, 44, 242)
TEES_BOX = box(392000, 505000, 479000, 582000)


def camera(bounds, *, padding=1.07):
    """An aspect-preserving affine transform; metres remain spatially correct."""
    xmin,ymin,xmax,ymax = bounds
    l,t,r,b = MAP_RECT
    span_x=(xmax-xmin)*padding
    span_y=(ymax-ymin)*padding
    scale=min((r-l)/span_x,(b-t)/span_y)
    mid_x=(xmax+xmin)/2; mid_y=(ymax+ymin)/2
    mid_px=(l+r)/2; mid_py=(t+b)/2
    return lambda x,y: (round(mid_px+(x-mid_x)*scale),
                        round(mid_py-(y-mid_y)*scale))


def each_polygon(geometry):
    if geometry is None or geometry.is_empty:
        return
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        yield from geometry.geoms
    elif hasattr(geometry,"geoms"):
        for shape in geometry.geoms:
            yield from each_polygon(shape)


def actual_polygon_layer(geometries, xy, colour, *, width=0, view=None):
    """Rasterise *true* polygons. Never replace small polygons with circles."""
    canvas=Image.new("RGBA",(WIDTH,HEIGHT),(0,0,0,0))
    draw=ImageDraw.Draw(canvas)
    for g in geometries:
        if g is None or g.is_empty:
            continue
        if view is not None:
            if not g.intersects(view):
                continue
            g = g.intersection(view)
        for poly in each_polygon(g):
            if poly.is_empty:
                continue
            path=[xy(x,y) for x,y in poly.exterior.coords]
            if len(path) < 3:
                continue
            draw.polygon(path,fill=colour)
            for hole in poly.interiors:
                draw.polygon([xy(x,y) for x,y in hole.coords],fill=(0,0,0,0))
            # Outline visible shapes only; don't inflate subpixel polygons.
            if width and max(x for x,y in path)-min(x for x,y in path)>=5:
                draw.line(path+[path[0]],fill=colour[:3]+(255,),width=width,
                          joint="curve")
    return canvas


def border_overlay(actual_boundary,view,xy):
    """Draw official region boundary, not the rectangular edge of a crop."""
    canvas=Image.new("RGBA",(WIDTH,HEIGHT),(0,0,0,0))
    draw=ImageDraw.Draw(canvas)
    line=actual_boundary.boundary.intersection(view)
    def draw_lines(g):
        if g.is_empty:
            return
        if g.geom_type=="LineString" and len(g.coords)>1:
            draw.line([xy(x,y) for x,y in g.coords],
                      fill=(148,170,155,220),width=3,joint="curve")
        elif hasattr(g,"geoms"):
            for part in g.geoms:
                draw_lines(part)
    draw_lines(line)
    return canvas


def project_data(projects_path: Path, extent):
    """Normalise and repair publisher-provided WCC project polygons."""
    return read_projects(projects_path, extent)


def choose_local_view(ancient, projects, broad_extent):
    """Pick a genuine WCC/ancient-woodland pairing for the last map close-up."""
    old=ancient.loc[ancient.geometry.intersects(broad_extent)].copy()
    new=projects.loc[projects.geometry.intersects(broad_extent)].copy()
    if old.empty or new.empty:
        raise ValueError("Cannot select a real nearby-woodland detail")
    tree=STRtree(list(old.geometry))
    viable=[]
    for project in new.geometry:
        idx=int(tree.nearest(project))
        old_site=old.geometry.iloc[idx]
        distance=float(project.distance(old_site))
        if distance>3000:
            continue
        p1,p2=nearest_points(project,old_site)
        x=(p1.x+p2.x)/2; y=(p1.y+p2.y)/2
        # Favour sites with appreciable polygon area and a nonzero gap.
        size=min(float(project.area),250000)
        score=size/(1+distance/2000)
        viable.append((score,x,y,distance))
    if not viable:
        raise ValueError("No eligible woodland project near an ancient patch")
    _,x,y,distance=max(viable)
    return box(x-8500,y-8500,x+8500,y+8500), distance


def bg_layer(region,view,xy):
    image=Image.new("RGBA",(WIDTH,HEIGHT),PAPER+(255,))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((35,381,1045,1502),radius=26,
                           fill=MAP_BG,outline=(220,228,218),width=2)
    if region is not None:
        image=Image.alpha_composite(image,border_overlay(region,view,xy))
    return image


def overlay(base,layer,opacity):
    if opacity<=0:
        return base
    alpha=max(0,min(1,opacity))
    copy=layer.copy()
    copy.putalpha(layer.getchannel("A").point(lambda a:round(a*alpha)))
    return Image.alpha_composite(base,copy)


def layout(image, chapter, step, *, region_label, counts, local=False):
    canvas=image.copy()
    draw=ImageDraw.Draw(canvas)
    draw.text((60,42),"30 DAY MAP CHALLENGE  /  03: POLYGONS",
              font=font(26,bold=True),fill=(43,110,82))
    draw.text((60,117),"THE WOODS THAT REMEMBER",
              font=font(49,bold=True),fill=INK)
    draw.text((60,185),"THE WOODS THAT ARE RETURNING",
              font=font(44,bold=True),fill=INK)
    draw.text((60,285),region_label.upper(),
              font=font(30,bold=True),fill=(65,100,80))
    draw.rounded_rectangle((842,43,1034,103),radius=25,fill=(222,233,219))
    draw.text((870,56),f"0{chapter+1} / 03",font=font(27,bold=True),
              fill=(43,110,82))
    draw.rounded_rectangle((38,1530,1042,1880),radius=26,
                           fill=(239,244,234))
    titles=("WHAT SURVIVES","WHAT IS RETURNING","TOGETHER","LOOK CLOSER")
    descriptions=(
       "Actual ancient woodland polygons",
       "Woodland Carbon Code project boundaries",
       "Ancient sites and woodland-creation projects",
       "Real woodland shapes, revealed by zooming",
    )
    draw.text((69,1553),titles[step],font=font(36,bold=True),fill=INK)
    draw.text((69,1615),descriptions[step],font=font(26),fill=MUTED)
    draw.rounded_rectangle((68,1678,92,1702),radius=4,fill=GREEN)
    draw.text((113,1672),"Ancient woodland",font=font(28,bold=True),fill=INK)
    draw.rounded_rectangle((68,1735,92,1759),radius=4,fill=GOLD)
    draw.text((113,1729),"Woodland project area",font=font(28,bold=True),fill=INK)
    label=("Polygon boundaries are real; tiny sites may be invisible."
           if chapter==0 else
           "Project boundaries ≠ confirmed tree cover.")
    draw.text((65,1812),label,font=font(23),fill=MUTED)
    draw.text((58,1901),
              "GB only (not NI) · Not a chronological planting animation",
              font=font(20),fill=(93,113,101))
    if local:
        draw.text((704,345),"17 km detail",font=font(23,bold=True),
                  fill=(70,107,83))
    return canvas.convert("RGB")


def scene_parts(ancient, projects, region, view, *, local=False):
    xy=camera(view.bounds,padding=1.07)
    old=ancient.geometry
    new=projects.geometry
    backdrop=bg_layer(region,view,xy)
    old_layer=actual_polygon_layer(old,xy,GREEN,view=view,width=1 if local else 0)
    new_layer=actual_polygon_layer(new,xy,GOLD,view=view,width=1 if local else 0)
    old_count=int(ancient.geometry.intersects(view).sum())
    new_count=int(projects.geometry.intersects(view).sum())
    return backdrop,old_layer,new_layer,(old_count,new_count)


def frame(parts,chapter,step,progress,label,*,local=False):
    background,ancient,projects,counts=parts
    image=background.copy()
    if step==0:
        image=overlay(image,ancient,min(1,progress/.65))
    else:
        image=overlay(image,ancient,1)
        image=overlay(image,projects,min(1,progress/.65) if step==1 else 1)
    return layout(image,chapter,step,region_label=label,
                  counts=counts,local=local)


def render(ancient,projects,region,output,*,fps=10,gif=True):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    if set(ancient.nation.unique())!={"England","Scotland","Wales"}:
        raise ValueError("Great Britain chapter requires all three nations")
    northeast=regions(Path("data/raw/regions-2025.geojson")).to_crs(27700)
    northeast=northeast.loc[northeast.RGN25CD.eq(NORTH_EAST_CODE)]
    if northeast.empty:
        raise ValueError("North East ONS boundary absent")
    ne_region=northeast.geometry.union_all()
    localview,pair_distance=choose_local_view(ancient,projects,TEES_BOX)
    gb_extent=box(*ancient.total_bounds.buffer(0).bounds) if False else box(*ancient.total_bounds)
    chapters=[
        ("Great Britain",gb_extent,None),
        ("North East England",ne_region,ne_region),
        ("County Durham & Tees Valley",TEES_BOX,ne_region),
    ]
    chapter_frames=[]
    master=output/"woods-returning-three-chapter-master.mp4"
    meta={"chapters":[],"is_chronological":False,
          "woodland_creation_polygon_coverage":"WCC only, validation stage or later",
          "northern_ireland_included":False,
          "symbols_replacing_polygons":False,
          "local_detail_gap_m":round(pair_distance,1)}
    master_writer=imageio.get_writer(master,format="FFMPEG",fps=fps,codec="libx264",
                                     macro_block_size=2,output_params=["-pix_fmt","yuv420p"])
    try:
        for ci,(name,view,boundary) in enumerate(chapters):
            part=scene_parts(ancient,projects,boundary,view)
            actual_old,actual_new=part[3]
            detail=scene_parts(ancient,projects,boundary,localview,local=True) if ci==2 else None
            clip=output/f"woods-returning-0{ci+1}-{['great-britain','north-east','tees-valley'][ci]}.mp4"
            poster=clip.with_suffix(".png")
            first_frames=[]
            with imageio.get_writer(clip,format="FFMPEG",fps=fps,codec="libx264",
                                    macro_block_size=2,output_params=["-pix_fmt","yuv420p"]) as cw:
                for step in range(4):
                    parts=detail if ci==2 and step==3 else part
                    for i in range(round(fps*2.4)):
                        progress=i/fps
                        pic=frame(parts,ci,step,progress,name,local=ci==2 and step==3)
                        if step==3 and i==round(fps*2.4)-1:
                            pic.save(poster)
                        pix=np.asarray(pic)
                        cw.append_data(pix)
                        master_writer.append_data(pix)
                        if gif and ci==2 and i%3==0:
                            first_frames.append(pic.resize((540,960),Image.Resampling.LANCZOS))
            if first_frames:
                first_frames[0].save(output/"woods-returning-tees-polygons.gif",format="GIF",
                                     save_all=True,append_images=first_frames[1:],
                                     duration=300,loop=0,optimize=True)
            meta["chapters"].append({"chapter":ci+1,"name":name,
                                     "ancient_polygon_features":actual_old,
                                     "project_polygon_features":actual_new,
                                     "contains_local_polygon_zoom":ci==2})
            print(f"Rendered {clip} ({actual_old:,} ancient polygons, {actual_new:,} WCC features)",flush=True)
    finally:
        master_writer.close()
    (output/"actual-polygons-manifest.json").write_text(json.dumps(meta,indent=2))
    return master


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--england",type=Path,required=True)
    parser.add_argument("--scotland",type=Path,required=True)
    parser.add_argument("--wales",type=Path,required=True)
    parser.add_argument("--projects",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path("challenges/03-polygons/outputs/real-polygons"))
    parser.add_argument("--no-gif",action="store_true")
    args=parser.parse_args()
    ancient=combine_inventories({"England":args.england,"Scotland":args.scotland,"Wales":args.wales})
    # WCC is a GB inventory; no Northern Ireland or fake planting years.
    project_bound=box(-250000,-120000,750000,1350000)
    projects=project_data(args.projects,project_bound)
    print(f"{len(ancient):,} ancient polygons and {len(projects):,} creation-project parts",flush=True)
    print(render(ancient,projects,None,args.output,gif=not args.no_gif),flush=True)


if __name__=="__main__":
    main()
