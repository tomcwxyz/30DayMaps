# Footprints print maker

Any place drawn as buildings and nothing else, sized for print or the web, with your own title and words. Three ways to run it.

## 1. Web page

`web/footprints/index.html` is a single page with no build step. Search a place (or pick an example), edit the words, choose paper and colours, press **Draw buildings**, then download:

- **PNG**: web size (2000 px long edge), or 150/300 dpi for print. Phones may refuse very large images; use 150 dpi or the SVG.
- **SVG**: vector, prints sharp at any size. It names the Archivo font; a printer without it substitutes a similar sans.

It uses OpenStreetMap everywhere (buildings from OpenFreeMap's OpenMapTiles vector tiles, search from Nominatim), so it works worldwide but differs a little from the OS-based prints. Prints made from it carry the credit "Data from OpenStreetMap · © OpenMapTiles · OpenFreeMap". Open it locally by double-clicking the file, or host it (GitHub Pages serves it at `/web/footprints/`).

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
