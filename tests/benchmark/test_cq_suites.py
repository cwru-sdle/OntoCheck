"""Regression tests for the competency-question benchmark suites."""

import unittest
from pathlib import Path

from ontocheck.benchmark import run_suite


ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ROOT / "SupplementaryMaterials/Benchmarks"
ONTOLOGIES = ROOT / "SupplementaryMaterials/Ontologies"

# Suite, ontology files, and the cases each ontology does not yet pass.
SUITES = {
    "EBSD-cq.json": (["EBSD.ttl"],
                     {"ebsd-retrieval-001", "ebsd-plan-001"}),
    "Capacitors-cq.json": (["Capacitor-Equipment.ttl", "Capacitor-Sample.ttl",
                            "Capacitor-SampleHolder.ttl"],
                           {"capacitors-retrieval-001", "capacitors-summary-001"}),
    "GeoOutage-cq.json": (["GeoOutage.ttl"], {"geooutage-plan-001"}),
    "Geospatial-cq.json": (["Geospatial-Rasters.ttl",
                            "Geospatial-SatelliteSensorBand.ttl",
                            "Geospatial-mdsGeo.ttl"], set()),
}


class CqSuiteTests(unittest.TestCase):
    def test_suites_run_and_report_known_gaps(self):
        for suite, (files, gaps) in SUITES.items():
            with self.subTest(suite=suite):
                result = run_suite(BENCHMARKS / suite,
                                   [ONTOLOGIES / f for f in files])
                self.assertEqual(len(result.results), 4)
                self.assertTrue(all(c.status == "success" for c in result.results))
                self.assertEqual({c.case_id for c in result.results
                                  if c.score < 1.0}, gaps)


if __name__ == "__main__":
    unittest.main()
