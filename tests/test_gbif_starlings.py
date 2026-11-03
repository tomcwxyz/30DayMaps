import unittest
from unittest.mock import patch
from maps.gbif_starlings import licence_type, parse_record, fetch

class TestGbifStarlingDownloader(unittest.TestCase):
    def test_licences(self):
        self.assertEqual(licence_type("CC0_1_0"), "CC0")
        self.assertEqual(licence_type("CC_BY_4_0"), "CC BY 4.0")
        self.assertEqual(licence_type("http://creativecommons.org/licenses/by/4.0/legalcode"), "CC BY 4.0")
        self.assertIsNone(licence_type("CC_BY_NC_4_0"))
        self.assertIsNone(licence_type("unknown"))
    def test_record(self):
        rec = {"key":123,"decimalLatitude":54.2,"decimalLongitude":-1.57,"year":2025,"month":11,"countryCode":"GB","license":"CC_BY_4_0","datasetKey":"source"}
        row,error=parse_record(rec)
        self.assertIsNone(error)
        self.assertEqual(row["gbifID"],"123")
        self.assertEqual(row["licence"],"CC BY 4.0")
        for props, expected in [
            ({"license":"CC_BY_NC_4_0"},"licence"),
            ({"decimalLatitude":75},"bounding"),
            ({"countryCode":"FR"},"country"),
            ({"month":5},"date"),
        ]:
            with self.subTest(props=props):
                result,reason=parse_record({**rec,**props})
                self.assertIsNone(result)
                self.assertIn(expected,reason)
    def test_fetch_paginated(self):
        def rec(i):
            return {"key":i,"decimalLatitude":54+i*.001,"decimalLongitude":-2,"year":2025,"month":11,"countryCode":"GB","license":"CC0_1_0","datasetKey":"set","datasetName":"Test"}
        taxon={"usageKey":1234,"matchType":"EXACT","rank":"SPECIES","scientificName":"Sturnus vulgaris Linnaeus, 1758"}
        pages=[taxon,{"count":301,"results":[rec(i) for i in range(300)]},{"count":301,"results":[rec(300)]}]
        with patch("maps.gbif_starlings.get_json",side_effect=pages),patch("maps.gbif_starlings.time.sleep"):
            rows,meta=fetch()
        self.assertEqual(len(rows),301)
        self.assertEqual(meta["exported_records"],301)
        self.assertEqual(meta["dataset_attribution"][0]["records"],301)
    def test_no_silent_truncation(self):
        taxon={"usageKey":1234,"matchType":"EXACT","rank":"SPECIES","scientificName":"Sturnus vulgaris Linnaeus, 1758"}
        with patch("maps.gbif_starlings.get_json",side_effect=[taxon,{"count":30000,"results":[]}]):
            with self.assertRaisesRegex(RuntimeError,"above"):
                fetch()

if __name__ == "__main__":
    unittest.main()
