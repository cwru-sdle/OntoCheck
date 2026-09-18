"""Regression tests for the executable XRD benchmark pilot."""

import unittest
from pathlib import Path

from ontocheck.benchmark import run_suite


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "SupplementaryMaterials/Benchmarks/XRD-graph-path.json"
ONTOLOGY = ROOT / "SupplementaryMaterials/Ontologies/XRD.ttl"


class XrdPilotTests(unittest.TestCase):
    def test_expected_deduction_and_summary_results(self):
        result = run_suite(SUITE, ONTOLOGY)
        cases = {case.case_id: case for case in result.results}

        self.assertEqual(result.score, 1.0)
        self.assertEqual(set(cases), {"xrd-deduction-001", "xrd-summary-001"})

        deduction = cases["xrd-deduction-001"]
        self.assertEqual(deduction.status, "success")
        self.assertEqual(deduction.actual[0]["value"], "mds:ProcessingMethod")
        self.assertEqual(deduction.actual[0]["hops"], 2)
        self.assertTrue(deduction.actual[0]["inferred"])
        self.assertEqual(deduction.evidence_score, 1.0)

        summary = cases["xrd-summary-001"]
        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.metrics["coverage"], 1.0)
        self.assertEqual(summary.metrics["relevance"], 1.0)
        self.assertEqual(
            set(summary.actual["sections"]["aliases"]),
            {
                '"L-PBF"@en',
                '"LPBF"@en',
                '"SLM"@en',
                '"Selective Laser Melting"@en',
            },
        )
        self.assertEqual(
            summary.actual["sections"]["promoted_behavior"],
            ["mds:RapidSolidification"],
        )


if __name__ == "__main__":
    unittest.main()
