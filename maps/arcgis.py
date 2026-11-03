"""Paginated ArcGIS feature-service downloads for the Day 03 polygon extras."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

HEADERS = {"User-Agent": "30DayMaps/0.1 (open-data research)"}


def query_features(layer_url: str, *, bbox: tuple[float, float, float, float] | None = None,
                   where: str = "1=1", out_fields: str = "*", page_size: int = 500,
                   max_pages: int = 400, paginate: bool = True, session=None) -> gpd.GeoDataFrame:
    """Fetch every feature matching a query, page by page, into British National Grid.

    Requests GeoJSON in WGS84 (the only CRS GeoJSON promises) and reprojects locally.
    Fails if the service reports an error or a page limit is hit, rather than
    silently returning a partial layer.
    """
    http = session or requests
    params = {
        "where": where, "outFields": out_fields, "returnGeometry": "true",
        "outSR": "4326", "f": "geojson", "resultRecordCount": str(page_size),
    }
    if not paginate:  # some services reject paging parameters outright
        params.pop("resultRecordCount")
    if bbox is not None:
        params.update({
            "geometry": ",".join(str(v) for v in bbox),
            "geometryType": "esriGeometryEnvelope", "inSR": "27700",
            "spatialRel": "esriSpatialRelIntersects",
        })
    frames, offset = [], 0
    for _ in range(max_pages):
        page = dict(params, resultOffset=str(offset)) if paginate else params
        payload = _get_json(http, f"{layer_url.rstrip('/')}/query", page)
        if "error" in payload:
            raise RuntimeError(f"ArcGIS error from {layer_url}: {payload['error']}")
        features = payload.get("features", [])
        if features:
            frames.append(gpd.GeoDataFrame.from_features(features, crs="EPSG:4326"))
        exceeded = payload.get("exceededTransferLimit") or payload.get(
            "properties", {}).get("exceededTransferLimit")
        if not paginate:
            if exceeded:
                raise RuntimeError(f"Unpaginated query to {layer_url} was truncated")
            break
        if not features or (len(features) < page_size and not exceeded):
            break
        offset += len(features)
    else:
        raise RuntimeError(f"Page limit reached for {layer_url}; refusing a partial layer")
    if not frames:
        raise ValueError(f"No features returned from {layer_url}")
    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    return combined.to_crs(27700)


def _get_json(http, url, params, attempts: int = 4):
    """Retry gateway timeouts and dropped connections; ArcGIS Online has off moments."""
    import time
    for attempt in range(attempts):
        try:
            response = http.get(url, params=params, timeout=(20, 180), headers=HEADERS)
            if getattr(response, "status_code", 200) in (502, 503, 504) and attempt < attempts - 1:
                time.sleep(5 * 2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts - 1:
                raise
            time.sleep(5 * 2 ** attempt)


def cached_query(cache: Path, layer_url: str, *, force: bool = False, **query) -> gpd.GeoDataFrame:
    """Download once to GeoPackage; later runs read the cache."""
    cache = Path(cache)
    if cache.exists() and not force:
        data = gpd.read_file(cache)
        if data.crs is None:
            raise ValueError(f"Cached layer has no CRS: {cache}")
        return data.to_crs(27700)
    data = query_features(layer_url, **query)
    cache.parent.mkdir(parents=True, exist_ok=True)
    data.to_file(cache, driver="GPKG")
    return data
