"""Download NRW's Wales 2021 Ancient Woodland Inventory from its public WFS.

Explicitly paginate, validate FeatureCollection responses and persist the exact
download as GeoJSON. A failed/partial download is never used to label a GB map.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import requests

SERVICE = "https://datamap.gov.wales/geoserver/inspire-nrw/ows"
TYPE_NAME = "inspire-nrw:NRW_ANCIENT_WOODLAND_INVENTORY_2021"


def fetch_wales(destination: Path, *, page_size: int = 1000,
                session=None) -> Path:
    """Fetch every feature, validating WFS numberMatched, IDs and pagination."""
    if page_size < 1 or page_size > 10000:
        raise ValueError("page_size must be from 1 to 10000")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    http = session or requests.Session()
    seen = set()
    total = None
    count = 0
    start = 0
    try:
        with temp.open("w", encoding="utf-8") as out:
            out.write('{"type":"FeatureCollection","features":[')
            first = True
            while start < 1_000_000:
                resp = http.get(SERVICE, params={
                    "service": "WFS",
                    "version": "2.0.0",
                    "request": "GetFeature",
                    "typeNames": TYPE_NAME,
                    "outputFormat": "application/json",
                    "srsName": "EPSG:4326",
                    "count": page_size,
                    "startIndex": start,
                }, timeout=(20, 150))
                resp.raise_for_status()
                try:
                    payload = resp.json()
                except ValueError as exc:
                    raise RuntimeError("NRW WFS did not return JSON; check service") from exc
                if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
                    raise RuntimeError(f"NRW WFS returned error/non-GeoJSON: {str(payload)[:400]}")
                advertised = payload.get("numberMatched")
                if advertised is None or str(advertised).lower() == "unknown":
                    raise RuntimeError("NRW WFS omitted a verifiable numberMatched total")
                try:
                    page_total = int(advertised)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(f"Invalid NRW numberMatched: {advertised}") from exc
                if total is None:
                    total = page_total
                if total != page_total:
                    raise RuntimeError("NRW WFS changed the total across pages")
                records = payload["features"]
                if not records and count != total:
                    raise RuntimeError("NRW WFS stopped before all features were fetched")
                for feature in records:
                    if not isinstance(feature.get("geometry"), dict):
                        raise RuntimeError("Wales feature missing geometry")
                    identifier = feature.get("id")
                    if identifier is None:
                        raise RuntimeError("NRW WFS feature missing source ID")
                    if identifier in seen:
                        raise RuntimeError("Wales WFS repeated a feature ID across pages")
                    seen.add(identifier)
                    if not first:
                        out.write(",")
                    out.write(json.dumps(feature, separators=(",", ":")))
                    first = False
                    count += 1
                if count > total:
                    raise RuntimeError("NRW WFS returned more features than advertised")
                print(f"Wales: {count:,}/{total:,} records fetched", flush=True)
                if count == total:
                    break
                if not records:
                    raise RuntimeError("Incomplete Welsh inventory")
                # Advance by *actual* returned count in case WFS caps page size.
                start += len(records)
            else:
                raise RuntimeError("Exceeded safety limit for Welsh woodland WFS")
            out.write("]}")
        if not count or count != total:
            raise RuntimeError(f"Incomplete Welsh inventory: got {count}, expected {total}")
        temp.replace(destination)
        return destination
    finally:
        temp.unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/wales-ancient-woodland.geojson"))
    args = parser.parse_args()
    print(fetch_wales(args.output), flush=True)


if __name__ == "__main__":
    main()
