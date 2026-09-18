"""CLI integration tests for executable benchmark suites."""

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ontocheck.cli import main


ROOT = Path(__file__).resolve().parents[2]
XRD_SUITE = ROOT / "SupplementaryMaterials/Benchmarks/XRD-graph-path.json"
XRD_ONTOLOGY = ROOT / "SupplementaryMaterials/Ontologies/XRD.ttl"


class BenchmarkCliTests(unittest.TestCase):
    def test_runs_benchmark_and_writes_json_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            argv = [
                "ontocheck",
                str(XRD_ONTOLOGY),
                "--benchmark",
                str(XRD_SUITE),
                "--benchmark-output",
                str(output),
            ]
            stdout = StringIO()
            with patch("sys.argv", argv), redirect_stdout(stdout):
                exit_code = main()
            stored = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stored["score"], 1.0)
        self.assertIn("xrd-summary-001: success", stdout.getvalue())

    def test_returns_failure_when_a_benchmark_case_errors(self):
        ontology = """\
@prefix ex: <https://example.org/> .
ex:A ex:related ex:B .
"""
        suite = {
            "schema_version": "1.0",
            "suite_id": "invalid-reasoning",
            "domain": "test",
            "namespaces": {"ex": "https://example.org/"},
            "inference": {"profile": "graph_path"},
            "cases": [
                {
                    "id": "invalid-path",
                    "level": "complex_reasoning",
                    "task_type": "deduction",
                    "prompt": "Follow an undeclared transitive relation.",
                    "query": {
                        "language": "graph_path",
                        "source": "ex:A",
                        "predicate": "ex:related",
                    },
                    "expected": {"kind": "result_set", "values": ["ex:B"]},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "ontology.ttl"
            suite_path = Path(directory) / "suite.json"
            output_path = Path(directory) / "result.json"
            ontology_path.write_text(ontology, encoding="utf-8")
            suite_path.write_text(json.dumps(suite), encoding="utf-8")
            argv = [
                "ontocheck",
                str(ontology_path),
                "--benchmark",
                str(suite_path),
                "--benchmark-output",
                str(output_path),
            ]
            with patch("sys.argv", argv), redirect_stdout(
                StringIO()
            ), redirect_stderr(StringIO()):
                exit_code = main()
            stored = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(stored["results"][0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
