import json
import pytest

from maps.woods_wales import fetch_wales


class FakeResponse:
    def __init__(self, features):
        self.features = features

    def raise_for_status(self):
        pass

    def json(self):
        return {"type": "FeatureCollection", "features": self.features}


class FakeWFS:
    def __init__(self):
        self.starts = []

    def get(self, url, *, params, timeout):
        self.starts.append(params["startIndex"])
        start = params["startIndex"]
        if start >= 4:
            return FakeResponse([])
        return FakeResponse([
            {"type": "Feature", "id": f"wood.{x}", "properties": {},
             "geometry": {"type": "Polygon",
                          "coordinates": [[[-4,52],[-3.9,52],[-3.9,52.1],[-4,52]]]}}
            for x in range(start, min(start+2, 4))
        ])


def test_wales_wfs_paginates_and_never_silently_truncates(tmp_path):
    client = FakeWFS()
    out = fetch_wales(tmp_path / "wales.geojson", page_size=2, session=client)
    data = json.loads(out.read_text())
    assert len(data["features"]) == 4
    assert client.starts == [0, 2, 4]


class RepeatingWFS:
    def get(self, url, *, params, timeout):
        return FakeResponse([
            {"type": "Feature", "id": "same",
             "geometry": {"type": "Polygon",
                          "coordinates": [[[-4,52],[-3.9,52],[-3.9,52.1],[-4,52]]]}}
            for _ in range(2)
        ])


def test_repeated_features_rejected_and_partial_file_removed(tmp_path):
    with pytest.raises(RuntimeError, match="repeated a feature ID"):
        fetch_wales(tmp_path / "wales.geojson", page_size=2, session=RepeatingWFS())
    assert not (tmp_path / "wales.geojson").exists()
    assert not (tmp_path / "wales.geojson.part").exists()
