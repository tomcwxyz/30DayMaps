# Footprints print maker

Any place drawn as buildings and nothing else, sized for print or the web, with your own title and words. Three ways to run it.

## 1. Web page

`web/footprints/index.html` is a single page with no build step. Search a place (or pick an example), edit the words, choose paper and colours, press **Draw buildings**, then download:

- **PNG**: web size (2000 px long edge), or 150/300 dpi for print. Phones may refuse very large images; use 150 dpi or the SVG.
- **SVG**: vector, prints sharp at any size. It names the Archivo font; a printer without it substitutes a similar sans.

It uses OpenStreetMap everywhere (buildings from OpenFreeMap's OpenMapTiles vector tiles, search from Nominatim), so it works worldwide but differs a little from the OS-based prints. Prints made from it carry the credit "Data from OpenStreetMap · © OpenMapTiles · OpenFreeMap". Open it locally by double-clicking the file, or host it (GitHub Pages serves it at `/web/footprints/`).

### Ready-made cities and the place cache

Picking a place loads its buildings from the quickest source available:

1. **Ready-made cities.** The gallery on the page lists the cities in `web/footprints/cities/cities.json` (London, Newcastle, Edinburgh, Paris, Amsterdam, Venice, Barcelona, Rome, Munich, Berlin, Copenhagen, New York, Sydney and Tokyo to start with). Each is one small file (0.2–2.2 MB), so it opens in about a second, with a thumbnail. Any width up to the city's `width_km` uses it; wider maps load from tiles.
2. **The place cache.** Once someone draws a new place, the server builds the same kind of file for it and keeps it in Vercel Blob, so the next person who picks somewhere within about 200 m, at the same width or narrower, gets it straight away. The server builds these itself from the tiles; it never stores anything a browser sends, so nobody can plant a fake map.
3. **OpenFreeMap tiles**, as before, for everything else.

To add or change cities, edit `cities.json` and commit. The **Prepare footprint cities** workflow rebuilds the files and thumbnails and commits them to the same branch. Run it by hand (Actions → Prepare footprint cities) now and then to pick up new OpenStreetMap mapping.

To switch on the place cache, connect a Blob store to the Vercel project (Storage → Create → Blob → connect to `30daymaps-footprints`). Vercel then sets `BLOB_READ_WRITE_TOKEN` and the cache starts working on the next deploy. Without it the page simply loads tiles. Each cached place takes 0.1–2 MB; Blob's free allowance holds several hundred.

The shared code for all three lives in `web/footprints/lib/footprints-data.js` (tile reading and the file format), `web/footprints/api/pack.js` (the cache) and `web/footprints/lib/build-cities.js` (ready-made cities). `maps/footprint_packs.py` reads the files in Python.

## 2. Terminal

    python -m pip install -e .
    python -m maps.prints --list
    python -m maps.prints --place york --paper A3
    python -m maps.prints --place barcelona --paper square --theme night --width-km 4 --subtitle "The Eixample grid"
    python -m maps.prints --lat 54.9745 --lon -1.5975 --name "Ouseburn" --width-km 2 \
        --title "The Ouseburn" --subtitle "Every building in the valley" --kicker "Newcastle"

Options: `--paper` A4, A3, A2, A1, 50x70, square · `--landscape` · `--width-km` ground width shown · `--theme` paper, night, blue, ink (or `--ink` and `--background` hex colours) · `--title`, `--subtitle`, `--kicker`, `--note` · `--dpi` (default 300) · `--formats` any of print, web, pdf · `--source` auto, os, osm.

Output goes to `prints/<place>/` (not committed): a 300 dpi PNG, a web PNG, and a vector PDF.

**Data**: in Great Britain it uses OS OpenMap – Local, downloading the 100 km tiles it needs (about 70 MB each, cached in `data/raw/`). Elsewhere, or with `--source osm`, it uses OpenStreetMap buildings from OpenFreeMap's vector tiles (the same ones the web page uses). Each print carries the right credit line automatically. Preset places live in `maps/print_places.json`; add your own there.

## 3. GitHub

Actions → **Footprints print maker** → **Run workflow**, fill in the form (place or lat/lon, title, subtitle, paper, theme…), and download the result from the run's artifacts. The button appears once the workflow is on the default branch.
