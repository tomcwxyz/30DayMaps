# Moss maps — Day 04: Clusters

The initial NBN Atlas 10 km grid-based experiment became the **Day 04 — Clusters** map, *A Rolling Stone Gathers No Moss*.

The active implementation and methodology are at [challenges/04-clusters/README.md](../04-clusters/README.md).

The original record evidence remains at web/moss/moss.geojson with its source/licence manifest. Spatially connected clusters are built reproducibly by maps/moss_clusters.py and served by web/moss/index.html, including a toggle to show and inspect the original grid.

Run from the repository root:

    python -m pip install -e '.[test]'
    python -m pytest -q tests/test_moss.py tests/test_moss_clusters.py
    python -m maps.moss_clusters
    python -m http.server 8000

Open http://localhost:8000/web/moss/. Use python -m maps.moss first only when you want a fresh real NBN source snapshot. The map does not substitute invented records.
