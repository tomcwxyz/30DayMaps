# Peaks print maker

Prints of real mountains, or of your own route, in five styles: **poster** (contours with a skyline or route profile underneath), **contours**, **ridgelines**, **skyline** and **panorama**. Names and heights on or off, seven colour schemes, title and subtitle, paper sizes from A4 to A1 plus panoramic sheets, and PNG or SVG downloads.

Everything runs in the browser. Elevation comes straight from the Mapzen/Tilezen Terrarium tiles on AWS Open Data and is cleaned the same way as `maps/peaks.py`; summit names come from OpenStreetMap through Overpass (bundled for the ready-made mountains); search uses Nominatim. A GPX file is read on the device and never uploaded.

- `index.html`: the page and controls
- `lib/terrain.js`: tiles to a local metre grid, repairs, blur, sampling, summit names
- `lib/draw.js`: styles and layout, as a list of items in millimetres
- `lib/render.js`: paints that list to canvas (preview, PNG) or SVG (fonts embedded)
- `places.json`: ready-made mountains, written by `python -m maps.peaks web` from `maps/peak_places.json`
- `test/harness.py`: drives the page in Chromium. `suite OUT` runs offline with stand-in tiles built from `peaks/dem`; `live OUT` uses the real services. The **Peaks web check** workflow runs `live` on every change and commits screenshots to `peaks/web-shots`.

Serve the folder with any static server (`python -m http.server -d web/peaks`). `?place=cuillin&style=panorama` opens a ready-made mountain in a style; `?tiles=` points the page at another Terrarium tile server.
