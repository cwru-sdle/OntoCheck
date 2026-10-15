"""Tests for conceptual fitness, structural fitness and counterfactual importance."""

import json
import tempfile
import unittest
from pathlib import Path

from ontocheck.query_fitness import (
    conceptual_fitness_v_0_0_1,
    counterfactual_importance_v_0_0_1,
    structural_fitness_v_0_0_1,
)


EX = "https://example.org/"

# measures links detectors to quantities through domain and range; partOf has
# no domain or range, but Beamline carries "partOf some Facility".
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
ex:measures a owl:ObjectProperty ; rdfs:domain ex:Detector ;
    rdfs:range ex:Quantity .
ex:partOf a owl:ObjectProperty .
"""


def query(a, rel, b):
    return {"graph_query": {
        "nodes": [{"nid": 0, "node_type": "class", "class": a},
                  {"nid": 1, "node_type": "class", "class": b}],
        "edges": [{"start": 0, "end": 1, "relation": rel}],
    }}


# Every query has 3 concepts and 1 edge, so |Q_lm| = 3 concepts / 1 edge and
# w_c is the number of queries using c; w_e = 1 for each edge.
QUESTIONS = [
    query("ex:XrayDetector", "ex:measures", "ex:Quantity"),  # domain/range
    query("ex:Beamline", "ex:partOf", "ex:Facility"),        # restriction
    query("ex:Gizmo", "ex:partOf", "ex:Facility"),           # Gizmo missing
]


class QueryFitnessTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ttl = Path(cls.tmp.name) / "onto.ttl"
        cls.ttl.write_text(ONTOLOGY, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_conceptual_fitness(self):
        # Weights: Facility 2, partOf 2, the other five concepts 1 each (9).
        # Only Gizmo (weight 1) is unmatched: f_c = 8 / 9.
        r = conceptual_fitness_v_0_0_1(self.ttl, QUESTIONS)
        self.assertAlmostEqual(r.score, round(8 / 9, 4))
        self.assertEqual(r.affected, [EX + "Gizmo"])
        self.assertEqual(r.detail["concepts"][EX + "Facility"]["weight"], 2.0)

    def test_structural_fitness(self):
        r = structural_fitness_v_0_0_1(self.ttl, QUESTIONS)
        self.assertAlmostEqual(r.score, round(2 / 3, 4))
        self.assertEqual(r.detail["per_query"], [1.0, 1.0, 0.0])
        evidence = {k: v["evidence"] for k, v in r.detail["edges"].items()}
        self.assertEqual(evidence["XrayDetector --measures--> Quantity"],
                         "domain/range")
        self.assertEqual(evidence["Beamline --partOf--> Facility"],
                         "restriction")

        # The same question as SPARQL gives the same edge.
        sparql = ("PREFIX ex: <https://example.org/> SELECT ?d WHERE { "
                  "?d a ex:XrayDetector . ?d ex:measures ?q . ?q a ex:Quantity }")
        r = structural_fitness_v_0_0_1(self.ttl, [sparql])
        self.assertEqual(r.score, 1.0)

    def test_counterfactual_importance(self):
        r = counterfactual_importance_v_0_0_1(self.ttl, QUESTIONS)
        imp = r.detail["importance"]
        # Detector is not in any query, but the measures edge rests on it.
        self.assertAlmostEqual(imp[EX + "Detector"]["structural"], round(1 / 3, 4))
        self.assertEqual(imp[EX + "Detector"]["conceptual"], 0.0)
        # Facility: conceptual weight 2/9 and one of three edges.
        self.assertAlmostEqual(imp[EX + "Facility"]["total"],
                               round((2 / 9 + 1 / 3) / 2, 4))
        # partOf carries exactly as much (weight 2, the same edge): a tie.
        self.assertEqual(imp[EX + "partOf"], imp[EX + "Facility"])
        self.assertEqual(set(r.affected[:2]), {EX + "Facility", EX + "partOf"})
        self.assertNotIn(EX + "Sample", imp)

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
        self.assertAlmostEqual(r["structural_fitness"], round(2 / 3, 4))
        r = run_assessment(self.ttl, **kwargs)              # default: all three
        self.assertEqual(set(r["fitness"]), {"conceptualFitness",
                                             "structuralFitness",
                                             "counterfactualImportance"})


if __name__ == "__main__":
    unittest.main()
