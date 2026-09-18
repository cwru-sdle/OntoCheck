"""Tests for benchmark suite validation."""

import copy
import unittest

from ontocheck.benchmark import BenchmarkValidationError, parse_suite


def valid_suite():
    return {
        "schema_version": "1.0",
        "suite_id": "tiny-v1",
        "domain": "test",
        "namespaces": {"ex": "https://example.org/"},
        "inference": {"profile": "none"},
        "cases": [
            {
                "id": "retrieve-001",
                "level": "fact_retrieval",
                "task_type": "fact_retrieval",
                "prompt": "Which samples are materials?",
                "query": {
                    "language": "sparql",
                    "text": "SELECT ?sample WHERE { ?sample a ex:Material . }",
                },
                "expected": {
                    "kind": "result_set",
                    "values": ["ex:SampleA"],
                },
            }
        ],
    }


class ParseSuiteTests(unittest.TestCase):
    def test_parses_valid_suite(self):
        suite = parse_suite(valid_suite())

        self.assertEqual(suite.suite_id, "tiny-v1")
        self.assertEqual(suite.cases[0].task_type, "fact_retrieval")

    def test_rejects_duplicate_case_ids(self):
        data = valid_suite()
        data["cases"].append(copy.deepcopy(data["cases"][0]))

        with self.assertRaisesRegex(
            BenchmarkValidationError, "Duplicate case IDs"
        ):
            parse_suite(data)

    def test_rejects_zero_total_weight(self):
        data = valid_suite()
        data["cases"][0]["scoring"] = {
            "answer_weight": 0,
            "evidence_weight": 0,
            "constraint_weight": 0,
        }

        with self.assertRaisesRegex(
            BenchmarkValidationError, "at least one positive weight"
        ):
            parse_suite(data)


if __name__ == "__main__":
    unittest.main()
