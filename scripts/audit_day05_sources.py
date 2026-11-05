#!/usr/bin/env python3
"""Day 05 source-coverage audit (read-only; no record merging).

Compare counts returned by GBIF and NBN Atlas for example British locations
and observation month. These are NOT interchangeable:
- search engines, interpretation, dataset inclusion and taxonomies differ
- record counts include duplicates across systems
- NBN location generalisation can mask precision
- NBN records carry separate licences, including noncommercial restrictions

This script never downloads or republishes individual NBN occurrences.
Output is a machine-readable, aggregate-only audit; it should not be
presented as a combined occurrence count.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

GBIF = "https://api.gbif.org/v1/occurrence/search"
NBN = "https://records-ws.nbnatlas.org/occurrences/search"
SITES = [
    {"name":"North East: Newton Aycliffe", "latitude":54.617,"longitude":-1.578},
    {"name":"Urban Scotland: Edinburgh", "latitude":55.9533,"longitude":-3.1883},
    {"name":"Rural Cumbria: Keswick", "latitude":54.601,"longitude":-3.135},
]
MONTH = 11
YEARS = "2021–2025"
RADIUS_KM = 5


def gbif_wkt(longitude:float, latitude:float, radius_km:float) -> str:
    import math
    latitude_r, longitude_r = math.radians(latitude), math.radians(longitude)
    distance = radius_km / 6371.0088
    ring=[]
    for i in range(37):
        bearing = 2*math.pi*i/36
        destlat=math.asin(math.sin(latitude_r)*math.cos(distance)+
                         math.cos(latitude_r)*math.sin(distance)*math.cos(bearing))
        destlon=longitude_r+math.atan2(
            math.sin(bearing)*math.sin(distance)*math.cos(latitude_r),
            math.cos(distance)-math.sin(latitude_r)*math.sin(destlat))
        ring.append((math.degrees(destlon),math.degrees(destlat)))
    ring.reverse()
    return "POLYGON((" + ",".join(f"{x:.6f} {y:.6f}" for x,y in ring) + "))"


def get_json(endpoint, params):
    url = endpoint + "?" + urlencode(params, doseq=True)
    request = Request(url, headers={
        "User-Agent":"30DayMaps-Day05-aggregate-source-audit/1.0",
        "Accept":"application/json"})
    with urlopen(request,timeout=38) as response:
        return json.load(response)


def audit_site(site):
    lat, lon = site["latitude"],site["longitude"]
    result = {"site":site["name"],"query_month":MONTH,
              "radius_km":RADIUS_KM,"years":YEARS}
    queries = {
      "gbif":{
        "endpoint":GBIF,
        "query":{
            "geometry":gbif_wkt(lon,lat,RADIUS_KM),
            "month":str(MONTH),
            "year":"2021,2025",
            "taxonKey":"212",  # GBIF legacy backbone Aves
            "occurrenceStatus":"PRESENT",
            "hasCoordinate":"true",
            "hasGeospatialIssue":"false",
            "limit":"0",
        },
      },
      "nbn":{
        "endpoint":NBN,
        "query":{
            "q":"*:*",
            "fq":["-occurrence_status:absent",
                  "year:[2021 TO 2025]",
                  # NBN indexed search-field names should be checked in practice.
                  "month:11",
                  "taxon_rank:species"],
            "lat":str(lat),
            "lon":str(lon),
            "radius":str(RADIUS_KM),
            "pageSize":"0",
        },
      }
    }
    for key, task in queries.items():
        try:
            data=get_json(task["endpoint"],task["query"])
            if key=="gbif":
                result[key]={"status":"ok","count":data.get("count")}
            else:
                # NBN Solr records endpoint convention is totalRecords;
                # do not fill in counts from differently named fields.
                count=data.get("totalRecords")
                result[key]={"status":"ok" if isinstance(count,int) else "unknown_shape",
                             "count":count,"response_keys":sorted(list(data.keys()))[:20]}
        except (HTTPError, URLError, ValueError, TimeoutError) as exc:
            result[key]={"status":"error","error":type(exc).__name__,
                         "note":str(exc)[:130]}
    return result



def probe_nbn_filters():
    """Find the smallest documented public query that the NBN endpoint accepts.

    Never mistake this broad-taxa diagnostic for bird/November data.
    """
    site=SITES[0]
    base={
        "q":"*:*",
        "lat":str(site["latitude"]),
        "lon":str(site["longitude"]),
        "radius":"5",
        "pageSize":"0",
    }
    variants=[
        ("all_public_records_in_radius",base),
        ("years_filter",dict(base,fq=["year:[2021 TO 2025]"])),
        ("observation_month_filter",dict(base,fq=["year:[2021 TO 2025]","month:11"])),
        ("bird_taxon_filter_candidate",dict(base,fq=[
            "year:[2021 TO 2025]","month:11","taxon_class:Aves"
        ])),
        ("bird_classs_candidate",dict(base,fq=[
            "year:[2021 TO 2025]","month:11","classs:Aves"
        ])),
        ("bird_class_candidate",dict(base,fq=[
            "year:[2021 TO 2025]","month:11","class:Aves"
        ]))
    ]
    result={}
    for label,query in variants:
        try:
            response=get_json(NBN,query)
            result[label]={
                "status":"ok",
                "totalRecords":response.get("totalRecords"),
                "keys":list(response.keys())[:12],
            }
        except (HTTPError,URLError,ValueError,TimeoutError) as exc:
            result[label]={"status":"error","kind":type(exc).__name__,
                           "note":str(exc)[:130]}
    return result


def main():
    report={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "purpose":"Compare independent source coverage; DO NOT ADD COUNTS OR MERGE",
        "definitions":{
            "gbif":"Georeferenced GBIF bird (taxonKey 212) occurrences, November 2021–2025",
            "nbn":"NBN Atlas public search, November 2021–2025; parameters exploratory and not comparable until validated",
        },
        "copyright_licence_warning":"NBN Atlas includes CC-BY-NC and generalised sensitive records. Do not ingest or present without per-record licence checks, citation and deduplication.",
        "results":[audit_site(site) for site in SITES],
        "nbn_parameter_diagnostic":probe_nbn_filters(),
    }
    filename=Path(sys.argv[1]) if len(sys.argv)>1 else Path("day05-source-audit.json")
    filename.parent.mkdir(parents=True,exist_ok=True)
    filename.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    # An API being unavailable is a finding, not a reason to make up a count.
    if not any(item["gbif"].get("status")=="ok" for item in report["results"]):
        raise SystemExit("No live GBIF baseline could be checked")


if __name__=="__main__":
    main()
