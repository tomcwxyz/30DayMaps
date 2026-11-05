#!/usr/bin/env python3
"""Verify GBIF actually returns reusable multimedia for nearby bird species.

All image licence checks refer to the *media object's* licence, rather than
inheriting a (potentially different) occurrence data licence.
No image is downloaded, cached or copied by this audit.
"""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from scripts.audit_day05_sources import gbif_wkt

GBIF="https://api.gbif.org/v1/occurrence/search"
ALLOW={"CC0_1_0","CC_BY_4_0","CC_BY_3_0"}
def query(params):
    url=GBIF+"?"+urlencode(params)
    with urlopen(Request(url,headers={
        "User-Agent":"30DayMaps-Day05-image-licence-audit/1.0",
        "Accept":"application/json"}),timeout=35) as response:
        return json.load(response)

def usable(occurrence,species_key):
    if str(occurrence.get("speciesKey"))!=str(species_key):
        return False
    for media in occurrence.get("media",[]):
        licence=str(media.get("license") or "")
        allowed=licence in ALLOW or licence.startswith(
            ("http://creativecommons.org/licenses/by/4.0",
             "https://creativecommons.org/licenses/by/4.0",
             "http://creativecommons.org/publicdomain/zero/1.0",
             "https://creativecommons.org/publicdomain/zero/1.0"))
        if (allowed and str(media.get("identifier") or "").startswith("https://")
                and (str(media.get("type") or "").lower()=="stillimage"
                or str(media.get("format") or "").lower().startswith("image/"))):
            return True
    return False

def main():
    near=query({
        "geometry":gbif_wkt(-1.578,54.617,5),
        "month":"11","year":"2021,2025","taxonKey":"212",
        "occurrenceStatus":"PRESENT","hasCoordinate":"true",
        "limit":"3","facet":"speciesKey","facetLimit":"8"
    })
    facet=next((f for f in near.get("facets",[])
                if "species" in f.get("field","").lower() and
                "key" in f.get("field","").lower()),{})
    samples=[]
    for entry in facet.get("counts",[])[:8]:
        key=entry["name"]
        images=query({"taxonKey":str(key),"mediaType":"StillImage",
                      "occurrenceStatus":"PRESENT","limit":"16"})
        samples.append({
            "speciesKey":key,
            "nearby_November_record_count":entry["count"],
            "global_image_sample_size":len(images.get("results",[])),
            "licensed_image_present_in_first_16":any(
                usable(record,key) for record in images.get("results",[])
            )
        })
    report={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "note":"Photographs are global taxon examples, not local observations. Only explicit per-media reuse licences are accepted.",
        "reference_area":"Newton Aycliffe example location (5 km)",
        "species_tested":len(samples),
        "licensable_species_in_sample":sum(item["licensed_image_present_in_first_16"] for item in samples),
        "samples":samples,
    }
    print(json.dumps(report,indent=2))
    path=Path(sys.argv[1]) if len(sys.argv)>1 else Path("day05-image-audit.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    if not samples:
        raise SystemExit("No source species facets available")


if __name__=="__main__":
    main()
