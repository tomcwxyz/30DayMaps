import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from maps.settlements import rank_far_from_built_up
from maps.buses import clean_stops


def fixture_stops():
    return clean_stops(pd.DataFrame([
        {"ATCOCode": "A1", "StopType": "BCT", "Status": "active", "Easting": 100, "Northing": 100, "CommonName": "Village", "NptgLocalityCode": "V"},
        {"ATCOCode": "A2", "StopType": "BCT", "Status": "active", "Easting": 110, "Northing": 100, "CommonName": "Village", "NptgLocalityCode": "V"},
        {"ATCOCode": "B1", "StopType": "BCT", "Status": "active", "Easting": 300, "Northing": 100, "CommonName": "Farm", "NptgLocalityCode": "F"},
        {"ATCOCode": "C1", "StopType": "BCT", "Status": "active", "Easting": 500, "Northing": 100, "CommonName": "Borders", "NptgLocalityCode": "B"},
    ]))


def fixture_areas():
    return gpd.GeoDataFrame({"BUA22NM": ["Town", "Cross-border hamlet"]},
                            geometry=[box(90,90,115,115), box(450,90,470,110)], crs="EPSG:27700")


def test_inside_built_up_has_zero_distance():
    ranks = rank_far_from_built_up(fixture_stops(), fixture_areas(), top_n=10)
    assert ranks.loc[ranks.ATCOCode.eq("A1"), "distance_to_built_up_m"].item() == pytest.approx(0)
    assert ranks.loc[ranks.ATCOCode.eq("B1"), "distance_to_built_up_m"].item() == pytest.approx(150)
    assert len(ranks) == 3  # Pair of same-name stops is one geographical location.


def test_english_candidates_use_cross_border_built_up_areas():
    ranked = rank_far_from_built_up(fixture_stops(), fixture_areas(), england_geometry=box(0,0,350,350))
    assert set(ranked.ATCOCode) == {"A1", "B1"}
    assert ranked.iloc[0].ATCOCode == "B1"
    assert ranked.iloc[0].nearest_built_up_name == "Cross-border hamlet"


def test_reject_empty_areas():
    with pytest.raises(ValueError):
        rank_far_from_built_up(fixture_stops(), fixture_areas().iloc[:0])