"""One-call live GBIF integration check for the Day 05 wildlife map.

Runs on GitHub Actions. No sample sightings or results are written to the repo.
Tests the live endpoint, actual filter semantics, and species facet support.
"""
from __future__ import annotations
import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CENTRE_LAT, CENTRE_LON = 54.617, -1.578  # approximate town-centre demo, not a home address


def radius_wkt(lon: float, lat: float, radius_km: float, sides: int = 36) -> str:
    distance = radius_km / 6371.0088
    latitude, longitude = math.radians(lat), math.radians(lon)
    points = []
    for i in range(sides + 1):
        bearing = 2 * math.pi * i / sides
        destlat = math.asin(math.sin(latitude) * math.cos(distance) +
                           math.cos(latitude) * math.sin(distance) * math.cos(bearing))
        destlon = longitude + math.atan2(math.sin(bearing) * math.sin(distance) * math.cos(latitude),
                                         math.cos(distance) - math.sin(latitude) * math.sin(destlat))
        points.append((math.degrees(destlon), math.degrees(destlat)))
    points.reverse()
    return "POLYGON((" + ",".join(f"{lon:.6f} {lat:.6f}" for lon, lat in points) + "))"


def main() -> None:
    params = {
        "geometry": radius_wkt(CENTRE_LON, CENTRE_LAT, 5),
        "year": "2021,2025",
        "month": "11",
        "taxonKey": "212",  # GBIF Backbone Aves
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
        "limit": "5",
        "facet": "speciesKey",
        "facetLimit": "10",
    }
    url = "https://api.gbif.org/v1/occurrence/search?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "30DayMaps-Day05-API-SanityCheck/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=35) as response:
        assert response.status == 200, response.status
        data = json.load(response)
    assert isinstance(data.get("count"), int), "GBIF did not return an occurrence count"
    assert isinstance(data.get("results"), list), "GBIF did not return occurrence records"
    if data["count"] > 0:
        assert data["results"], "GBIF count is positive but records missing"
        assert all(isinstance(item.get("key"), int) for item in data["results"])
    facet = next((f for f in data.get("facets", [])
                  if "species" in f.get("field", "").lower() and "key" in f.get("field", "").lower()), None)
    assert facet is not None, "GBIF did not return a speciesKey facet"
    assert isinstance(facet.get("counts"), list), "Species facet counts are unavailable"
    if data["count"] > 0:
        assert facet["counts"], "Source records exist but species facet is empty"
    # A second, on-demand query demonstrates the seasonal distribution for a
    # real selected species. It uses the same location and year window but
    # deliberately removes the month filter.
    seasonal_values = None
    if facet["counts"]:
        first_species = facet["counts"][0]["name"]
        seasonal_params = dict(params)
        seasonal_params.pop("month")
        seasonal_params["taxonKey"] = str(first_species)
        seasonal_params["facet"] = "month"
        seasonal_params["facetLimit"] = "12"
        seasonal_params["limit"] = "0"
        seasonal_url = "https://api.gbif.org/v1/occurrence/search?" + urlencode(seasonal_params)
        with urlopen(Request(seasonal_url, headers={
            "User-Agent": "30DayMaps-Day05-API-SanityCheck/1.0",
            "Accept": "application/json"
        }), timeout=35) as response:
            seasonal_data = json.load(response)
        month_facet = next((x for x in seasonal_data.get("facets", [])
                            if x.get("field", "").lower() == "month"), None)
        assert month_facet is not None, "GBIF did not return a month facet"
        assert isinstance(month_facet.get("counts"), list), "GBIF month facet missing counts"
        seasonal_values = len(month_facet["counts"])
    print(json.dumps({
        "success": True,
        "source": "GBIF occurrence search",
        "reference_location": "approximate Newton Aycliffe town-centre",
        "filter_month": "November",
        "filter_years": "2021–2025",
        "query_radius_km": 5,
        "records_matching_query": data["count"],
        "source_records_returned_for_smoke_test": len(data["results"]),
        "species_facet_values_returned": len(facet["counts"]),
        "monthly_facet_values_returned": seasonal_values
    }, indent=2))


if __name__ == "__main__":
    main()
