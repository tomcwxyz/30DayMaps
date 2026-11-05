# Day 05 · Sight — What's Outside Your Window?

**Status: published interactive wildlife explorer at [`web/day05-wildlife/`](../../../web/day05-wildlife/), deployed to GitHub Pages. Browser and live GBIF tests exist. The page now starts from the visitor’s browser location, when permitted, rather than a fixed example town.**

Run `npm install --no-save leaflet@1.9.4 maplibre-gl@5.9.0` then `node scripts/prepare_day05_vendor.cjs web` once, followed by `python -m http.server 8000` from the repository root. Open `http://localhost:8000/web/day05-wildlife/`. This copies the open-source map library into a locally hosted vendor directory; it is not a JavaScript framework build. Run the geodesic radius tests with `node --test tests/day05-geo.test.cjs`.

**Implemented:** place search (submit only, via Nominatim), map-point selection, optional browser geolocation, month and radius controls, 2021–2025 baseline plus optional 2026, four GBIF taxon groups, real occurrence-map points with source links, and full-search species facet counts for the leading 25 species. The map shows at most the first 300 returned points (clearly labelled) and lets a user fetch points for a selected species. No predictive probability is claimed. Future work remains in the brief below.

## Location-first behaviour (November 2026)

- On first opening the page, the browser asks for geolocation permission. A successful permission response starts the **first GBIF occurrence query** for the user's approximate position.
- The browser location is rounded to three decimal places before it is used in the circle query. The map does not store this position in cookies, local storage, URLs or a database.
- If the user declines permission, geolocation is unavailable, times out or reports a location outside the map's Britain coverage, the page loads a **clearly labelled example near Newton Aycliffe** and provides manual place search and map-pin selection. It never claims the example is the user's location.
- Manual place search or map-click choices win over a late geolocation callback; no delayed browser permission response can silently move the map somewhere else.
- The map is temporarily centred over Britain, without a fake local radius or record count, until a location is resolved.
- **Provider disclosure:** The GBIF search request contains a polygon around the rounded location, and map-tile providers receive the selected map area. We cannot claim that third-party services don't log requests. Don't include precise home coordinates in shareable links.
- The first load and fallbacks have a Playwright mobile browser regression test using **simulated Edinburgh coordinates**, with no access to a real visitor's position.
- The interface now shows the species field guide before the map on mobile, with a direct map link. The muted, lighter style follows the Day 5 field-notes approach.

## Data and image audit (5 November 2026)

The live source comparison is available from GitHub Actions as **Day 05 GBIF and NBN coverage audit**. Three locations are checked with fixed November 2021–2025 and 5 km filters. GBIF filters to georeferenced records without known geospatial issues; NBN uses its independent public spatial index, with co-ordinate generalisation and licence restrictions. Totals must never be added or presented as equivalent samples.

The initial GBIF audit returned 51 November bird records in the Newton Aycliffe example area, 391 near Keswick and 9,294 near Edinburgh. NBN's documented location, year and month filters were verified; its working bird-class filter is `classs:Aves`. NBN Atlas may expose records under CC-BY-NC terms and may hide or generalise sensitive species locations. We **do not** merge or republish NBN individual records.

The separate NBN bird-class query is now working with `classs:Aves` and month/year/radius filters. The live 5 November audit returned:

| Area, 5 km, November 2021–2025 | GBIF georeferenced birds | NBN Atlas public bird records |
| --- | ---: | ---: |
| Newton Aycliffe | 51 | 328 |
| Edinburgh | 9,294 | 9,078 |
| Keswick | 391 | 809 |

These are **not comparable unique-event totals**: NBN public precision, licence coverage and source datasets differ, so neither number can simply be added to the other. Some of the same sightings may appear in both platforms. The implementation continues to show **GBIF-only** counts and location markers until licensing, source citation, spatial uncertainty and record-level deduplication can be implemented without leaking sensitive locations.

The first photo audit used eight leading species actually returned by the local GBIF query. Six had a photo in the first thirty-two globally indexed multimedia occurrences with an explicitly suitable media licence, compared with four when only the first sixteen results were inspected. The field-guide implementation queries a small, lazy-loaded global sample, checks each media licence independently, and includes the creator, licence and parent GBIF occurrence link. A photo is never described as a local sighting. If the licence is missing, restricted or ambiguous, no photo appears.

## Next priorities

1. Audit additional UK wildlife recording coverage, especially NBN Atlas, against GBIF. Check dataset licences, masking and duplicate occurrence IDs before introducing any second source.
2. Add properly licensed and attributed species photographs, when a source offers them. They must represent the **species**, not falsely imply that a pictured individual was observed locally.
3. Show last-observed dates and account for coordinate uncertainty on the map. Distinguish field-guide record counts from probability, abundance or completeness.
4. Explore a month strip and a print-ready seasonal card once the data quality is improved.

## The question

*What species have people recorded near this place, in this month of the year?*

This is a **seasonal atlas of nearby records**, not a claim to identify animals visible from a real window, predict what a visitor will see, or calculate wildlife abundance. It is an independent Day 05 experiment and must not depend on the Dale Head terrain work.

## Audience experience

1. Start on a map of Britain with a clear example location and an explicit location picker (place search or pin). Browser location is available **only on demand**; never request it automatically.
2. Choose a month, January–December. Default to the current month. This means *observations made in this calendar month across previous years*, not records uploaded this month.
3. Choose a radius (1, 3, 5 or 10 km; default 5 km). Draw the real-radius circle and show the scale.
4. Switch between **Birds** (first complete vertical), **Mammals**, **Butterflies & moths**, and **Plants** (later verticals, independently checked taxonomy).
5. Explore two linked views:
   - **On the map**: original records, with data-quality and sensitive-species location treatment respected.
   - **Field guide**: species recorded within the chosen radius, with common/scientific names, record counts, last observation and an inspect-source link.
6. Select a species to filter the map and display the actual records behind its count. Return to all nearby species.
7. Empty states, loading states and errors must be informative: *no qualifying published records* is **not** *the species is absent*.

## First product (MVP)

- Britain-only location search plus a pin-based alternative; optionally show an example location.
- Birds first. Add other taxa only after verifying taxonomic grouping, coverage and source licence.
- Month and radius selectors, field-guide list, map points, real record count, recent years with observations, last-recorded date.
- **2021–2025** as the initial fixed comparison period; current-year records can be shown through a separate explicit option with an 'incomplete year' warning. Make years configurable rather than hardcoding them throughout the code.
- GBIF occurrence search for real georeferenced observation records, with filters for month, year range, taxon, accepted identification where possible, coordinate data and human/machine observations as appropriate. Exclude records without an event month, dubious coordinates or known absences. Keep GBIF record IDs to link to sources.
- Precise-distance testing: GBIF's geometry filter accepts WKT polygons in **longitude/latitude** order. Use an approximately circular polygon rather than blindly treating a latitude/longitude rectangle as the requested radius. Query size and polygon complexity should be kept sensible.
- Species counts must derive from *all matching records*, using a server-side count/facet or a complete batch extract; **never** use a capped sample of the first 300 records as if it were the total. If an exhaustive result cannot be obtained, say 'sample' and remove invented totals.
- For a small interactive demo, fetching one page of actual points is acceptable **only if** the map says that it shows a sample of the source records and species ranking is not misrepresented. Query caching and request debouncing should protect the provider.
- No AI-generated occurrence data and no invented common names. Link to GBIF species and occurrence records. Store provenance, source/last-fetched dates, licence and publisher attribution where available.

## Data design

Initial provider: [GBIF Occurrence API](https://techdocs.gbif.org/en/openapi/v1/occurrence); GBIF records aggregate data from many publishers and can be biased towards accessible/recorded places. The API supports occurrence search, filtering by month and year, geometry and taxon, and paging. Request limits and rate limits apply; for larger analysis use an occurrence download rather than repeatedly crawling the search API.

Candidate GET parameters for a **single location and month**: `geometry` (closed WKT polygon in lon/lat order), `month` (1–12), `year` (range), `taxonKey` (validated taxon), `hasCoordinate=true`, `occurrenceStatus=PRESENT` and appropriate `basisOfRecord`. Verify exact searchable filter semantics and availability against the live API before implementing. Use species-level identification rather than blindly counting genus-level records as a species.

Caveats:
- Records are **not** probabilities, abundance, or an authoritative species inventory.
- Multiple reports of one bird can be multiple records; recording effort varies by month, species, year and place.
- Georeferenced observations may be obscured, generalised or have coordinate uncertainty larger than the selected radius. Surface this uncertainty and do not imply metre-scale accuracy.
- Check UK national data providers (notably NBN Atlas) as a second source, keeping licences, duplicate handling and masking policies explicit. Do not silently merge two aggregators and double-count the same observation.
- Species images, if introduced, must be licensed and attributed; a photo must never be used to imply a local observation.
- Location privacy: avoid persisting an entered address or exact personal location, do not put exact coordinates into share links by default, and explain the destination of requests to external services.

## Components

- `LocationPicker` — place search, map pin, optional browser location permission
- `MonthPicker` — twelve months with a descriptive month label
- `RadiusPicker` — simple distance choices
- `TaxonPicker` — birds first
- `OccurrenceMap` — data points, radius circle and selected species
- `SpeciesList` and `SpeciesDetail` — ranked recorded taxa, provenance and inspectable records
- `DataProvenance` — period, dataset, attribution, limitations, export context

Use plain web components / modular JavaScript for this challenge unless there is a compelling reason to add a framework. The map and the field guide must work on mobile.

## Done means

- Switching **November → May** for the same location changes records according to **observation month**, not upload month.
- Selecting 1 km versus 10 km changes the query and the visible circle without claiming results outside the selected radius.
- All displayed records have actual provider IDs, observation dates and coordinates; the interface never fabricates species.
- Records with uncertain/sensitive coordinates are represented according to data restrictions, not precise pins asserted as known locations.
- A sparse-area query or failed API call produces a truthful empty/error state.
- A record's source, limitations and date range are visible without hunting through the repo.
- A working example is validated against returned real data before it is publicly described as live.

## Later, not day-one

Optional field-guide illustrations, month-to-month comparison, recording-effort correction where credible, song/audio links with licensing, 'things to look for' editorial content grounded in the species list, and print-quality seasonal postcards.
