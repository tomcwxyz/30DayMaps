# Days 08 and 09 — Utopia / Urban–Rural

Two independent, static-hosted, data-grounded North East maps. Neither requires a server, accounts, a mapping API key, or an AI-generated image.

## Day 08: A wild place within ten minutes
URL after Pages deploy: `/day08-utopia/`

**Real evidence:** Forestry Commission's [Woods for All](https://services2.arcgis.com/mHXjwgl3OARRqqD4/ArcGIS/rest/services/Woods_For_All/FeatureServer/0) vector layer (published 2025). Queries are spatially filtered to the visible map; woodland polygons show the source's exact `access` field: `public access` or `no known public access`. The underlying woodland inventory is mainly from 2022. Data is OGL 3.0.

**Thought experiment:** click any point or select a town. An 800 m radius represents approximate ten-minute *straight-line proximity* at 4.8 km/h; it is explicitly **not** a ten-minute walk or network isochrone. The current estimate measures distance to the nearest mapped publicly accessible woodland polygon. “What if?” highlights the nearest woodland with no known public access (if it is within 2.5 km), and draws a hypothetical, straight-line link. No new access rights, paths or permissions are asserted. The comparison is **not** a population or universal-coverage statistic.

**Limitations:** Forest Commission source contains unverified or out-of-date access information and narrow public-path corridors; a source “public access” field does not guarantee a legal right to enter the whole polygon. Neither terrain, actual entrances, walking-network distance, land ownership, habitat quality nor suitability has been calculated. If a 6,000-polygon query cap is reached, zoom in.

## Day 09: Where does the city end?
URL after Pages deploy: `/day09-urban-rural/`

**Real evidence:** [ESA WorldCover 2021 v200](https://esa-worldcover.org/en/data-access), 10 m pixel-level land-cover classes. A WMS from Terrascope renders the original land-cover classification as a map overlay. The cross-section is calculated separately from a Cloud-Optimised GeoTIFF (COG) covering tile `N54W003`, **not** from an image screenshot.

**Method:** a straight line between Newcastle city centre and Hamsterley Forest, divided into 61 sample points. For each point, a 500 m surrounding circular sample is extracted from the WorldCover classification raster, downsampled to an overview resolution (approximately 60–90 m), and the percentage in each land-cover category is displayed as a stacked section. “Built-up” is WorldCover code 50, trees code 10, cropland 40, and grass/shrubland 20/30. This is not an administrative urban/rural classification or an assessment of where people can go.

**Reliability:** if COG access fails for any reason (service or browser restrictions), the profile displays an explicit unavailability state; there are **no estimated or fabricated percentages**. It is a 2021 landscape snapshot, not a 2026 land-change map.

## Local run / checks
From the repository root:

```bash
node --check web/day08-utopia/geo.js
node --check web/day08-utopia/app.js
node --check web/day09-urban-rural/landcover.js
node --check web/day09-urban-rural/app.js
node --test tests/day08-day09.test.cjs
python -m http.server 8000 --directory web
```

Open `http://localhost:8000/day08-utopia/` and `http://localhost:8000/day09-urban-rural/`.

Map tiles, the Forestry Commission feature service, the ESA WMS and COG, Leaflet and GeoTIFF.js are loaded over HTTPS. **Offline use is not supported.** For publication, the GitHub Pages workflow copies both pages and shared styling to the same site as existing map challenges.

### Attribution
- Day 08: Contains Forestry Commission information licensed under the Open Government Licence v3.0; the Forestry Commission access evidence has its own important caveats.
- Day 09: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium.
- Basemap © OpenStreetMap contributors and CARTO.

### Next improvements
- Day 08: obtain a suitable walking network, entrances and postcode-centred population data to calculate **actual ten-minute walking catchments**, then test candidate links against access, feasibility and habitat criteria.
- Day 09: download and store a smaller, reproducible COG-derived corridor data product in the repository so the cross-section stays available without third-party COG range requests. Optionally overlay official ONS Rural–Urban Classification to demonstrate how administrative classifications differ from land-cover gradients.
