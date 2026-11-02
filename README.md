# 30DayMaps

Thirty enjoyable cartographic experiments in November 2026. The aim is to ask good questions using open geographic data, make print-worthy maps, and periodically try mapping tools we haven't used before. Not thirty new applications.

## Day 01 — Points: the pillars that mapped England

The **master geography is England**, including Cumbria and everywhere else visited. The **North East** is a detailed view of the same national data, using the 2025 ONS North East region (including Tees Valley). The top-ten highest and most isolated rankings are **England-wide**. For isolation, neighbouring pillars in Scotland and Wales remain in the comparison set so borders don't create false extremes.

Source: [Ordnance Survey's complete triangulation archive](https://www.ordnancesurvey.co.uk/geodesy-positioning/legacy-data/trig-search) (historic, not maintained). Region boundaries: [ONS Regions December 2025](https://www.data.gov.uk/dataset/c80bd244-e77f-4d29-bd5e-4063f4e58eaf/regions-december-2025-boundaries-en-bgc). Contains OS data © Crown copyright and database right; licensed under OGL v3.0. The archive's 'not recorded as destroyed' does **not** mean verified standing in 2026.

### Run

Requires Python 3.11+ and internet for the first run:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e '.[test]'
python -m pytest -q
python -m maps.trigs
```

The first run downloads the OS archive and ONS boundaries into `data/raw/` (ignored by Git), then writes the following to `challenges/01-points/outputs/`: `england-overview.png`, `england-visited.png`, `england-highest.png`, `england-isolated.png`, `england-lost.png`, `north-east-detail.png`, and accompanying national/regional CSV files. Add `--force` to refresh public datasets. If the OS download is unavailable, download `CompleteTrigArchive.zip` manually from the link above and run `python -m maps.trigs --archive /path/to/CompleteTrigArchive.zip`.

### Personal visited pillars

After the first run, use station IDs from `challenges/01-points/outputs/england-pillars.csv` to create your **private** file `data/private/visited.csv`:

```csv
station_id,visited,date,notes
<replace-with-OS-station-id>,yes,2024-06-01,Visited on a run
```

Remove the example placeholder before running. Keep this personal CSV uncommitted. The visited map is **England-wide**. Grey points mean no visit is *recorded*, not necessarily never visited. GPX matching can come later; proximity to a route is not proof of a visit.

### Output definitions

- **Highest**: ten tallest English pillars by OS archive height, excluding those marked destroyed.
- **Most isolated**: ten English pillars with the greatest *straight-line distance* to another pillar not marked destroyed anywhere in Great Britain. This does not measure footpath or driving access.
- **Lost**: OS archive's destroyed mark flag, not independently checked present-day condition.
- **North East**: a regional inset of national pillars, not a differently filtered source catalogue.

## Loneliest bus stops — England-wide exploration

Use [DfT NaPTAN national CSV](https://beta-naptan.dft.gov.uk/download/national) to explore geographical isolation and later match against active timetables. The official public [CSV endpoint](https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv) can be downloaded automatically:

```bash
python -m maps.buses --output explorations/loneliest-bus-stops/outputs/top100.csv
```

This gives an **England-only geographic candidate ranking** and matching PNG, with cross-border nearest-neighbour comparisons against all GB stops. It filters for active boarding locations (`BCT`, `BCS`, `BCQ`), excludes entrance/access records and the floating hail-and-ride category, then groups platforms within 75 metres that have an identical normalised name (or nearby bays within one station locality). Each group's distance is the shortest straight-line distance to another group's platform; this is **not** walking or public transport travel distance. The output exposes original stop IDs and group sizes for audit. Active NaPTAN *records* do not verify the presence of an operating service. Uncertain local pairs or duplicate stops must be reviewed before sharing a definitive top-100 list.

Planned definitions: (1) furthest from another distinct stop location, (2) furthest from a settlement, and (3) fewest actual scheduled departures. We will present separate rankings rather than an arbitrary composite score.

## Approach

Reusable foundations are minimal: fetching sources, boundary handling, attribution and styling. Individual challenges can switch tools: GeoPandas/Matplotlib first, then MapLibre, QGIS, H3, DuckDB Spatial, 3D, cartograms, animated cartography and unconventional approaches when the question merits it.

Each map should answer a question, credit the data, document its technique, and state what it cannot tell us.