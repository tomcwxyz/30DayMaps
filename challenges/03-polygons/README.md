# Day 03 — Polygons: The Woods That Remember

**Question:** what do historic woodland fragments look like across Great Britain, and how far apart are mapped ancient woodland patches in the North East?

This maps actual woodland polygons, not a reconstruction of all woodland that existed in 1600.

## Open national inventories

- England: [Natural England Ancient Woodland (England)](https://www.data.gov.uk/dataset/9461f463-c363-4309-ae77-fdcd7e9df7d3/ancient-woodland-england), the baseline version.
- Scotland: [NatureScot Ancient Woodland Inventory](https://www.data.gov.uk/dataset/c2f57ed9-5601-4864-af5f-a6e73e977f54/ancient-woodland-inventory-scotland1), using historic Roy and Ordnance Survey maps.
- Wales: [NRW Ancient Woodland Inventory (2021, updated 2026)](https://datamap.gov.wales/layers/inspire-nrw:NRW_ANCIENT_WOODLAND_INVENTORY_2021), accessed by paginated WFS.
- Northern Ireland: [Woodland Trust Ancient and Long-established Woodland Inventory](https://ati.woodlandtrust.org.uk/back-on-the-map); **not included** while publication and reuse permissions are unresolved. Contact gis@woodlandtrust.org.uk.

The inventories have different survey dates, site definitions, minimum size thresholds, and revision cycles. Do not treat raw polygon counts as directly comparable national woodland abundance.

## Running

Install the existing project dependencies, then run the tests:

    python -m pip install -e '.[test]'
    python -m pytest -q tests/test_woods.py tests/test_woods_wales.py

Download England and Scotland official publisher archives:

    python -m maps.woods --download

Download and validate the Welsh NRW WFS separately:

    python -m maps.woods_wales --output data/raw/wales-ancient-woodland.geojson

Or use local official GeoPackages, zipped GeoPackages and GeoJSONs:

    python -m maps.woods --england data/raw/england-ancient-woodland.gpkg.zip --scotland data/raw/scotland-ancient-woodland.gpkg.zip --wales data/raw/wales-ancient-woodland.geojson

The GitHub Actions workflow in .github/workflows/render-woods.yml handles downloads, rendering and artifacts.

## Maps and data

- **Great Britain** map (only created when all three nations were loaded).
- **England** overview using the baseline inventory.
- **North East England** detail map from the official ONS 2025 region, including Tees Valley.
- North East GeoPackage and a fragmentation CSV, with polygon area (ha) and edge-to-edge distance to the nearest other **North East** polygon (metres).
- Per-nation polygon counts, area and median polygon size.
- Source manifest declaring actual coverage, including that Northern Ireland and English revised counties are not yet included.

### Revisions

Natural England's [revised inventory](https://www.data.gov.uk/dataset/12b72196-1f20-44a9-8fe0-0e78db46a67c/ancient-woodland-revised-england-completed-counties) takes precedence for completed counties. The code supports reconciliation using explicit completed-county coverage boundaries. **Do not** simply append revised polygons or erase old polygons only where they overlap: both methods give misleading results. The CLI intentionally sticks to the documented baseline until the official completed-county geography is integrated.

### Interpretation

A polygon is a mapped site boundary, not necessarily a biologically independent woodland or the full extent of historic woods. Fragmentation is a simple separation measure; it is not ecological connectivity. Maps at country scale render tiny areas smaller than the printed pixel size.

## Attribution

Natural England and Ordnance Survey data © Crown copyright and database rights, OS AC0000851168. Copyright NatureScot; contains Ordnance Survey data © Crown copyright and database right. Contains Natural Resources Wales information © NRW and database right; contains OS data, OS licence AC0000849444. Check each publisher's current attribution and licence notices before reuse.
