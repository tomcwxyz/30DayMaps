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
2. Choose **All moss records** to see every 10 km square containing at least one of the eight chosen species, regardless of clustering. Alternatively select **All 8 recorded together** to see all squares where all eight were recorded, plus connected-cluster outlines. Bog, woodland-associated, grassland-associated and stone-and-wall groupings remain separate cluster views.
3. Keep only squares meeting a minimum number of different selected species and a minimum sum of observations from those species.
4. Connect qualifying squares using **eight-neighbour (queen) adjacency**, sharing an edge or a corner. British and Irish National Grid coordinates are treated as separate coordinate systems, so they cannot connect accidentally.
5. Retain connected components with at least three cells. Excluded, isolated cells are still represented in the optional original-data grid.
6. Dissolve squares in their native projected coordinates, round edges subtly with a 1.2 km positive and negative buffer, simplify by 450 m and convert to WGS84 for Leaflet.

The **All moss records** overview is deliberately a colour-coded grid map: it must show every observed square, including isolated ones. It can colour by (a) the species with the most observation records in a square (eight distinct colours), or (b) the number of different species recorded (a sequential scale from 1 to 8). It does **not** colour exclusively occupied patches: other species may also occur in a square. Counts reflect recording effort, not ecological dominance.

The **All 8 recorded together** view is a strict co-occurrence comparison. Its 197 qualifying squares each contain records of all eight species; 130 of those form 20 clusters of at least three neighbours and the remaining 67 appear as individual pale-gold squares. It always uses the `all-focus` profile (8 of 8, without an observation-count cut-off); we do not offer a misleading 7-of-8 "broader" setting under this label.

The **habitat group** views are true **spatial connected-component clusters**, not choropleths, heatmaps, or statistically significant hotspots. The outlines are graphical footprints of selected recording squares, **not areas covered by moss**.

### Reproducible thresholds

Each tuple below is (minimum distinct species in each square, minimum records of those species). At least three neighbouring squares must be connected.

| Group | Broader | Focused (default) | Strongest |
|---|---|---|---|
| All eight *cluster calculation* (historic profiles) | (7, 120) | (8, 0) | (8, 100) |
| Bog mosses (two Sphagnum species) | (2, 0) | (2, 5) | (2, 10) |
| Woodland-associated (two species) | (2, 40) | (2, 60) | (2, 80) |
| Grassland-associated (one species) | (1, 25) | (1, 40) | (1, 50) |
| Stone and wall species (three) | (3, 45) | (3, 60) | (3, 80) |

These thresholds were explored against the 3 November 2026 NBN source snapshot. The interface deliberately fixes the all-eight comparison to (8, 0), while its larger connected components remain available for inspection. Simply connecting every square containing any moss would create one enormous cluster containing more than 2,500 grid squares. We instead explore stronger co-recorded concentrations. The thresholds are editorial and explanatory, **not validated ecological abundance cut-offs**.

## Interpreting an uncoloured area

**This is a map of where records gather into thresholded clusters, not a map of where moss exists.** In the default **Stone & walls → Focused** profile, a qualifying grid square needs records of all three selected species **and at least 60 combined observation records**, with at least three qualifying neighbouring 10 km squares needed for a visible cluster. Thus, an area can have many verified sightings and still appear blank.

The optional **Reveal recorded squares outside clusters** layer draws muted 10 km evidence squares containing *any* species in the selected habitat-associated group, even when they do not meet the concentration threshold. The viewer shows both the number of source squares with sightings and the number contained in visible clusters. These are different quantities; neither is moss extent or abundance.

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

An all-records colour-coded overview with a full eight-species key and richness toggle, a strict all-eight-recorded view including isolated cells, habitat-group buttons, three concentration levels for habitat clusters, zoomable clickable cluster polygons, ranked gatherings, cluster summaries and an optional click-through source grid. Responsive layout for desktop and mobile. No new Vercel project or service required.

Offline tests in tests/test_moss_clusters.py cover the grid conversion, diagonal links, separation of grid projections, thresholds, output geometry and minimum cluster size. GitHub Actions also validates the live NBN retrieval and the real derived files, then commits both source and clusters on main.
