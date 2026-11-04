# Day 04 — Clusters: GBIF common-starling data

**Scope: data collection only.** The earlier interactive site, curated roost locations, animated flock, and Vercel demonstration have been removed from the Day 4 codebase. No map or visualisation is currently published from this work.

## Dataset

A reproducible GBIF occurrence API extraction targeting the species *Sturnus vulgaris* (European/common starling) in the United Kingdom, for **November 2025**. The query requests coordinates, no reported geospatial issue and `PRESENT` occurrence status.

- Script: [`maps/gbif_starlings.py`](../../maps/gbif_starlings.py)
- Tests: [`tests/test_gbif_starlings.py`](../../tests/test_gbif_starlings.py)
- GitHub Action: [`.github/workflows/day04-gbif.yml`](../../.github/workflows/day04-gbif.yml)
- Intended output: `challenges/04-clusters/data/gbif_sturnus_vulgaris_gb_2025_11.csv`
- Intended attribution: `challenges/04-clusters/data/gbif_manifest.json`

The files in `data/` exist **only after a completed, successful download and commit**. Do not treat their absence as zero observations.

## Run locally

From the repository root with Python 3.11+:

```bash
python -m unittest discover -s tests -p 'test_gbif_starlings.py' -v
python -m maps.gbif_starlings
```

The downloader uses the standard library. It pages through every matching result, de-duplicates on GBIF ID and preserves event date, location, dataset and licence identifiers, and quality flags. It stores a JSON manifest with retrieval timestamp, GBIF query parameters, source dataset attribution, counts and SHA-256 integrity hash.

**Bounded extract:** The GBIF public search API has a 100,000-record ceiling. To avoid quietly writing a biased page-limited sample, this script fails if more than 20,000 matching records are found. Expand the scope only by using a documented, licence-aware GBIF download request and storing the download DOI.

**Licences:** The script includes CC0 and CC BY 4.0 observations. CC BY-NC and unknown-licence records are excluded from redistributed data. Individual contributing datasets and their attribution appear in the manifest.

## Interpret with care

GBIF starling observations are **not confirmed murmurations**, actual roost locations, numbers of individual birds or abundance measurements. Records are heavily influenced by where people observe and report birds; clusters may indicate observation effort rather than wildlife behaviour. No statistical hot-spot or population claim should be made without addressing those biases.

Source: [GBIF](https://www.gbif.org/); individual records can be resolved at `https://www.gbif.org/occurrence/{gbifID}`.

For any future publication or substantive research, request an official GBIF DOI-backed occurrence download and cite the contributing datasets.

### Deep-pagination reliability

The extraction splits the November search into six non-overlapping five-day ranges using GBIF's documented `day` range filter, keeping individual search offsets below 10,000. The manifest records each partition's count and compares their sum against the original unpartitioned monthly count. If GBIF contains month-only observations without an explicit day, the check **fails rather than silently omitting those records**. This is intentional: a complete dataset is preferable to a misleading partial extract.
