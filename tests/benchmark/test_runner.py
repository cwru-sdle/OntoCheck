"""End-to-end tests for the dependency-free benchmark runner."""

import json
import tempfile
import unittest
from pathlib import Path

from rdflib import RDFS, URIRef

from ontocheck.benchmark import (
    ReasonerAnswer,
    ReasonerRegistry,
    parse_suite,
    run_suite,
    write_result,
)


ONTOLOGY = """\
@prefix ex: <https://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:SampleA a ex:Material .
ex:Leaf rdfs:subClassOf ex:Middle .
ex:Middle rdfs:subClassOf ex:Root .
"""


def suite_data():
    return {
        "schema_version": "1.0",
        "suite_id": "tiny-v1",
        "domain": "test",
        "namespaces": {
            "ex": "https://example.org/",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        },
        "inference": {"profile": "none"},
        "cases": [
            {
                "id": "select-001",
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
            },
            {
                "id": "ask-001",
                "level": "fact_retrieval",
                "task_type": "fact_retrieval",
                "prompt": "Is SampleA a material?",
                "query": {
                    "language": "sparql",
                    "text": "ASK { ex:SampleA a ex:Material . }",
                },
                "expected": {"kind": "boolean", "values": True},
            },
        ],
    }


class BenchmarkRunnerTests(unittest.TestCase):
    def test_runs_select_and_ask_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")

            result = run_suite(parse_suite(suite_data()), ontology_path)

        self.assertEqual(result.score, 1.0)
        self.assertEqual([case.status for case in result.results], ["success"] * 2)
        self.assertEqual(result.results[0].actual, ["ex:SampleA"])

    def test_unknown_task_type_is_a_visible_failure(self):
        data = suite_data()
        data["cases"][0]["task_type"] = "future_task"
        data["cases"] = data["cases"][:1]

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(parse_suite(data), ontology_path)

        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.results[0].status, "error")
        self.assertIn("No evaluator registered", result.results[0].diagnostics[0])

    def test_graph_path_deduction_returns_proof(self):
        data = suite_data()
        data["inference"]["profile"] = "graph_path"
        data["cases"] = [
            {
                "id": "deduce-001",
                "level": "complex_reasoning",
                "task_type": "deduction",
                "prompt": "What is Leaf's ancestor after two subclass steps?",
                "query": {
                    "language": "graph_path",
                    "source": "ex:Leaf",
                    "predicate": "rdfs:subClassOf",
                    "min_hops": 2,
                    "max_hops": 2,
                },
                "expected": {
                    "kind": "result_set",
                    "values": ["ex:Root"],
                },
                "evidence": {
                    "required_paths": [
                        [
                            "ex:Leaf",
                            "rdfs:subClassOf",
                            "ex:Middle",
                            "rdfs:subClassOf",
                            "ex:Root",
                        ]
                    ]
                },
                "scoring": {
                    "answer_weight": 0.7,
                    "evidence_weight": 0.3,
                },
            }
        ]

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(parse_suite(data), ontology_path)

        case_result = result.results[0]
        self.assertEqual(case_result.score, 1.0)
        self.assertEqual(case_result.actual[0]["hops"], 2)
        self.assertTrue(case_result.actual[0]["inferred"])
        self.assertTrue(
            all(step["asserted"] for step in case_result.actual[0]["proof_steps"])
        )
        self.assertEqual(case_result.evidence_score, 1.0)

    def test_contextual_summary_combines_grounded_sections(self):
        data = suite_data()
        data["cases"] = [
            {
                "id": "summary-001",
                "level": "contextual_summarization",
                "task_type": "contextual_summary",
                "prompt": "Summarize the sample and class hierarchy.",
                "query": {
                    "language": "sparql_summary",
                    "sections": [
                        {
                            "id": "materials",
                            "query": (
                                "SELECT ?item WHERE "
                                "{ ?item a ex:Material . }"
                            ),
                        },
                        {
                            "id": "hierarchy",
                            "query": (
                                "SELECT ?parent WHERE "
                                "{ ex:Leaf rdfs:subClassOf ?parent . }"
                            ),
                        },
                    ],
                },
                "expected": {
                    "kind": "structured_summary",
                    "values": {
                        "materials": ["ex:SampleA"],
                        "hierarchy": ["ex:Middle"],
                    },
                },
            }
        ]

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(parse_suite(data), ontology_path)

        case_result = result.results[0]
        self.assertEqual(case_result.score, 1.0)
        self.assertEqual(case_result.metrics["coverage"], 1.0)
        self.assertEqual(case_result.metrics["faithfulness"], 1.0)
        self.assertEqual(
            case_result.actual["sections"]["hierarchy"], ["ex:Middle"]
        )

    def test_contextual_summary_scores_expected_mismatch(self):
        data = suite_data()
        data["cases"] = [
            {
                "id": "summary-mismatch",
                "level": "contextual_summarization",
                "task_type": "contextual_summary",
                "prompt": "Summarize two ontology fragments.",
                "query": {
                    "language": "sparql_summary",
                    "sections": [
                        {
                            "id": "materials",
                            "query": (
                                "SELECT ?item WHERE "
                                "{ ?item a ex:Material . }"
                            ),
                        },
                        {
                            "id": "hierarchy",
                            "query": (
                                "SELECT ?parent WHERE "
                                "{ ex:Leaf rdfs:subClassOf ?parent . }"
                            ),
                        },
                    ],
                },
                "expected": {
                    "kind": "structured_summary",
                    "values": {
                        "materials": ["ex:SampleA"],
                        "hierarchy": ["ex:Root"],
                    },
                },
            }
        ]

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(parse_suite(data), ontology_path)

        case_result = result.results[0]
        self.assertEqual(case_result.status, "success")
        self.assertEqual(case_result.score, 0.5)
        self.assertEqual(case_result.metrics["coverage"], 0.5)
        self.assertTrue(case_result.diagnostics)

    def test_contextual_summary_rejects_duplicate_sections(self):
        data = suite_data()
        data["cases"] = [
            {
                "id": "summary-invalid",
                "level": "contextual_summarization",
                "task_type": "contextual_summary",
                "prompt": "Invalid duplicate summary sections.",
                "query": {
                    "language": "sparql_summary",
                    "sections": [
                        {
                            "id": "same",
                            "query": "SELECT ?item WHERE { ?item a ex:Material . }",
                        },
                        {
                            "id": "same",
                            "query": "SELECT ?item WHERE { ?item a ex:Material . }",
                        },
                    ],
                },
                "expected": {
                    "kind": "structured_summary",
                    "values": {"same": ["ex:SampleA"]},
                },
            }
        ]

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(parse_suite(data), ontology_path)

        self.assertEqual(result.results[0].status, "error")
        self.assertIn("duplicate summary section", result.results[0].diagnostics[0])

    def test_graph_path_rejects_non_transitive_predicate(self):
        data = suite_data()
        data["inference"]["profile"] = "graph_path"
        data["cases"] = [
            {
                "id": "invalid-deduction",
                "level": "complex_reasoning",
                "task_type": "deduction",
                "prompt": "Follow a relation that is not transitive.",
                "query": {
                    "language": "graph_path",
                    "source": "ex:Leaf",
                    "predicate": "ex:related",
                    "min_hops": 1,
                    "max_hops": 2,
                },
                "expected": {"kind": "result_set", "values": []},
            }
        ]

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(parse_suite(data), ontology_path)

        self.assertEqual(result.results[0].status, "error")
        self.assertIn("not declared transitive", result.results[0].diagnostics[0])

    def test_reasoner_registry_accepts_an_external_adapter(self):
        class StaticReasoner:
            name = "static-test"

            def reason(self, case, graph):
                leaf = URIRef("https://example.org/Leaf")
                root = URIRef("https://example.org/Root")
                return [ReasonerAnswer(root, ((leaf, RDFS.subClassOf, root),))]

        data = suite_data()
        data["inference"]["profile"] = "external"
        data["cases"][0]["task_type"] = "deduction"
        data["cases"][0]["query"] = {
            "language": "external_query",
        }
        data["cases"][0]["expected"]["values"] = ["ex:Root"]
        reasoners = ReasonerRegistry()
        reasoners.register("external", StaticReasoner())

        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(
                parse_suite(data), ontology_path, reasoners=reasoners
            )

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.results[0].evaluator, "deduction-v1+static-test")

    def test_writes_machine_readable_result(self):
        with tempfile.TemporaryDirectory() as directory:
            ontology_path = Path(directory) / "tiny.ttl"
            result_path = Path(directory) / "result.json"
            ontology_path.write_text(ONTOLOGY, encoding="utf-8")
            result = run_suite(parse_suite(suite_data()), ontology_path)

            write_result(result, result_path)
            stored = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(stored["suite_id"], "tiny-v1")
        self.assertEqual(stored["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
