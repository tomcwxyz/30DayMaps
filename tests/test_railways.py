import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from maps.railways import (read_railway_lines, clip_lines, length_summary,
                          make_maps, railway_title)


def fixture_seq(tmp_path):
    records = [
        {"type": "Feature", "id": "way/1", "properties": {"railway": "abandoned", "name": "Old Branch"},
         "geometry": {"type": "LineString", "coordinates": [[-1.4, 54.5], [-1.39, 54.5]]}},
        {"type": "Feature", "id": "way/2", "properties": {"railway": "disused"},
         "geometry": {"type": "LineString", "coordinates": [[-1.42, 54.5], [-1.41, 54.5]]}},
        {"type": "Feature", "id": "way/3", "properties": {"railway": "rail"},
         "geometry": {"type": "LineString", "coordinates": [[-1.44, 54.5], [-1.43, 54.5]]}},
        {"type": "Feature", "id": "way/4", "properties": {"railway": "station"},
         "geometry": {"type": "Point", "coordinates": [-1.4, 54.5]}},
        {"type": "Feature", "id": "way/5", "properties": {"railway": "razed"},
         "geometry": {"type": "LineString", "coordinates": [[-1.45, 54.5], [-1.46, 54.5]]}},
    ]
    path = tmp_path / "railways.geojsonseq"
    path.write_text("".join("\x1e" + json.dumps(x) + "\n" for x in records))
    return path


def test_reads_osmium_geojsonseq_and_ignores_non_line(tmp_path):
    lines = read_railway_lines(fixture_seq(tmp_path))
    assert len(lines) == 4
    assert set(lines.status) == {"abandoned", "disused", "rail", "razed"}
    assert lines.crs.to_epsg() == 27700
    assert lines.osm_id.iloc[0] == "way/1"


def test_clip_uses_bng_metres_and_summarises(tmp_path):
    data = read_railway_lines(fixture_seq(tmp_path))
    bounds = box(*data.total_bounds)
    result = clip_lines(data, bounds)
    summary = length_summary(result)
    assert result.length_km.gt(0).all()
    assert set(summary.status) == {"abandoned", "disused", "rail", "razed"}
    assert summary.mapped_feature_km.sum() == pytest.approx(result.geometry.length.sum() / 1000)


def test_empty_data_is_rejected(tmp_path):
    path = tmp_path / "empty.geojsonseq"
    path.write_text('\x1e' + json.dumps({"type":"Feature","properties":{"railway":"station"},"geometry":{"type":"Point","coordinates":[0,0]}}) + '\n')
    with pytest.raises(ValueError, match="No usable railway ways"):
        read_railway_lines(path)


def test_renders_both_geographies_without_network(tmp_path):
    railway = read_railway_lines(fixture_seq(tmp_path))
    polygon = box(*railway.total_bounds).buffer(5000)
    border = gpd.GeoDataFrame({"RGN25CD": ["E12000001", "E12000002"]},
                              geometry=[polygon, box(0, 0, 100, 100)], crs=27700)
    boundary_path = tmp_path / "regions.geojson"
    border.to_file(boundary_path, driver="GeoJSON")
    out = tmp_path / "outputs"
    make_maps(fixture_seq(tmp_path), out, boundaries_path=boundary_path)
    for area in ("england", "north-east"):
        assert (out / f"{area}-railways.png").stat().st_size > 10000
        assert (out / f"{area}-railway-summary.csv").exists()
        assert (out / f"{area}-railways.gpkg").exists()


def test_title_is_not_passenger_service_claim():
    assert railway_title("england") == "The Railways We Lost"
    with pytest.raises(ValueError):
        railway_title("britain")

def test_north_east_only_mode_does_not_publish_partial_england_map(tmp_path):
    railway = read_railway_lines(fixture_seq(tmp_path))
    polygon = box(*railway.total_bounds).buffer(5000)
    border = gpd.GeoDataFrame({"RGN25CD": ["E12000001", "E12000002"]},
                              geometry=[polygon, box(0, 0, 100, 100)], crs=27700)
    boundary_path = tmp_path / "regions.geojson"
    border.to_file(boundary_path, driver="GeoJSON")
    out = tmp_path / "outputs"
    make_maps(fixture_seq(tmp_path), out, boundaries_path=boundary_path, area="north-east")
    assert (out / "north-east-railways.png").exists()
    assert not (out / "england-railways.png").exists()


def test_railway_source_signature_changes_on_updated_extract(tmp_path):
    from maps.railways import source_signature
    p = tmp_path / "rail.osm.pbf"
    p.write_bytes(b"old")
    old = source_signature(p)
    p.write_bytes(b"changed source file")
    assert source_signature(p) != old


def test_town_labels_are_reprojected_from_geographic_coordinates():
    from maps.railways import north_east_town_points
    towns = north_east_town_points().set_index("name")
    darlington = towns.loc["Darlington"].geometry
    middlesbrough = towns.loc["Middlesbrough"].geometry
    assert towns.crs.to_epsg() == 27700
    assert 426000 < darlington.x < 433000
    assert 510000 < darlington.y < 520000
    assert 445000 < middlesbrough.x < 455000
    assert 515000 < middlesbrough.y < 525000
    assert middlesbrough.x > darlington.x
    assert middlesbrough.y > darlington.y


def test_label_position_fails_if_town_outside_region():
    from maps.railways import draw_ne_town_labels
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="outside North East boundary"):
        draw_ne_town_labels(ax, box(0, 0, 100, 100))
    plt.close(fig)
