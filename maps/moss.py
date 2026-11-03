"""Fetch open-licence UK moss records from NBN Atlas as 10 km grid summaries."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import requests
from pyproj import Transformer

API = "https://records-ws.nbnatlas.org/occurrences/search"
SPECIES_API = "https://species-ws.nbnatlas.org/search"
SPECIES = {
    "Sphagnum palustre": ("Blunt-leaved bog-moss", "Bog"),
    "Sphagnum capillifolium": ("Red bog-moss", "Bog"),
    "Polytrichum commune": ("Common haircap", "Woodland"),
    "Hypnum cupressiforme": ("Cypress-leaved plait-moss", "Woodland"),
    "Rhytidiadelphus squarrosus": ("Springy turf-moss", "Grassland"),
    "Grimmia pulvinata": ("Grey-cushioned Grimmia", "Stone and walls"),
    "Tortula muralis": ("Wall screw-moss", "Stone and walls"),
    "Syntrichia ruralis": ("Great hairy screw-moss", "Stone and walls"),
}
GB = Transformer.from_crs(27700, 4326, always_xy=True)
IE = Transformer.from_crs(29903, 4326, always_xy=True)
LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def open_licence(label):
    token = re.sub("[^a-z0-9]", "", str(label).lower())
    if token.startswith(("cc0", "ogl", "opengovernmentlicence")):
        return True
    return token.startswith("ccby") and not any(v in token for v in ("nc", "nd", "sa"))


def facet_rows(payload, field):
    roots = payload.get("facetResults", [])
    if isinstance(roots, dict):
        roots = roots.get("fieldResult", [])
    if isinstance(roots, dict):
        roots = [roots]
    for item in roots:
        if not isinstance(item, dict):
            continue
        if (item.get("fieldName") or item.get("field") or item.get("name")) == field:
            return item.get("fieldResult", item.get("values", []))
    if roots and all(isinstance(x, dict) and "label" in x for x in roots):
        return roots
    return []


def resolve_tvk(session, species):
    """Resolve an accepted UKSI taxon key, avoiding authorship/name ambiguity."""
    params = [("q", "*:*"), ("fq", "idxtype:TAXON"),
              ("fq", 'scientificName:"' + species + '"'), ("pageSize", 25)]
    try:
        response = session.get(SPECIES_API, params=params, timeout=30)
        response.raise_for_status()
        items = response.json().get("searchResults", {}).get("results", [])
    except (requests.RequestException, ValueError, AttributeError):
        return None
    exact = [item for item in items
             if item.get("scientificName", "").casefold() == species.casefold()]
    exact.sort(key=lambda item: item.get("taxonomicStatus") != "accepted")
    for item in exact:
        key = item.get("acceptedConceptID") or item.get("guid")
        if key and re.fullmatch(r"[A-Z]+[0-9]+", str(key)):
            return key
    return None


def query(session, species, fields, licence=None, tvk=None):
    params = [("q", "lsid:" + tvk if tvk else 'taxon_name:"' + species + '"'),
              ("fq", '-occurrence_status:"absent"'),
              ("pageSize", 0), ("flimit", -1)]
    if licence is not None:
        params.append(("fq", 'license:"' + licence.replace('"', "") + '"'))
    params.extend(("facets", name) for name in fields)
    for attempt in range(3):
        try:
            response = session.get(API, params=params, timeout=50)
            response.raise_for_status()
            data = response.json()
            if data.get("status", "OK") != "OK":
                raise ValueError("NBN API response: " + str(data.get("status")))
            return data
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 + attempt)
    raise RuntimeError("Unreachable")


def square(ref):
    ref = re.sub(r"\s+", "", str(ref).upper())
    m = re.fullmatch(r"([A-HJ-Z]{1,2})(\d{2})", ref)
    if not m:
        return None
    letters, digits = m.groups()
    if len(letters) == 2:
        a, b = (LETTERS.index(c) for c in letters)
        e100 = ((a - 2) % 5) * 5 + b % 5
        n100 = 19 - (a // 5) * 5 - b // 5
        if not (0 <= e100 <= 6 and 0 <= n100 <= 12):
            return None
        e, n, transformer = e100 * 100000, n100 * 100000, GB
    else:
        a = LETTERS.index(letters)
        e, n, transformer = (a % 5) * 100000, (4 - a // 5) * 100000, IE
    e += int(digits[0]) * 10000
    n += int(digits[1]) * 10000
    pts = [(e, n), (e + 10000, n), (e + 10000, n + 10000),
           (e, n + 10000), (e, n)]
    ring = [[round(x, 6), round(y, 6)] for x, y in
            (transformer.transform(a, b) for a, b in pts)]
    lon = sum(pt[0] for pt in ring[:4]) / 4
    lat = sum(pt[1] for pt in ring[:4]) / 4
    if not (-11.8 < lon < 2.6 and 49 < lat < 61.5):
        return None
    return ring


def retrieve(session):
    cells = defaultdict(Counter)
    species_info = []
    providers = Counter()
    rejected_grids = Counter()
    for scientific, (common, habitat) in SPECIES.items():
        print("Checking NBN taxon:", scientific, flush=True)
        tvk = resolve_tvk(session, scientific)
        licences = query(session, scientific, ("license",), tvk=tvk)
        licence_facets = facet_rows(licences, "license")
        if not licence_facets:
            if not int(licences.get("totalRecords", 0)):
                species_info.append({"name": scientific, "common": common, "type": habitat,
                                     "licences": [], "mapped_records": 0,
                                     "all_licence_records": 0, "taxon_key": tvk,
                                     "status": "not returned by NBN occurrence query"})
                continue
            raise ValueError("No licence facets for " + scientific + "; cannot verify data use")
        permitted = sorted({str(item["label"]) for item in licence_facets
                            if open_licence(item.get("label"))})
        mapped_records = 0
        for licence in permitted:
            response = query(session, scientific, ("cl18", "data_provider"), licence, tvk=tvk)
            grids = facet_rows(response, "cl18")
            if response.get("totalRecords", 0) and not grids:
                raise ValueError("No 10 km grid facets for " + scientific)
            for entry in grids:
                code = str(entry.get("label", "")).upper().replace(" ", "")
                count = int(entry.get("count", 0))
                if count <= 0:
                    continue
                if square(code) is None:
                    rejected_grids[code] += count
                    continue
                cells[code][scientific] += count
                mapped_records += count
            for entry in facet_rows(response, "data_provider"):
                providers[str(entry.get("label", "unknown"))] += int(entry.get("count", 0))
        species_info.append({"name": scientific, "common": common, "type": habitat,
                             "licences": permitted, "mapped_records": mapped_records,
                             "all_licence_records": int(licences.get("totalRecords", 0)),
                             "taxon_key": tvk, "status": "mapped" if mapped_records else "no open mapped records"})
    if not cells:
        raise ValueError("No open-licence NBN moss grid data; refusing to create empty map")
    features = [{"type": "Feature",
                 "geometry": {"type": "Polygon", "coordinates": [square(code)]},
                 "properties": {"grid": code, "richness": len(counts),
                                "records": sum(counts.values()), "species": dict(counts)}}
                for code, counts in sorted(cells.items())]
    manifest = {"title": "A rolling stone gathers no moss", "source": "NBN Atlas",
                "source_api": API, "generated_at": datetime.now(timezone.utc).isoformat(),
                "resolution": "10 km occurrence grid, NOT moss cover",
                "scope": "Eight selected moss species; open-licence records only",
                "caveat": "Presence-only records; coverage and recording effort vary. Blank does not mean absent.",
                "grids": len(features), "species": species_info,
                "contributors": [{"name": k, "record_count": v} for k, v in providers.most_common()],
                "unmapped_grid_labels": dict(rejected_grids.most_common(30))}
    return {"type": "FeatureCollection", "features": features}, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("web/moss"))
    args = parser.parse_args()
    with requests.Session() as session:
        session.headers.update({"User-Agent": "30DayMaps open-source moss map/1.0"})
        geojson, manifest = retrieve(session)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "moss.geojson").write_text(json.dumps(geojson, separators=(",", ":")))
    (args.output / "moss-manifest.json").write_text(json.dumps(manifest, indent=2))
    print("NBN Atlas moss grids:", manifest["grids"])


if __name__ == "__main__":
    main()
