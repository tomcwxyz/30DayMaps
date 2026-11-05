# Day 05 · Sight — What the Mountain Sees

**Status: first interactive 3D terrain implementation committed at [`web/day05-dale-head/`](../../../web/day05-dale-head/); calculated viewshed and live-browser verification still outstanding.**

Run `npm install --no-save leaflet@1.9.4 maplibre-gl@5.9.0`, `node scripts/prepare_day05_vendor.cjs web` once, then `python -m http.server 8000` from the repository root. Open `http://localhost:8000/web/day05-dale-head/`. The local MapLibre bundle avoids relying on a third-party CDN at runtime.

**Implemented:** MapLibre 3D raster-DEM terrain from public AWS/Tilezen Terrarium tiles, low-level summit camera, four directions, relief-exaggeration controls and 3D overview. This *is not* yet a scientifically computed line-of-sight viewshed, nor should the experimental summit camera be represented as a surveyed panorama. The detailed computation plan remains below.

## The question

*What can you actually see from the summit of Dale Head?*

This project reconstructs a **view from the summit** and separately calculates the **terrain viewshed**. It is independent from the 'What's Outside Your Window?' wildlife atlas.

## Grounded start location

Dale Head summit cairn: approximately **54.527271, -3.201936**, height around **753 m**, cited from [Wainwrights.info](https://wainwrights.info/fell.php?id=160). The actual fell top is slightly offset from the tall cairn: retain and clearly describe the viewpoint used when running any analysis. Use a consistent projected coordinate in the terrain calculation. Never assume the chosen observer elevation is equal to the elevation in every data source.

## Experience

1. **From the summit** — a first-person-feeling, rotatable 3D representation of the *real terrain* with a modest, labelled observer height (e.g. ground + 1.7 m).
2. **Across the landscape** — the 2D terrain viewshed map, highlighting land theoretically visible from that point, and hidden ground behind intervening ridges.
3. **On the horizon** — known fells labelled by verified position and height. Only mark a fell as 'visible' when it passes line-of-sight checks.

The two main views must use the same observer location and DEM. The terrain itself must be computed from actual terrain data, not generated imagery.

## Terrain data

- Primary analysis dataset: [OS Terrain 50](https://docs.os.uk/os-downloads/products/land-and-terrain-portfolio/os-terrain-50) (open, 50 m ground-height posts, British National Grid). Appropriate to a wider Lake District landscape, but small ridges and near-field details may be missed.
- Higher-resolution near summit: Environment Agency 1 m/2 m LiDAR **where available**; use actual coverage metadata rather than claiming blanket availability.
- A live 3D base might use MapLibre `raster-dem` with suitable, properly licensed Terrarium or Terrain-RGB tiles, but this is only the **viewer**. Do not claim its GPU relief is a viewshed analysis. If live tiles differ from the analytical DEM, describe that difference visibly.
- Cartographic and analysis output must cite the exact dataset versions and licences, including OS copyright/OGL where appropriate.

## Viewshed method (reproducible)

1. Fetch and mosaic DEM tiles for a declared bounding radius, clip to region and preserve units/projection.
2. Locate observer on DEM and add declared eye height.
3. For each DEM cell in analysis range, trace elevation samples along the line from observer to target, accounting for interpolation and cell spacing; a target is visible only if all intervening terrain falls below the sight line.
4. Optionally account for Earth curvature and atmospheric refraction on longer views, **explicitly state the choice**.
5. Encode visible/hidden as a GeoTIFF plus a visually designed overlay; no-data is different from hidden terrain.
6. Compare a small group of known summit-to-summit rays with a second method or manually inspected topographic profiles.

Use `rasterio`, `numpy`, `pyproj` and optionally `richdem` or another established viewshed tool; do not invent geometry code where proven GIS tools can be used. If using GDAL viewshed, capture the command, observer/target heights, max distance and curvature coefficient. Unit tests should cover blocking ridges, clear sight lines and no-data.

## Composition and interaction

- Opening frame looks north from Dale Head down Newlands Valley, not overhead as though controlling a drone.
- Three simple controls: **Look around**, **See what's visible**, **Name the mountains**.
- A static A3-quality version should be a genuine computed map, paired with a rendered panorama or silhouette and readable labels.
- Mobile: accessible touch rotation and a 2D viewshed fallback for devices unable to render 3D reliably.
- Hide obvious extraneous map controls. Distinguish absolute 3D realism from modest visual exaggeration.

## Done means

- Live viewer uses **real terrain elevation data** and names the provider.
- A real viewshed raster exists and is reproducible with a one-command build from a documented dataset.
- The 3D view, 2D overlay and summit labels share one viewpoint.
- Output metadata includes observer coordinates, observer height, analysis radius, raster resolution, source date and line-of-sight assumptions.
- No fake viewshed, painted green illustration, or generated landscape is presented as a scientific result.
- Generated high-resolution output and working preview are inspected visually before claiming the exercise complete.

## Phasing

**Phase A:** source/DEM check, observer coordinate and first 3D terrain scene.

**Phase B:** genuine viewshed calculation, validation and 2D linked panel.

**Phase C:** summit labels, first-person composition, interaction polish, high-resolution print export.
