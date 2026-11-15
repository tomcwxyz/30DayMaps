"""Summit names as they print, and the route builder's summit matching and trimming."""
import pytest

from maps.peaks import label
from maps.peaks_routes import join, snap


@pytest.mark.parametrize("raw, printed", [
    ("High Stile (summit)", "High Stile"),
    ("Bakestall (Wainwright summit)", "Bakestall"),
    ("Scar Crags (Wainwright)", "Scar Crags"),
    ("Gowbarrow Fell Summit", "Gowbarrow Fell"),
    ("Mallie SIde", "Mallie Side"),
    ("Third Crinkle (Gunson Knott)", "Third Crinkle (Gunson Knott)"),   # a real second name stays
    ("Y Lliwedd (East Peak)", "Y Lliwedd (East Peak)"),
    ("McDonald Hill", "McDonald Hill"),
])
def test_summit_names_print_without_osm_bookkeeping(raw, printed):
    assert label(raw) == printed


OSM = [("Yewbarrow North Top", 54.471358, -3.2733096, "616.6"), ("Yewbarrow", 54.4649007, -3.2768237, "628.7"),
       ("Scar Crags (summit)", 54.575013, -3.2259289, "672")]


def test_an_exact_name_beats_a_nearer_subsidiary_top():
    (got,) = snap([("Yewbarrow", 54.4685, -3.273, "peak")], OSM)
    assert got[1:3] == (54.4649007, -3.2768237)


def test_bookkeeping_in_the_osm_name_still_matches_exactly():
    (got,) = snap([("Scar Crags", 54.5747, -3.226, "peak")], OSM)
    assert got[1:3] == (54.575013, -3.2259289)


def test_a_summit_with_no_osm_match_stops_the_build():
    with pytest.raises(SystemExit, match="Hopegill Head"):
        snap([("Hopegill Head", 54.5869, -3.2337, "peak")], OSM)   # the old hint, 1.8 km out


OUT = [(54.0, -3.0, 0), (54.001, -3.0, 0), (54.002, -3.0, 0)]
BACK_AND_ON = [(54.002, -3.0, 0), (54.001, -3.0, 0), (54.001, -3.001, 0)]


def test_a_dead_end_to_a_via_point_is_trimmed():
    assert [p[:2] for p in join(join([], OUT, False), BACK_AND_ON, True)] == [(54.0, -3.0), (54.001, -3.0), (54.001, -3.001)]


def test_an_out_and_back_to_a_summit_is_kept():
    assert len(join(join([], OUT, False), BACK_AND_ON, False)) == 5
