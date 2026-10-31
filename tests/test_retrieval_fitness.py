"""Tests for retrieval fitness."""

import json
import tempfile
import unittest
from pathlib import Path

from rdflib import Graph, URIRef

from ontocheck.retrieval_fitness import gold_evidence, retrieval_fitness


GRAPH = """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Phase a owl:Class ; rdfs:label "Phase" .
ex:BetaPhase a owl:Class ; rdfs:label "Beta Phase" ;
    rdfs:subClassOf ex:Phase ,
        [ a owl:Restriction ; owl:onProperty ex:transformsInto ;
          owl:someValuesFrom ex:AlphaPhase ] .
ex:AlphaPhase a owl:Class ; rdfs:label "Alpha Phase" ; rdfs:subClassOf ex:Phase .
ex:transformsInto a owl:ObjectProperty ; rdfs:label "transforms into" .
ex:sample1 a ex:BetaPhase .
"""

QUERY = """PREFIX ex: <https://example.org/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?target ?label WHERE {
  ex:BetaPhase rdfs:subClassOf [ a owl:Restriction ;
      owl:onProperty ex:transformsInto ; owl:someValuesFrom ?target ] .
  OPTIONAL { ?target rdfs:label ?label }
}"""


class RetrievalFitnessTest(unittest.TestCase):

    def test_gold_evidence_includes_the_restriction(self):
        g = Graph().parse(data=GRAPH, format="turtle")
        [path] = gold_evidence(g, QUERY)
        self.assertEqual(len(path), 5)   # subClassOf, 3 restriction, label
        self.assertIn(URIRef("https://example.org/AlphaPhase"),
                      {o for _, _, o in path})

    def test_ontology_retriever_finds_the_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            ttl = Path(tmp) / "g.ttl"
            ttl.write_text(GRAPH, encoding="utf-8")
            cq = Path(tmp) / "cq.json"
            cq.write_text(json.dumps([{
                "qid": "1", "sparql_query": QUERY,
                "question": "What does the beta phase transform into?"}]),
                encoding="utf-8")
            r = retrieval_fitness(ttl, cq)
        self.assertEqual(r.score, 1.0)
        self.assertEqual(r.detail["per_query"][0]["support_path_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
