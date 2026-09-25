"""Execution tests for human-readable benchmark SPARQL companions."""

import unittest
from pathlib import Path

from rdflib import Graph

from ontocheck.task_based_metric import _extract_sparql_from_markdown


ROOT = Path(__file__).resolve().parents[2]


class SparqlCompanionTests(unittest.TestCase):
    def test_companion_queries_execute_with_nonempty_results(self):
        fixtures = (
            (
                "xrd",
                ROOT / "SupplementaryMaterials/Ontologies/XRD.ttl",
                ROOT
                / "SupplementaryMaterials/SPARQL_Queries/XRD-Benchmark.md",
            ),
            (
                "matproc",
                ROOT / "SupplementaryMaterials/Ontologies/MatProc.ttl",
                ROOT
                / "SupplementaryMaterials/SPARQL_Queries/MatProc-Benchmark.md",
            ),
        )

        for name, ontology_path, questions_path in fixtures:
            with self.subTest(suite=name):
                graph = Graph()
                graph.parse(ontology_path, format="turtle")
                queries = _extract_sparql_from_markdown(questions_path)

                self.assertEqual(len(queries), 4)
                for index, query in enumerate(queries):
                    with self.subTest(suite=name, query=index):
                        result = graph.query(query)
                        if result.type == "ASK":
                            self.assertTrue(result.askAnswer)
                        else:
                            self.assertEqual(result.type, "SELECT")
                            self.assertTrue(list(result))


if __name__ == "__main__":
    unittest.main()
