"""Offline tests for the Day 04 NBN spatial cluster method."""
import pytest
from shapely.geometry import shape

from maps import moss_clusters as clusters


def synthetic_cell(grid, species, count=1):
    return {"type": "Feature", "properties": {
        "grid": grid, "species": dict.fromkeys(species, count)
    }, "geometry": None}


def make_dataset(*cells):
    return {"type": "FeatureCollection", "features": list(cells)}


def test_national_grid_conversion_has_correct_axes():
    assert clusters.grid_key("NZ25") == ("GB", 42, 55)
    assert clusters.grid_key("NZ26") == ("GB", 42, 56)
    assert clusters.grid_key("NZ35") == ("GB", 43, 55)
    assert clusters.grid_key("J38")[0] == "NI"
    with pytest.raises(ValueError):
        clusters.grid_key("NOT-A-GRID")


def test_adjacency_includes_diagonals_but_not_distant_cells():
    cells = {
        ("GB", 1, 1): {}, ("GB", 2, 2): {}, ("GB", 3, 3): {},
        ("GB", 8, 8): {}, ("GB", 9, 8): {},
    }
    components = clusters.neighbouring_components(cells)
    assert len(components) == 1
    assert len(components[0]) == 3


def test_two_grid_systems_never_connect():
    cells = {("GB", 1, 1): {}, ("GB", 1, 2): {},
             ("NI", 1, 1): {}, ("NI", 1, 2): {}}
    assert clusters.neighbouring_components(cells, min_cells=3) == []


def test_reproducible_species_richness_clusters():
    all_species = list(clusters.GROUPS["all"])
    data = make_dataset(*[
        synthetic_cell(ref, all_species, 15)
        for ref in ["NZ25", "NZ26", "NZ35", "NZ55"]])
    output, metadata = clusters.compile_clusters(data, {"generated_at": "2026-11-03"})
    features = [f for f in output["features"]
                if f["properties"]["group"] == "all" and f["properties"]["level"] == "focus"]
    assert len(features) == 1
    candidate = features[0]
    assert candidate["properties"]["cell_count"] == 3
    assert candidate["properties"]["species_count"] == 8
    assert candidate["properties"]["observations"] == 3 * 8 * 15
    assert candidate["properties"]["grid_refs"] == ["NZ25", "NZ26", "NZ35"]
    assert shape(candidate["geometry"]).is_valid
    assert metadata["profiles"]["all-focus"]["eligible_cells"] == 4
    assert metadata["profiles"]["all-focus"]["cells_in_clusters"] == 3


def test_bog_cooccurrence_not_merely_sphagnum_presence():
    bog = list(clusters.GROUPS["bog"])
    data = make_dataset(
        synthetic_cell("NZ25", bog),
        synthetic_cell("NZ26", bog),
        synthetic_cell("NZ35", bog),
        synthetic_cell("NZ36", [bog[0]], 50),
    )
    output, report = clusters.compile_clusters(data)
    broad = [f for f in output["features"]
             if f["properties"]["group"] == "bog" and f["properties"]["level"] == "broad"]
    assert len(broad) == 1
    assert broad[0]["properties"]["cell_count"] == 3
    assert report["profiles"]["bog-focus"]["clusters"] == 0


def test_empty_data_is_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        clusters.compile_clusters({"type": "FeatureCollection", "features": []})


def test_duplicate_grid_is_rejected():
    data = make_dataset(synthetic_cell("NZ25", []), synthetic_cell("NZ25", []))
    with pytest.raises(ValueError, match="Duplicate"):
        clusters.compile_clusters(data)


def test_mixed_projection_fails_footprint():
    with pytest.raises(ValueError, match="two different national grid"):
        clusters.cluster_footprint([("GB", 42, 55), ("NI", 42, 55)])
