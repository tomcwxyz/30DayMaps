# Day 04 — Clusters: Where the sky gathers

**Question:** where are publicly documented starling murmuration sites, and what can clustering reveal about the *locations in our small published example set*?

A mobile-first interactive map and an animated, explicitly simulated flock. The published map is **not** a density map of birds, a live roost finder, a complete UK census or a forecast of the next murmuration.

## Open it

From the repository root:

```bash
python -m http.server 8000
# Visit http://localhost:8000/web/day04/
```

Requires internet for the [Leaflet](https://leafletjs.com/) library, [CARTO](https://carto.com/) basemap tiles and fonts. The site data and behaviour otherwise run without an API key, bundler, account, framework or backend.

## How it works

- `web/day04/roosts.js` — 21 published example locations, with **indicative coordinates at named publicly accessible sites**; source and conservation links.
- `web/day04/clusters.js` — independently testable great-circle distance and connected-components proximity clustering.
- `web/day04/map.js` — source-linked Leaflet markers, geographical grouping, and accessible pop-ups.
- `web/day04/flock.js` — original, **simulated** starling-like agents using neighbour separation, alignment, cohesion and gradual roost attraction. The animated paths are not field measurements.
- `web/day04/main.js` — filters, radius, canvas controls, replay, time slider and source cards.
- `web/day04/style.css` — responsive layout; supports small screens and respects reduced-motion settings.

The cluster distance slider controls a **graph connectivity threshold** (kilometres). A group may contain sites farther apart than the threshold where they are linked through intermediate sites. Counts are the number of listed *places* in a group, never the number of birds or sightings.

### Sources and limitations

Named public sites were taken from:

1. [Woodland Trust — Starling murmurations](https://www.woodlandtrust.org.uk/blog/starling-murmurations/).
2. [Natural History Museum — How to spot a murmuration](https://www.nhm.ac.uk/discover/spot-a-starling-murmuration-this-winter.html).
3. [RSPB — The starling roost at Ham Wall](https://www.rspb.org.uk/days-out/reserves/ham-wall/the-starling-roost).
4. [ITV News — Wildlife Trust places to watch](https://www.itv.com/news/2025-12-04/why-do-starlings-make-murmurations-in-the-winter).

**Provenance note:** these are hand-curated examples from editorial reserve and birdwatching guides, not individual sighting records. Their site-centre coordinates are approximate, not verified active roosts. Precise and sensitive sites are intentionally not included, and some reserves ask not to be advertised. We do not extract the crowdsourced [Starlings in the UK roost map](https://www.starlingsintheuk.co.uk/roost-map.html) without permission. We cannot draw evidence-backed UK-wide heatmaps or starling-population conclusions from this sparse, non-random selection. Nor is the presence of a named site evidence that birds will be there tonight. The date of an original source report is not an activity timestamp.

To turn this into a statistically meaningful temporal hotspot map, collect licensed records of **actual roost observations with dates, provenance and sampling effort**, then validate bias, access policy and attribution before drawing density or trends. Generic GBIF/eBird starling *occurrences* are not interchangeable with roost records.

### Conservation

Four practical, source-linked actions: [RSPB starling nest box guide](https://www.rspb.org.uk/helping-nature/what-you-can-do/activities/create-a-cosy-starling-home), [RSPB species profile and feeding advice](https://www.rspb.org.uk/birds-and-wildlife/starling), [RSPB neighbourhood nest boxes](https://www.rspb.org.uk/helping-nature/what-you-can-do/activities/give-birds-a-place-to-call-home) and [Starlings in the UK ethical roost guide](https://www.starlingsintheuk.co.uk/roost-map.html).

## Test

```bash
node --test tests/day04.test.mjs
node --check web/day04/main.js
node --check web/day04/flock.js
```

The simulation is an illustration rather than a biological or physical model. The map is a geographic visualisation rather than a recreated photograph.
