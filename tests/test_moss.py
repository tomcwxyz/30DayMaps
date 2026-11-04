import pytest
from maps import moss

@pytest.mark.parametrize(("name", "expected"), [
    ("CC0", True), ("CC-BY", True), ("CC BY 4.0", True),
    ("OGL", True), ("Open Government Licence", True),
    ("CC-BY-NC", False), ("CC BY-ND", False), ("unknown", False),
])
def test_licences(name, expected):
    assert moss.open_licence(name) is expected

@pytest.mark.parametrize("grid", ["NZ25", "SK53", "TQ28", "HP61", "J38"])
def test_grid_reference(grid):
    ring = moss.square(grid)
    assert ring is not None
    assert len(ring) == 5
    assert ring[0] == ring[-1]

def test_north_east_location():
    ring = moss.square("NZ25")
    lon = sum(p[0] for p in ring[:4]) / 4
    lat = sum(p[1] for p in ring[:4]) / 4
    assert -1.9 < lon < -1.3 and 54.8 < lat < 55.0

def test_facet_api_formats():
    rows = [{"label": "CC-BY", "count": 10}]
    assert moss.facet_rows({"facetResults": [
        {"fieldName": "license", "fieldResult": rows}]}, "license") == rows
    assert moss.facet_rows({"facetResults": {"fieldResult": [
        {"fieldName": "license", "fieldResult": rows}]}}, "license") == rows

def test_exclude_noncommercial(monkeypatch):
    monkeypatch.setattr(moss, "SPECIES", {"Grimmia pulvinata": ("Grimmia", "Stone")})
    monkeypatch.setattr(moss, "resolve_tvk", lambda *a: None)
    def fake_query(session, species, fields, licence=None, tvk=None):
        if licence is None:
            return {"totalRecords": 80, "facetResults": [
                {"fieldName": "license", "fieldResult": [
                    {"label": "CC-BY", "count": 50},
                    {"label": "CC-BY-NC", "count": 30}]}]}
        assert licence == "CC-BY"
        return {"totalRecords": 50, "facetResults": [
            {"fieldName": "cl18", "fieldResult": [{"label": "NZ25", "count": 50}]},
            {"fieldName": "data_provider", "fieldResult": [{"label": "BBS", "count": 50}]}]}
    monkeypatch.setattr(moss, "query", fake_query)
    geojson, manifest = moss.retrieve(object())
    assert len(geojson["features"]) == 1
    assert geojson["features"][0]["properties"]["records"] == 50
    assert manifest["species"][0]["all_licence_records"] == 80

def test_no_unlicensed_data(monkeypatch):
    monkeypatch.setattr(moss, "SPECIES", {"Grimmia pulvinata": ("Grimmia", "Stone")})
    monkeypatch.setattr(moss, "query", lambda *a, **k: {"totalRecords": 10})
    with pytest.raises(ValueError, match="No licence facets"):
        moss.retrieve(object())
