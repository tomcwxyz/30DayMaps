# Day 05 · Sight — What's Outside Your Window?

**Status: first interactive implementation committed at [`web/day05-wildlife/`](../../../web/day05-wildlife/); live API behaviour and deployment need browser verification.**

Run `python -m http.server 8000` from the repository root and open `http://localhost:8000/web/day05-wildlife/`. No front-end build step. Run the geodesic radius tests with `node --test tests/day05-geo.test.cjs`.

**Implemented:** place search (submit only, via Nominatim), map-point selection, optional browser geolocation, month and radius controls, 2021–2025 baseline plus optional 2026, four GBIF taxon groups, real occurrence-map points with source links, and full-search species facet counts for the leading 25 species. The map shows at most the first 300 returned points (clearly labelled) and lets a user fetch points for a selected species. No predictive probability is claimed. Future work remains in the brief below.

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
