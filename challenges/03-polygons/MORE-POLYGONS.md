# Day 03 — four more polygon maps

Four smaller questions alongside the woodland piece. Each runs on its own and writes to `challenges/03-polygons/outputs/<map>/` (ignored by Git). `.github/workflows/render-day03-extras.yml` downloads, renders and uploads each as an artifact.

    python -m pip install -e '.[test]'
    python -m pytest -q tests/test_polygon_extras.py
    python -m maps.land_parcels
    python -m maps.access_land
    python -m maps.watersheds
    python -m maps.footprints

## 1. How few parcels cover Northumberland?

`maps/land_parcels.py` · [HM Land Registry INSPIRE Index Polygons](https://use-land-property-data.service.gov.uk/datasets/inspire), Northumberland file, plus the ONS December 2025 county boundary.

Ranks every index polygon by area and asks how many it takes to cover half the registered land. Map bands the largest 1%, next 9% and the rest; an inset shows the cumulative curve.

**What it can't tell you:** who owns anything. Index polygons show registered freehold extents, with no owner names. One owner can hold many polygons; one title can have several. Unregistered land is blank. The published Northumberland file carries an internal timestamp of March 2023, which is printed on the map. The download service needs a cookie-keeping client, so the code uses a session.

Attribution (required by HM Land Registry): *This information is subject to Crown copyright and database rights [year] and is reproduced with the permission of HM Land Registry. The polygons (including the associated geometry, namely x, y co-ordinates) are subject to Crown copyright and database rights [year] Ordnance Survey AC0000851063.*

## 2. Right to roam, and the gaps

`maps/access_land.py` · Natural England's [CRoW Act 2000 Access Layer](https://ckan.publishing.service.gov.uk/dataset/crow-act-2000-access-layer2) for the North East region (ONS 2025, including Tees Valley).

Access land in two greens (open country or common land; dedicated-only land, mostly forestry such as Kielder). Everything else is shaded by straight-line distance to the nearest access land, measured on a 100 m grid and including access land up to 15 km over the regional border.

**What it can't tell you:** public rights of way, the England Coast Path margin and permissive access aren't in this layer, so "far from access land" is not "no access". Distances are not walking distances.

© Natural England copyright. Contains Ordnance Survey data © Crown copyright and database right. OGL v3.0.

## 3. Which sea gets your rain?

`maps/watersheds.py` · Environment Agency WFD River Water Body Catchments Cycle 3, read from [The Rivers Trust's ArcGIS copy](https://services3.arcgis.com/Bb8lfThdhugyc4G3/ArcGIS/rest/services/England_WFD_River_Water_Body_Catchments_Cycle_3/FeatureServer) (OGL, © Environment Agency).

Northern England's catchments coloured by the sea they reach. Classification is an explicit lookup: Northumbria and Humber river basin districts drain to the North Sea, North West to the Irish Sea, and Solway Tweed is split by management catchment (Tweed and Till east; Eden and Esk, Waver and Wampool west). Any new catchment name stops the run rather than being guessed. The heavy line is the shared edge between the two drainage areas.

**What it can't tell you:** the catchments stop at the Scottish border, and the watershed is only as precise as the catchment boundaries.

## 4. Footprints only

`maps/footprints.py` · [OS OpenMap – Local](https://www.ordnancesurvey.co.uk/products/os-open-map-local), NZ tile, buildings layer.

A 9 × 11 km poster of Newcastle and Gateshead in building outlines alone, and a sheet of three 1.4 km squares: the Byker Wall, Heaton's Tyneside flats and Bensham's terraces.

**What it can't tell you:** OpenMap – Local generalises buildings, so terraces often read as single long blocks.

Contains OS data © Crown copyright and database right 2026. OGL v3.0.
