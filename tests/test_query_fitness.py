"""Tests for conceptual fitness, structural fitness and counterfactual
concept importance."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from ontocheck.query_fitness import (
    conceptual_fitness,
    counterfactual_importance,
    structural_fitness,
)


EX = "https://example.org/"

# measures links Detector to Quantity by domain and range; partOf has no
# domain or range, but Beamline carries "partOf some Facility".  Device is
# declared equivalent to an external Instrument class.
ONTOLOGY = """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Detector a owl:Class ; rdfs:label "Detector" .
ex:XrayDetector a owl:Class ; rdfs:label "X-ray detector" ;
    rdfs:subClassOf ex:Detector .
ex:Quantity a owl:Class ; rdfs:label "Quantity" .
ex:Facility a owl:Class ; rdfs:label "Facility" .
ex:Sample a owl:Class ; rdfs:label "Sample" .
ex:Beamline a owl:Class ; rdfs:label "Beamline" ;
    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:partOf ;
                      owl:someValuesFrom ex:Facility ] .
ex:Device a owl:Class ;
    owl:equivalentClass <https://other.org/Instrument> .
ex:measures a owl:ObjectProperty ; rdfs:domain ex:Detector ;
    rdfs:range ex:Quantity .
ex:partOf a owl:ObjectProperty .
"""


def query(nodes, edges=(), prefix=None):
    item = {"graph_query": {
        "nodes": [{"nid": i, "node_type": "class", "class": c}
                  for i, c in enumerate(nodes)],
        "edges": [{"start": s, "end": t, "relation": r} for s, r, t in edges],
    }}
    if prefix:
        item["sparql_query"] = f"PREFIX ex: <{prefix}> SELECT * WHERE {{}}"
    return item


QUESTIONS = [
    # d = 2: XrayDetector -> Detector (superclass), then measures.
    query(["ex:XrayDetector", "ex:Quantity"], [(0, "ex:measures", 1)]),
    # d = 1: the restriction on Beamline.
    query(["ex:Beamline", "ex:Facility"], [(0, "ex:partOf", 1)]),
    # Gizmo has no support, so the edge has none either.
    query(["ex:Gizmo", "ex:Facility"], [(0, "ex:partOf", 1)]),
    # Entailed support through owl:equivalentClass; no task edges.
    query(["<https://other.org/Instrument>"]),
]


def ask(case_id, text):
    return {"id": case_id, "level": "fact_retrieval",
            "task_type": "fact_retrieval", "prompt": case_id,
            "query": {"language": "sparql", "text": text},
            "expected": {"kind": "boolean", "values": True}}


SUITE = {
    "schema_version": "1.0", "suite_id": "fitness-v1", "domain": "test",
    "namespaces": {"ex": EX,
                   "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                   "owl": "http://www.w3.org/2002/07/owl#"},
    "inference": {"profile": "none"},
    "cases": [
        ask("a", "ASK { ex:XrayDetector rdfs:subClassOf ex:Detector }"),
        ask("b", "ASK { ex:Beamline a owl:Class }"),
        # Facility is named but optional: removing it changes nothing.
        ask("c", "ASK { ex:Sample a owl:Class . "
                 "OPTIONAL { ex:Facility a owl:Class } }"),
    ],
}


class QueryFitnessTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.ttl = root / "onto.ttl"
        cls.ttl.write_text(ONTOLOGY, encoding="utf-8")
        cls.suite = root / "suite.json"
        cls.suite.write_text(json.dumps(SUITE), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_conceptual_fitness(self):
        # F_C per query with w = 1: 1, 1, 2/3, 1; averaged with pi = 1/4.
        r = conceptual_fitness(self.ttl, QUESTIONS)
        self.assertAlmostEqual(r.score, round(11 / 12, 4))
        self.assertEqual(r.affected, [EX + "Gizmo"])
        concepts = r.detail["concepts"]
        self.assertEqual(concepts["https://other.org/Instrument"]["tier"],
                         "entailed")
        # w_work: Facility is in queries 2 and 3, each with 3 requirements.
        self.assertAlmostEqual(concepts[EX + "Facility"]["w_work"],
                               round(2 * (1 / 4) / 3, 4))

        # A query namespace that differs from the ontology's binding for the
        # same prefix is an authorised mapping (exact) -- or, when that is
        # not authorised, only an alignment on the local name.
        moved = [query(["ex:Quantity"], prefix="https://elsewhere.org/")]
        r = conceptual_fitness(self.ttl, moved)
        self.assertEqual(r.score, 1.0)
        self.assertEqual(r.detail["concepts"]["https://elsewhere.org/Quantity"]
                         ["via"], "prefix mapping")
        r = conceptual_fitness(self.ttl, moved, authorize_prefix_mapping=False)
        self.assertEqual(r.score, 0.0)
        self.assertEqual(r.detail["aligned_score"], 1.0)

    def test_structural_fitness(self):
        # s = exp(-ln 2 (d - 1)): 1/2, 1, 0; query 4 has no edges.
        r = structural_fitness(self.ttl, QUESTIONS)
        self.assertAlmostEqual(r.score, round((0.5 + 1 + 0) / 3, 4))
        edges = r.detail["edges"]
        self.assertEqual(edges["XrayDetector --measures--> Quantity"]["d"], 2)
        self.assertEqual(edges["Beamline --partOf--> Facility"]["d"], 1)
        self.assertIsNone(edges["Gizmo --partOf--> Facility"]["d"])
        # Path coverage 1, 1, 0; path stretch 2 and 1 where defined.
        self.assertAlmostEqual(r.detail["path_coverage"], round(2 / 3, 4))
        self.assertAlmostEqual(r.detail["path_stretch"], 1.5)

        r = structural_fitness(self.ttl, QUESTIONS[:1], lam=math.log(4))
        self.assertAlmostEqual(r.score, 0.25)

    def test_counterfactual_importance(self):
        r = counterfactual_importance(self.ttl, benchmark=self.suite)
        weights = r.detail["weights"]
        # Removing any of the four required concepts fails one of the three
        # cases; removing Facility changes nothing.
        self.assertAlmostEqual(weights[EX + "Beamline"]["drop"], round(1 / 3, 4))
        self.assertEqual(weights[EX + "Facility"]["w_impact"], 0.0)
        self.assertAlmostEqual(weights[EX + "Sample"]["w_impact"], 0.25)
        # w_work: Beamline 1/3, the other four 1/6.  Spearman = 0.25.
        self.assertAlmostEqual(r.score, 0.25)

        r = counterfactual_importance(self.ttl, QUESTIONS)
        self.assertTrue(r.status.startswith("Skipped"))

    def test_runner_selects_metrics_by_name(self):
        from ontocheck import run_assessment
        out = Path(self.tmp.name)
        questions = out / "questions.json"
        questions.write_text(json.dumps(QUESTIONS), encoding="utf-8")
        kwargs = dict(questions=str(questions), domain_prefixes=["ex"],
                      output_log_file=str(out / "a.log"),
                      output_csv_file=str(out / "a.csv"))
        r = run_assessment(self.ttl, structural_fitness=True, **kwargs)
        self.assertEqual(list(r["fitness"]), ["structuralFitness"])
        # Default: fitness from the questions, importance only with a suite.
        r = run_assessment(self.ttl, **kwargs)
        self.assertEqual(set(r["fitness"]),
                         {"conceptualFitness", "structuralFitness"})
        r = run_assessment(self.ttl, benchmark=str(self.suite), **kwargs)
        self.assertIn("counterfactualImportance", r["fitness"])


if __name__ == "__main__":
    unittest.main()
