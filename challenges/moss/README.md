# A rolling stone gathers no moss

This experimental UK map uses the NBN Atlas occurrence search API to compare eight illustrative moss species in open-licence records. It maps **recorded presences** by 10 km square, not the land covered by moss.

## Design

The interactive map in web/moss/index.html offers two metrics: number of selected species represented in a grid square, or number of observations recorded there. Species can be selected by type: bog, woodland, grassland, stone and walls. It suits a nature-themed standalone piece, Day 09 urban–rural, or a later challenge with a modified visual language.

## Data and licences

Official API: https://records-ws.nbnatlas.org/occurrences/search

Documentation: https://nbnatlas.freshdesk.com/support/solutions/articles/201000131599-occurrence-web-services

Only CC0, CC-BY and OGL records are included. The importer first checks the licence facet for each species; it refuses to proceed when it cannot verify licences. To avoid mass occurrence downloads and inadvertent disclosure of precise sensitive sites, it requests 10 km grid facet counts (cl18). A dated source manifest lists licences and returned data partners for attribution.

This selected-species comparison is not total bryophyte diversity; no causal claims about the proverb. Higher recording counts do not mean greater moss abundance. Recording effort and availability of open records vary. Northern Ireland grid references are supported where the source supplies them. Invalid or unsupported grid labels are reported.

## Run and share

Install dependencies (Python 3.11+), then run:

    python -m pip install -e '.[test]'
    python -m pytest -q tests/test_moss.py
    python -m maps.moss
    python -m http.server 8000

Open http://localhost:8000/web/moss/ to explore the map. There is no mock or synthetic map data. If NBN is unavailable, data generation fails rather than showing invented sightings.

The workflow in .github/workflows/render-moss.yml downloads the grid data, uploads the GeoJSON and provenance manifest as an Actions artefact, and commits the snapshot into the repository when running on main. Publishing the webpage separately remains optional. Reuse of any NBN data must preserve the relevant source attribution and licence conditions.
