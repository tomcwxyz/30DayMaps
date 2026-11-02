import pandas as pd
import pytest
from shapely.geometry import box
from maps.buses import clean_stops, group_stop_locations, rank_isolated_locations


def stops_example():
    return pd.DataFrame([
        dict(ATCOCode="A1",StopType="BCT",Status="active",Easting=100,Northing=100,CommonName="Farm Road",NptgLocalityCode="L1"),
        dict(ATCOCode="A2",StopType="BCT",Status="active",Easting=130,Northing=100,CommonName="Farm Road",NptgLocalityCode="L1"),
        dict(ATCOCode="B1",StopType="BCT",Status="active",Easting=600,Northing=100,CommonName="Other Road",NptgLocalityCode="L1"),
        dict(ATCOCode="C1",StopType="BCT",Status="active",Easting=1000,Northing=100,CommonName="Border",NptgLocalityCode="L2"),
        dict(ATCOCode="D1",StopType="BCT",Status="inactive",Easting=100,Northing=300,CommonName="Old",NptgLocalityCode="L1"),
        dict(ATCOCode="E1",StopType="BCE",Status="active",Easting=100,Northing=200,CommonName="Entrance",NptgLocalityCode="L1"),
    ])


def test_non_bus_and_inactive_excluded():
    stops = clean_stops(stops_example())
    assert set(stops.ATCOCode) == {"A1", "A2", "B1", "C1"}


def test_nearby_opposite_sides_are_one_location():
    groups = group_stop_locations(clean_stops(stops_example()))
    assert groups.set_index("ATCOCode").loc["A1", "location_id"] == groups.set_index("ATCOCode").loc["A2", "location_id"]
    assert groups.location_id.nunique() == 3


def test_exact_distance_to_other_group_not_opposite_platform():
    ranked = rank_isolated_locations(clean_stops(stops_example()))
    ids = set(ranked.ATCOCode)
    assert "A1" in ids or "A2" in ids
    assert len(ranked) == 3
    first_group = ranked[ranked.CommonName.eq("Farm Road")].iloc[0]
    assert first_group.nearest_other_location_m == pytest.approx(470)


def test_filter_to_england_but_use_border_neighbor():
    ranked = rank_isolated_locations(clean_stops(stops_example()), england_geometry=box(0, 0, 700, 700))
    assert "C1" not in set(ranked.ATCOCode)
    assert "B1" in set(ranked.ATCOCode)
    b = ranked[ranked.ATCOCode.eq("B1")].iloc[0]
    assert b.nearest_other_location_m == pytest.approx(400)  # Border stop considered


def test_distinct_stops_same_street_but_not_same_name_stay_separate():
    rows = stops_example().copy()
    rows.loc[1, "CommonName"] = "Different stop"
    groups = group_stop_locations(clean_stops(rows))
    assert groups.location_id.nunique() == 4