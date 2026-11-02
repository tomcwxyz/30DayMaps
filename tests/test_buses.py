import pandas as pd
import pytest
from maps.buses import clean_stops, rank_isolated_locations


def test_non_bus_and_inactive_excluded():
    rows = pd.DataFrame([
        dict(ATCOCode="1",StopType="BCT",Status="active",Easting=100,Northing=100),
        dict(ATCOCode="2",StopType="BCT",Status="inactive",Easting=110,Northing=100),
        dict(ATCOCode="3",StopType="RLY",Status="active",Easting=130,Northing=100),
        dict(ATCOCode="4",StopType="BCT",Status="active",Easting=1000,Northing=100),
    ])
    clean = clean_stops(rows)
    assert set(clean.ATCOCode) == {"1", "4"}
    ranked = rank_isolated_locations(clean)
    assert len(ranked) == 2
    assert ranked.nearest_other_stop_m.iloc[0] == pytest.approx(900)
