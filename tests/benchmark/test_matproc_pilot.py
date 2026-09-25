"""Regression tests for the Materials Processing competency pilot."""

import unittest
from pathlib import Path

from ontocheck.benchmark import run_suite


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "SupplementaryMaterials/Benchmarks/MatProc-sps.json"
ONTOLOGY = ROOT / "SupplementaryMaterials/Ontologies/MatProc.ttl"


class MatProcPilotTests(unittest.TestCase):
    def test_linked_sps_family_covers_all_four_levels(self):
        result = run_suite(SUITE, ONTOLOGY)
        cases = {case.case_id: case for case in result.results}

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.context.ontology_version, "matproc-0.3.2.0")
        self.assertEqual(
            set(cases),
            {
                "matproc-retrieval-001",
                "matproc-deduction-001",
                "matproc-summary-001",
                "matproc-plan-001",
            },
        )

        retrieval = cases["matproc-retrieval-001"]
        self.assertEqual(retrieval.status, "success")
        self.assertEqual(
            set(retrieval.actual),
            {
                "mds:PulsedCurrent",
                "mds:SinteringPressure",
                "mds:SinteringTemperature",
            },
        )

        deduction = cases["matproc-deduction-001"]
        self.assertEqual(deduction.status, "success")
        self.assertEqual(
            deduction.actual[0]["value"], "mds:MaterialsProcessing"
        )
        self.assertEqual(deduction.actual[0]["hops"], 2)
        self.assertEqual(deduction.evidence_score, 1.0)

        summary = cases["matproc-summary-001"]
        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.metrics["coverage"], 1.0)
        self.assertEqual(
            summary.actual["sections"]["standards"],
            ['"ISO 18755:2020"'],
        )

        plan = cases["matproc-plan-001"]
        self.assertEqual(plan.status, "success")
        self.assertEqual(plan.constraint_score, 1.0)
        self.assertFalse(plan.unsupported_claims)
        self.assertEqual(
            plan.actual["checks"]["pulsed-current-parameter"],
            "entailed",
        )


if __name__ == "__main__":
    unittest.main()
