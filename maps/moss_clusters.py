"""Day 04 — spatial clusters of NBN-recorded UK moss species.

The NBN 10 km cells are the only input. Thresholded neighbouring cells form
connected components (8-neighbour / queen adjacency). Clusters are *recording
patterns*, not mapped habitat extent or an ecological abundance estimate.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform, unary_union

from maps.moss import LETTERS, SPECIES

CELL_METRES = 10_000
MIN_CELLS = 3
# Each profile is a threshold on both distinct selected taxa and summed
# recorded observations. Varying the count threshold controls fragmentation;
# this is NOT an effort-corrected estimate of ecological richness.
GROUPS = {
    "all": tuple(SPECIES),
    "bog": tuple(name for name, (_, kind) in SPECIES.items() if kind == "Bog"),
    "woodland": tuple(name for name, (_, kind) in SPECIES.items() if kind == "Woodland"),
    "grassland": tuple(name for name, (_, kind) in SPECIES.items() if kind == "Grassland"),
    "stone": tuple(name for name, (_, kind) in SPECIES.items() if kind == "Stone and walls"),
}
# Evidence-calibrated to the NBN snapshot of 3 November 2026. Broad settings
# retain connected regions; focus separates the strongest co-recording groups.
THRESHOLDS = {
    "all": {"broad": (7, 120), "focus": (8, 0), "strong": (8, 100)},
    "bog": {"broad": (2, 0), "focus": (2, 5), "strong": (2, 10)},
    "woodland": {"broad": (2, 40), "focus": (2, 60), "strong": (2, 80)},
    "grassland": {"broad": (1, 25), "focus": (1, 40), "strong": (1, 50)},
    "stone": {"broad": (3, 45), "focus": (3, 60), "strong": (3, 80)},
}
TO_WGS = {
    "GB": Transformer.from_crs(27700, 4326, always_xy=True).transform,
    "NI": Transformer.from_crs(29903, 4326, always_xy=True).transform,
}


def grid_key(reference: str) -> tuple[str, int, int]:
    """Return grid scheme and integer 10 km easting/northing indices.

    The separate scheme prefix prevents connecting the British and Irish
    National Grids by coincidentally matching easting/northing values.
    """
    code = re.sub(r"\s+", "", str(reference).upper())
    match = re.fullmatch(r"([A-HJ-Z]{1,2})(\d{2})", code)
    if not match:
        raise ValueError(f"Not a UK 10 km grid reference: {reference!r}")
    letters, digits = match.groups()
    if len(letters) == 2:
        a, b = (LETTERS.index(c) for c in letters)
        e100 = ((a - 2) % 5) * 5 + b % 5
        n100 = 19 - (a // 5) * 5 - b // 5
        if not (0 <= e100 <= 6 and 0 <= n100 <= 12):
            raise ValueError(f"Outside British National Grid: {reference}")
        return "GB", e100 * 10 + int(digits[0]), n100 * 10 + int(digits[1])
    a = LETTERS.index(letters)
    return "NI", (a % 5) * 10 + int(digits[0]), (4 - a // 5) * 10 + int(digits[1])


def observation_stats(properties: dict, names: tuple[str, ...]) -> tuple[int, int]:
    data = properties.get("species", {})
    observed = {name: int(data.get(name, 0)) for name in names}
    return sum(value > 0 for value in observed.values()), sum(observed.values())


def neighbouring_components(eligible: dict, *, min_cells: int = MIN_CELLS) -> list[list[tuple]]:
    """Eight-connected components of occupied 10 km cells; deterministic.

    A diagonal join is treated as adjacency, not evidence of vegetation
    between the two cells. Components of fewer than min_cells are excluded.
    """
    visited = set()
    groups = []
    for source in sorted(eligible):
        if source in visited:
            continue
        pending = [source]
        visited.add(source)
        component = []
        while pending:
            scheme, x, y = current = pending.pop()
            component.append(current)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not (dx or dy):
                        continue
                    candidate = (scheme, x + dx, y + dy)
                    if candidate in eligible and candidate not in visited:
                        visited.add(candidate)
                        pending.append(candidate)
        if len(component) >= min_cells:
            groups.append(sorted(component))
    return sorted(groups, key=lambda comp: (-len(comp), comp[0]))


def cluster_footprint(cells: list[tuple], smooth_metres: float = 1_200):
    """Stylistic footprint of observed cells; it is NOT moss habitat extent.

    Dissolve exact 10 km square geometry in the correct national projection,
    then gently round corners before converting to GeoJSON coordinates.
    """
    schemes = {cell[0] for cell in cells}
    if len(schemes) != 1:
        raise ValueError("Cannot merge two different national grid systems")
    scheme = next(iter(schemes))
    squares = [box(x * CELL_METRES, y * CELL_METRES,
                   (x + 1) * CELL_METRES, (y + 1) * CELL_METRES)
               for _, x, y in cells]
    joined = unary_union(squares)
    # Avoid artificial merging of separate components: smoothing is small
    # relative to our 10 km uncertainty and applied after graph clustering.
    if smooth_metres:
        joined = joined.buffer(smooth_metres).buffer(-smooth_metres)
    joined = joined.simplify(450, preserve_topology=True)
    if joined.is_empty:
        raise ValueError("Cluster footprint became empty")
    return mapping(transform(TO_WGS[scheme], joined))


def compile_clusters(data: dict, source_manifest: dict | None = None) -> tuple[dict, dict]:
    """Build reproducible cluster profiles from the actual NBN occurrence grid."""
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError("Expected nonempty NBN moss FeatureCollection")
    indexed = {}
    for feature in data["features"]:
        properties = feature["properties"]
        key = grid_key(properties["grid"])
        if key in indexed:
            raise ValueError(f"Duplicate moss cell {properties['grid']}")
        indexed[key] = properties
    output = []
    counts = {}
    for group, names in GROUPS.items():
        for level, (min_species, min_records) in THRESHOLDS[group].items():
            eligible = {
                key: p for key, p in indexed.items()
                if (lambda s: s[0] >= min_species and s[1] >= min_records)(
                    observation_stats(p, names))
            }
            components = neighbouring_components(eligible)
            profile = f"{group}-{level}"
            counts[profile] = {
                "eligible_cells": len(eligible),
                "clusters": len(components),
                "cells_in_clusters": sum(len(c) for c in components),
                "min_species": min_species,
                "min_records": min_records,
                "min_adjacent_cells": MIN_CELLS,
            }
            for rank, cells in enumerate(components, 1):
                species = Counter()
                references = []
                for key in cells:
                    p = eligible[key]
                    references.append(p["grid"])
                    species.update({
                        name: int(p.get("species", {}).get(name, 0))
                        for name in names if p.get("species", {}).get(name, 0) > 0
                    })
                output.append({
                    "type": "Feature",
                    "geometry": cluster_footprint(cells),
                    "properties": {
                        "id": f"{profile}-{rank:03d}",
                        "group": group,
                        "level": level,
                        "rank": rank,
                        "cell_count": len(cells),
                        "observations": sum(species.values()),
                        "species_count": sum(n > 0 for n in species.values()),
                        "species": dict(sorted(species.items())),
                        "grid_refs": sorted(references),
                        "min_species": min_species,
                        "min_records": min_records,
                    },
                })
    manifest = {
        "title": "A rolling stone gathers no moss — Day 04: Clusters",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_generated_at": (source_manifest or {}).get("generated_at"),
        "source_file": "moss.geojson",
        "input_grids": len(indexed),
        "profiles": counts,
        "method": "Thresholded eight-neighbour connected components of NBN 10 km recording squares",
        "geometry_note": "Smoothed footprints of recording squares, not actual moss cover; may include sea, urban land or other unsuitable habitat.",
        "interpretation": "Clusters of recorded observations and co-occurrences; observer effort varies. No absence, abundance or habitat extent inferred.",
        "sensitivity": "Broad/focus/strong thresholds were calibrated to the 3 November 2026 eight-species snapshot, not an ecological benchmark.",
    }
    return {"type": "FeatureCollection", "features": output}, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("web/moss/moss.geojson"))
    parser.add_argument("--source-manifest", type=Path, default=Path("web/moss/moss-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("web/moss"))
    args = parser.parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8"))
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8")) if args.source_manifest.exists() else {}
    clusters, report = compile_clusters(data, manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "moss-clusters.geojson").write_text(
        json.dumps(clusters, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (args.output / "moss-clusters-manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Built {len(clusters['features'])} clusters in {len(report['profiles'])} profiles")
    for key, value in report["profiles"].items():
        print(f"  {key}: {value['clusters']} clusters, {value['cells_in_clusters']} squares")


if __name__ == "__main__":
    main()
