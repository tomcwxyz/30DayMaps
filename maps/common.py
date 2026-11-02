"""Reusable IO and boundaries for the mapping challenges."""
from __future__ import annotations

from pathlib import Path
import requests
import geopandas as gpd

OS_TRIG_ARCHIVE = "https://www.ordnancesurvey.co.uk/documents/gps/CompleteTrigArchive.zip"
ONS_REGIONS = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Regions_December_2025_Boundaries_EN_BGC/FeatureServer/0/query"
)
NORTH_EAST_CODE = "E12000001"
NAPTAN_CSV = "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"


def download(url: str, destination: Path, *, force: bool = False) -> Path:
    """Download once, atomically. Never commit downloaded data by default."""
    destination = Path(destination)
    if destination.exists() and not force:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=(15, 120), headers={
            "User-Agent": "30DayMaps/0.1 (open-data research)"
        }) as response:
            response.raise_for_status()
            with temp.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination


def regions(cache: Path, *, force: bool = False) -> gpd.GeoDataFrame:
    """The nine official English regions, including the entire North East/Tees Valley."""
    cache = Path(cache)
    if cache.exists() and not force:
        boundaries = gpd.read_file(cache)
    else:
        params = {
            "where": "1=1", "outFields": "*", "returnGeometry": "true",
            "outSR": "4326", "f": "geojson",
        }
        response = requests.get(ONS_REGIONS, params=params, timeout=(15, 120))
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(f"ONS ArcGIS error: {payload['error']}")
        features = payload.get("features", [])
        if len(features) != 9:
            raise ValueError(f"Expected nine English regions, got {len(features)}")
        boundaries = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        if "RGN25CD" not in boundaries:
            raise ValueError("ONS boundary schema changed: RGN25CD missing")
        boundaries = boundaries.to_crs("EPSG:27700")
        cache.parent.mkdir(parents=True, exist_ok=True)
        boundaries.to_file(cache, driver="GeoJSON")
    if boundaries.crs is None:
        raise ValueError("Missing CRS on English region boundaries")
    boundaries = boundaries.to_crs("EPSG:27700")
    if len(boundaries) != 9 or NORTH_EAST_CODE not in boundaries["RGN25CD"].values:
        raise ValueError("Invalid English region boundaries")
    return boundaries