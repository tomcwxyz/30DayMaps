from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from shapely.geometry import box

from maps.trigs import parse_pillars, rank_extremes, add_visits, in_area, archive_rows


def example_rows():
    return pd.DataFrame([
        {"TYPE OF MARK":"pillar", "EASTING":"400000", "NORTHING":"500000", "HEIGHT":"100.1", "DESTROYED MARK INDICATOR":"0", "New Name":"A", "Trig Name":"Alpha"},
        {"TYPE OF MARK":"pillar", "EASTING":"410000", "NORTHING":"510000", "HEIGHT":"200.4", "DESTROYED MARK INDICATOR":"0", "New Name":"B", "Trig Name":"Bravo"},
        {"TYPE OF MARK":"pillar", "EASTING":"430000", "NORTHING":"520000", "HEIGHT":"80", "DESTROYED MARK INDICATOR":"1", "New Name":"C", "Trig Name":"Charlie"},
        {"TYPE OF MARK":"surface block", "EASTING":"420000", "NORTHING":"520000", "HEIGHT":"99", "DESTROYED MARK INDICATOR":"0", "New Name":"D", "Trig Name":"Delta"},
        {"TYPE OF MARK":"pillar", "EASTING":"600000", "NORTHING":"650000", "HEIGHT":"550", "DESTROYED MARK INDICATOR":"0", "New Name":"E", "Trig Name":"Echo"},
    ])


def test_filters_only_pillars_and_destroyed_flag():
    pillars = parse_pillars(example_rows())
    assert len(pillars) == 4
    assert pillars.loc[pillars.station_id.eq("C"), "destroyed_in_archive"].item()
    assert "D" not in pillars.station_id.values
    assert pillars.crs.to_epsg() == 27700


def test_extremes_rank_english_candidates_with_gb_reference():
    all_gb = parse_pillars(example_rows())
    england = in_area(all_gb, box(390000, 490000, 450000, 550000))
    high, isolated = rank_extremes(england, all_gb, n=5)
    assert high.iloc[0].station_id == "B"
    assert set(isolated.station_id) == {"A", "B"}  # Destroyed excluded
    assert isolated.iloc[0].nearest_pillar_km > 0


def test_visits_do_not_assume_unrecorded_are_unvisited():
    pillars = parse_pillars(example_rows())
    visits = pd.DataFrame({"station_id": ["B"], "visited": [True]})
    merged = add_visits(pillars, visits)
    assert merged.loc[merged.station_id.eq("B"), "visited"].item()
    assert not merged.loc[merged.station_id.eq("A"), "visited"].item()


def test_archive_zip_reader(tmp_path):
    path = tmp_path / "trigs.zip"
    with ZipFile(path, "w") as z:
        z.writestr("historical.csv", example_rows().to_csv(index=False))
    assert len(archive_rows(path)) == 5
