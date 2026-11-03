"""Read verified Woodland Carbon Code project *polygons* from official ArcGIS data.

These are validated/verified project boundaries, NOT proof of already planted
trees, nor all woodland creation and not all rewilding. The projected footprint
may include open ground. No invented planting-year timeline is created.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import geopandas as gpd
import requests

SEARCH = "https://www.arcgis.com/sharing/rest/search"
EXPECTED_TITLE = "woodland carbon code projects"
# Independently identified from the live Scottish Forestry ArcGIS publication.
# Avoid using an arbitrary third-party layer merely sharing the right title.
PUBLISHER_SERVICE = ("https://services9.arcgis.com/RCPJF8Z8BrfjscvL/arcgis/rest/"
                     "services/Woodland_Carbon_Code_Projects_Read_Only_View/FeatureServer")
PUBLISHER_OWNER = "deborah.dunleavy_sf"


def _json(session, url, params):
    response = session.get(url, params=params, timeout=(20, 120))
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"ArcGIS service error: {payload['error']}")
    return payload


def find_project_layer(session=None) -> str:
    """Search ArcGIS Online for the publisher's named feature layer.

    Abort on ambiguity. A typo, expired layer, or renamed provider must be
    resolved rather than choosing some other forestry dataset silently.
    """
    http = session or requests.Session()
    candidates = []
    for query in (
        'title:"Woodland Carbon Code Projects" AND type:"Feature Service"',
        'title:"Woodland Carbon Code" AND type:"Feature Service"',
    ):
        result = _json(http, SEARCH, {"q": query, "f": "json", "num": 100})
        for item in result.get("results", []):
            title = str(item.get("title", "")).strip().lower()
            url = str(item.get("url", ""))
            if not url.startswith("https://") or "/rest/services/" not in url:
                continue
            if "woodland" not in title or "carbon" not in title or "code" not in title:
                continue
            if not url.endswith(("/FeatureServer", "/MapServer")):
                continue
            candidates.append({"title": title, "owner": item.get("owner"), "url": url,
                               "description": str(item.get("description", ""))[:200]})
        if candidates:
            break
    # Dedupe by URL, score exact publisher dataset title.
    candidates = list({x["url"]: x for x in candidates}.values())
    print("Woodland Carbon Code ArcGIS candidates:", json.dumps(candidates, indent=2), flush=True)
    verified = [x for x in candidates
                if x["owner"] == PUBLISHER_OWNER
                and x["url"].lower() == PUBLISHER_SERVICE.lower()]
    if len(verified) != 1:
        raise RuntimeError("Pinned Scottish Forestry WCC layer absent from ArcGIS discovery")
    return PUBLISHER_SERVICE


def download_polygons(output: Path, *, service: str | None = None, session=None) -> Path:
    """Page the ArcGIS project layer and reject incomplete or non-polygon output."""
    http = session or requests.Session()
    url = (service or PUBLISHER_SERVICE).rstrip("/")
    print(f"Using pinned Scottish Forestry WCC publisher service: {url}", flush=True)
    if not url.startswith("https://"):
        raise ValueError("ArcGIS source must be HTTPS")
    metadata = _json(http, url, {"f": "json"})
    layers = metadata.get("layers", [])
    if not layers:
        # Allow passing direct /FeatureServer/0 URL.
        layer = url
    else:
        selected = [x for x in layers if
                    "woodland" in str(x.get("name", "")).lower()
                    or "carbon" in str(x.get("name", "")).lower()]
        if not selected and len(layers) == 1:
            selected = layers
        if len(selected) != 1:
            raise RuntimeError(f"Expected one WCC polygon layer, found {layers}")
        layer = url + "/" + str(selected[0]["id"])
    details = _json(http, layer, {"f": "json"})
    if details.get("geometryType") != "esriGeometryPolygon":
        raise RuntimeError("WCC source is not a polygon layer")
    page_size = min(1000, int(details.get("maxRecordCount") or 1000))
    count_data = _json(http, layer + "/query",
                       {"where": "1=1", "returnCountOnly": "true", "f": "json"})
    expected = int(count_data["count"])
    if expected <= 0:
        raise RuntimeError("WCC project layer is empty")
    object_id = details.get("objectIdField") or details.get("objectIdFieldName") or "OBJECTID"
    features, seen = [], set()
    for offset in range(0, expected, page_size):
        page = _json(http, layer + "/query", {
            "where": "1=1", "outFields": "*", "returnGeometry": "true",
            "outSR": 4326, "f": "geojson",
            "orderByFields": object_id,
            "resultOffset": offset, "resultRecordCount": page_size,
        })
        if page.get("type") != "FeatureCollection":
            raise RuntimeError("WCC ArcGIS response is not GeoJSON FeatureCollection")
        records = page.get("features")
        if not isinstance(records, list) or not records:
            raise RuntimeError(f"WCC page at {offset} missing features")
        for feature in records:
            properties = feature.get("properties") or {}
            fid = properties.get(object_id) or feature.get("id")
            if fid is None or fid in seen:
                raise RuntimeError("WCC project feature IDs missing or repeated")
            seen.add(fid)
            if feature.get("geometry", {}).get("type") not in ("Polygon", "MultiPolygon"):
                raise RuntimeError("Non-polygon WCC geometry")
            features.append(feature)
        print(f"WCC: {len(features):,}/{expected:,} polygons fetched", flush=True)
    if len(features) != expected:
        raise RuntimeError(f"Incomplete WCC export: {len(features)} of {expected}")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".part")
    try:
        temporary.write_text(json.dumps({"type": "FeatureCollection",
                                         "features": features,
                                         "source_service": layer}),
                             encoding="utf-8")
        data = gpd.read_file(temporary, driver="GeoJSON")
        if len(data) != expected or data.crs is None:
            raise RuntimeError("Failed to validate WCC exported geometry")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", help="Verified official WCC polygon ArcGIS layer URL")
    parser.add_argument("--output", type=Path, default=Path("data/raw/wcc-projects.geojson"))
    args = parser.parse_args()
    print(download_polygons(args.output, service=args.service), flush=True)


if __name__ == "__main__":
    main()
