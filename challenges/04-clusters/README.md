# Day 04 — Clusters: A Rolling Stone Gathers No Moss

**But where does Britain's moss gather?** An interactive cluster map of eight selected moss species based on open-licence 10 km observation grids from the [NBN Atlas](https://nbnatlas.org/).

## Run the real map

    python -m pip install -e '.[test]'
    python -m pytest -q tests/test_moss.py tests/test_moss_clusters.py
    python -m maps.moss
    python -m maps.moss_clusters
    python -m http.server 8000

Open http://localhost:8000/web/moss/. The web viewer is split into index.html, app.js and style.css. The NBN snapshot and precomputed cluster files live in web/moss/ and are committed to the repository by the successful GitHub Actions main-branch run. The map does not use placeholder or generated observation data.

## What is a cluster here?

1. Start with NBN's open-licence, 10 km-square records, not exact species locations.
2. Select a moss group (all eight, bog, woodland-associated, grassland-associated, stone and walls).
3. Keep only squares meeting a minimum number of different selected species and a minimum sum of observations from those species.
4. Connect qualifying squares using **eight-neighbour (queen) adjacency**, sharing an edge or a corner. British and Irish National Grid coordinates are treated as separate coordinate systems, so they cannot connect accidentally.
5. Retain connected components with at least three cells. Excluded, isolated cells are still represented in the optional original-data grid.
6. Dissolve squares in their native projected coordinates, round edges subtly with a 1.2 km positive and negative buffer, simplify by 450 m and convert to WGS84 for Leaflet.

These are **spatial connected-component clusters**, not a choropleth, heatmap, or a statistically significant hotspot analysis. The outlines are graphical footprints of selected recording squares, **not areas covered by moss**.

### Reproducible thresholds

Each tuple below is (minimum distinct species in each square, minimum records of those species). At least three neighbouring squares must be connected.

| Group | Broader | Focused (default) | Strongest |
|---|---|---|---|
| All eight species | (7, 120) | (8, 0) | (8, 100) |
| Bog mosses (two Sphagnum species) | (2, 0) | (2, 5) | (2, 10) |
| Woodland-associated (two species) | (2, 40) | (2, 60) | (2, 80) |
| Grassland-associated (one species) | (1, 25) | (1, 40) | (1, 50) |
| Stone and wall species (three) | (3, 45) | (3, 60) | (3, 80) |

These thresholds were explored against the 3 November 2026 NBN source snapshot. Simply connecting every square containing any moss would create one enormous cluster containing more than 2,500 grid squares. We instead explore stronger co-recorded concentrations. The thresholds are editorial and explanatory, **not validated ecological abundance cut-offs**.

## Provenance and limitations

- Source retrieval and licence filtering: maps/moss.py; 10 km source observations: web/moss/moss.geojson.
- Cluster computation and geometry: maps/moss_clusters.py; derived output: web/moss/moss-clusters.geojson.
- NBN contributor and licence manifest: web/moss/moss-manifest.json. The NBN records used have CC0, CC-BY or OGL licences, with contributor attribution.
- Cluster profiles and source date: web/moss/moss-clusters-manifest.json.
- The source grid can be shown and clicked on the live map. This makes the soft, organic-looking cluster boundaries fully inspectable.
- Selected mosses are illustrative. Labels like woodland, bog and stone refer to associations, not a classification of each grid square's actual habitat.
- Reporting reflects recording effort, licensing and survey patterns. **Record counts are not abundance, biomass or moss cover.** Gaps may mean no recording, not ecological absence. Northern Ireland is included only where source records exist.
- Rounded boundaries are cartographic. They may overlap unsuitable habitats, developed land or sea, and are not modelled moss growth.

## Map features and quality checks

Species-group buttons, three concentration levels, zoomable clickable cluster polygons, ranked gatherings, cluster summaries and an optional click-through source grid. Responsive layout for desktop and mobile. No new Vercel project or service required.

Offline tests in tests/test_moss_clusters.py cover the grid conversion, diagonal links, separation of grid projections, thresholds, output geometry and minimum cluster size. GitHub Actions also validates the live NBN retrieval and the real derived files, then commits both source and clusters on main.
