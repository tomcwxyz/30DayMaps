"""Fetch a bounded, reproducible snapshot of UK common-starling GBIF occurrences.

This is *occurrence* data, not a dataset of roosts or murmurations.
Usage: python -m maps.gbif_starlings
Requires Python >= 3.11 and access to https://api.gbif.org
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.gbif.org/v1"
TAXON = "Sturnus vulgaris"
COUNTRY = "GB"
YEAR = 2025
MONTH = 11
PAGE_SIZE = 300
RECORD_LIMIT = 20_000
ROOT = Path("challenges/04-clusters/data")
COLUMNS = [
    "gbifID", "eventDate", "year", "month", "decimalLatitude",
    "decimalLongitude", "coordinateUncertaintyInMeters",
    "basisOfRecord", "occurrenceStatus", "datasetKey",
    "datasetName", "publisher", "licence", "issues",
]


def get_json(url: str) -> dict:
    headers = {
        "User-Agent": "30DayMaps/2026 (educational open-data map; GitHub tomcwxyz/30DayMaps)",
        "Accept": "application/json",
    }
    for attempt in range(6):
        try:
            with urlopen(Request(url, headers=headers), timeout=55) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 5:
                raise
            pause = min(32, 2**attempt + .5)
            print(f"GBIF request temporarily failed: {exc}; retrying in {pause}s", flush=True)
            time.sleep(pause)
    raise RuntimeError("Unreachable")


def query_url(resource: str, **params: object) -> str:
    return f"{API}/{resource}?{urlencode(params)}"


def resolve_taxon() -> dict:
    result = get_json(query_url("species/match", name=TAXON, strict="true"))
    if result.get("matchType") == "NONE":
        raise ValueError(f"GBIF could not match {TAXON!r}")
    if result.get("rank") != "SPECIES" or not str(result.get("scientificName", "")).startswith(TAXON):
        raise ValueError(f"Unexpected species match: {result}")
    if not isinstance(result.get("usageKey"), int):
        raise ValueError(f"Taxon missing usageKey: {result}")
    return result


def licence_type(value: str) -> str | None:
    """Only CC0/CC BY records are redistributed; CC BY-NC excluded."""
    text = str(value or "").lower().replace("-", "_")
    if "by_nc" in text or "/by_nc/" in text or "/by-nc/" in text:
        return None
    if "cc0" in text or "publicdomain/zero/1.0" in text:
        return "CC0"
    if "cc_by_4_0" in text or "licenses/by/4.0" in text:
        return "CC BY 4.0"
    return None


def parse_record(record: dict) -> tuple[dict | None, str | None]:
    ident = record.get("gbifID") or record.get("key")
    lat, lon = record.get("decimalLatitude"), record.get("decimalLongitude")
    if not ident or not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)):
        return None, "missing ID or coordinates"
    if not math.isfinite(lat) or not math.isfinite(lon) or not (49 <= lat <= 60 and -9 <= lon <= 3):
        return None, "outside bounding area"
    if record.get("country") != COUNTRY and record.get("countryCode") != COUNTRY:
        return None, "country not GB"
    if str(record.get("year")) != str(YEAR) or str(record.get("month")) != str(MONTH):
        return None, "unexpected date"
    valid_licence = licence_type(record.get("license", ""))
    if not valid_licence:
        return None, "licence excludes redistribution"
    issues = record.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    cleaned = {
        "gbifID": str(ident),
        "eventDate": str(record.get("eventDate") or ""),
        "year": YEAR,
        "month": MONTH,
        "decimalLatitude": lat,
        "decimalLongitude": lon,
        "coordinateUncertaintyInMeters": record.get("coordinateUncertaintyInMeters") or "",
        "basisOfRecord": record.get("basisOfRecord") or "",
        "occurrenceStatus": record.get("occurrenceStatus") or "",
        "datasetKey": record.get("datasetKey") or "",
        "datasetName": record.get("datasetName") or "",
        "publisher": record.get("publisher") or "",
        "licence": valid_licence,
        "issues": "|".join(issues),
    }
    return cleaned, None


def fetch() -> tuple[list[dict], dict]:
    taxon = resolve_taxon()
    taxon_key = taxon["usageKey"]
    params = {
        "taxonKey": taxon_key,
        "country": COUNTRY,
        "year": YEAR,
        "month": MONTH,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
    }
    # One complete monthly count is the integrity target.
    # GBIF deep-offset searches slowed dramatically beyond 10,000 results
    # in November 2026. Small non-overlapping day ranges avoid deep offsets.
    monthly = get_json(query_url("occurrence/search", **params, limit=0))
    total = int(monthly.get("count", 0))
    print(f"GBIF monthly occurrence count: {total}", flush=True)
    if total < 1:
        raise RuntimeError("No GBIF occurrences returned: refusing to write a blank snapshot")
    if total > RECORD_LIMIT:
        raise RuntimeError(
            f"GBIF returned {total:,} records, above our {RECORD_LIMIT:,} file limit. "
            "Narrow the documented date scope or use an authenticated GBIF DOI download. "
            "Do not silently store a biased first-page sample."
        )
    rows_by_id: dict[str, dict] = {}
    rejection_counts: Counter[str] = Counter()
    partitions = []
    partitioned_total = 0
    for first_day in range(1, 31, 5):
        last_day = min(30, first_day + 4)
        day_range = f"{first_day},{last_day}"
        bounded = {**params, "day": day_range}
        first_page = get_json(query_url("occurrence/search", **bounded, limit=PAGE_SIZE, offset=0))
        count = int(first_page.get("count", 0))
        print(f"Days {day_range}: {count:,} matches", flush=True)
        if count > 10_000:
            raise RuntimeError(
                f"Daily partition {day_range} has {count:,} records. "
                "Split into smaller day ranges before retrieving deeper offsets."
            )
        partitioned_total += count
        partitions.append({"day_range": day_range, "gbif_count": count})
        offset = 0
        payload = first_page
        while offset < count:
            if offset:
                payload = get_json(query_url(
                    "occurrence/search", **bounded, limit=PAGE_SIZE, offset=offset
                ))
            records = payload.get("results", [])
            if not records:
                raise RuntimeError(
                    f"GBIF pagination ended early at {day_range}, offset {offset}/{count}"
                )
            if len(records) > min(PAGE_SIZE, count - offset):
                raise RuntimeError("GBIF returned more than the declared page size")
            for occurrence in records:
                day = occurrence.get("day")
                if not isinstance(day, int) or not first_day <= day <= last_day:
                    raise RuntimeError(
                        f"GBIF returned a record outside day partition {day_range}"
                    )
                cleaned, why = parse_record(occurrence)
                if cleaned:
                    rows_by_id[cleaned["gbifID"]] = cleaned
                else:
                    rejection_counts[why] += 1
            offset += len(records)
            print(
                f"Fetched {offset:,}/{count:,} in days {day_range} "
                f"({len(rows_by_id):,} eligible unique records)", flush=True
            )
            if offset < count:
                time.sleep(.12)
    # Year/month-only events or long date intervals may have no single day.
    # Do not silently omit them: a full-month extract must account for all.
    if partitioned_total != total:
        raise RuntimeError(
            f"Partition coverage mismatch: monthly GBIF count is {total:,}, "
            f"daily partitions sum to {partitioned_total:,}. "
            "Some records may have imprecise dates. A complete extract needs "
            "another explicit strategy or an official GBIF download."
        )
    rows = sorted(rows_by_id.values(), key=lambda row: int(row["gbifID"]))
    if not rows:
        raise RuntimeError("No CC0/CC BY GBIF occurrences available for redistribution")
    ds_counts = Counter((r["datasetKey"], r["datasetName"], r["publisher"], r["licence"]) for r in rows)
    dataset_info = [
        {"datasetKey": k, "datasetName": n, "publisher": p, "licence": lic, "records": num}
        for (k, n, p, lic), num in ds_counts.most_common()
    ]
    manifest = {
        "source": "GBIF occurrence search API",
        "source_url": "https://www.gbif.org/",
        "api_endpoint": f"{API}/occurrence/search",
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "taxon": TAXON,
        "taxon_key": taxon_key,
        "gbif_match": {"scientificName": taxon.get("scientificName"), "rank": taxon.get("rank")},
        "query": params,
        "partitioned_counts": partitions,
        "partitioned_total": partitioned_total,
        "total_matching_gbif_occurrences": total,
        "exported_records": len(rows),
        "skipped_records": dict(rejection_counts),
        "deduplication": "gbifID",
        "record_identifier_url_template": "https://www.gbif.org/occurrence/{gbifID}",
        "licence_policy": "Redistribute only CC0 and CC BY 4.0. CC BY-NC and unknown licence records are omitted.",
        "dataset_attribution": dataset_info,
        "limitations": [
            "These are all eligible returned occurrence records for the bounded query, NOT murmuration or roost observations.",
            "Observations are not independent birds, abundance, density estimates, population or confirmed active roosts.",
            "Source licences and record quality vary. Spatial distribution reflects recorder effort and reporting bias.",
            "The search API is not a DOI-backed GBIF download; for formal publication request a citable download DOI.",
            "The file is a dated API snapshot and may change if GBIF publishers amend records.",
        ],
    }
    return rows, manifest


def save(rows: list[dict], manifest: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "gbif_sturnus_vulgaris_gb_2025_11.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    manifest["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest["csv_file"] = csv_path.name
    (output / "gbif_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(rows):,} records to {csv_path} ({csv_path.stat().st_size:,} bytes)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    rows, manifest = fetch()
    save(rows, manifest, args.output)


if __name__ == "__main__":
    main()
