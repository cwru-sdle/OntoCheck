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


def valid_v2_suite():
    data = valid_suite()
    data["schema_version"] = "2.0"
    data["context"] = {
        "ontology_version": "tiny-ontology-v1",
        "ontology_commit": "abc123",
        "data_version": "tiny-data-v1",
        "data_commit": "def456",
        "metric_version": "strict-set-v1",
    }
    data["cases"][0].update(
        {
            "family_id": "material-sample",
            "split": "test",
            "leakage_group": "material-sample",
            "provenance": {
                "sources": ["fixture:tiny.ttl"],
                "curator": "test-suite",
                "reviewers": ["test-reviewer"],
            },
            "assumptions": ["The fixture is the complete test graph."],
            "constraints": ["Answers must be named RDF resources."],
        }
    )
    data["cases"][0]["evidence"] = {
        "required_claims": ["SampleA is a Material."],
        "source_ids": ["fixture:sample-a"],
    }
    return data


def valid_v2_constrained_suite():
    data = valid_v2_suite()
    case = data["cases"][0]
    case.update(
        {
            "level": "constrained_generation",
            "task_type": "constrained_plan",
            "query": {
                "language": "sparql_constraints",
                "checks": [
                    {
                        "id": "sample-is-material",
                        "query": "ASK { ex:SampleA a ex:Material . }",
                    }
                ],
            },
            "expected": {
                "kind": "constraint_checks",
                "values": {"sample-is-material": "entailed"},
            },
            "scoring": {
                "answer_weight": 0,
                "constraint_weight": 1,
            },
        }
    )
    return data


class ParseSuiteTests(unittest.TestCase):
    def test_parses_valid_suite(self):
        suite = parse_suite(valid_suite())

        self.assertEqual(suite.suite_id, "tiny-v1")
        self.assertEqual(suite.cases[0].task_type, "fact_retrieval")

    def test_parses_v2_context_and_guardrails(self):
        suite = parse_suite(valid_v2_suite())
        case = suite.cases[0]

        self.assertEqual(suite.context.ontology_commit, "abc123")
        self.assertEqual(case.family_id, "material-sample")
        self.assertEqual(case.split, "test")
        self.assertEqual(case.provenance.sources, ("fixture:tiny.ttl",))
        self.assertEqual(
            case.evidence.required_claims,
            ("SampleA is a Material.",),
        )

    def test_v2_requires_reproducibility_context(self):
        data = valid_v2_suite()
        del data["context"]["data_commit"]

        with self.assertRaisesRegex(
            BenchmarkValidationError, "context.data_commit"
        ):
            parse_suite(data)

    def test_v2_requires_case_provenance(self):
        data = valid_v2_suite()
        data["cases"][0]["provenance"]["sources"] = []

        with self.assertRaisesRegex(
            BenchmarkValidationError, "provenance.sources"
        ):
            parse_suite(data)

    def test_v2_requires_leakage_group(self):
        data = valid_v2_suite()
        del data["cases"][0]["leakage_group"]

        with self.assertRaisesRegex(
            BenchmarkValidationError, "leakage_group"
        ):
            parse_suite(data)

    def test_v2_constrained_generation_requires_guardrails(self):
        data = valid_v2_suite()
        case = data["cases"][0]
        case["level"] = "constrained_generation"
        case["assumptions"] = []

        with self.assertRaisesRegex(
            BenchmarkValidationError, "assumptions must not be empty"
        ):
            parse_suite(data)

    def test_v2_constrained_plan_requires_matching_level(self):
        data = valid_v2_constrained_suite()
        data["cases"][0]["level"] = "fact_retrieval"

        with self.assertRaisesRegex(
            BenchmarkValidationError, "requires level constrained_generation"
        ):
            parse_suite(data)

    def test_v2_constrained_plan_rejects_duplicate_checks(self):
        data = valid_v2_constrained_suite()
        check = data["cases"][0]["query"]["checks"][0]
        data["cases"][0]["query"]["checks"].append(copy.deepcopy(check))

        with self.assertRaisesRegex(
            BenchmarkValidationError, "duplicate IDs"
        ):
            parse_suite(data)

    def test_v2_constrained_plan_rejects_answer_weight(self):
        data = valid_v2_constrained_suite()
        data["cases"][0]["scoring"]["answer_weight"] = 1

        with self.assertRaisesRegex(
            BenchmarkValidationError, "only a positive constraint_weight"
        ):
            parse_suite(data)

    def test_v1_ignores_v2_extension_fields(self):
        data = valid_suite()
        data["context"] = "legacy extension"
        data["cases"][0]["provenance"] = "legacy extension"
        data["cases"][0]["family_id"] = []
        data["cases"][0]["evidence"] = {
            "required_claims": "legacy extension"
        }

        suite = parse_suite(data)

        self.assertEqual(suite.context.ontology_version, "")
        self.assertEqual(suite.cases[0].evidence.required_claims, ())

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
