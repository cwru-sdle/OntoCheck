"""Tests for the optional hermitpy-backed inference profile."""

import unittest

from rdflib import Graph, RDFS, URIRef

from ontocheck.benchmark import (
    BenchmarkCase,
    BenchmarkLevel,
    HermiTReasoner,
    default_reasoners,
)
from ontocheck.benchmark.models import ExpectedResult, QuerySpec
from hermitpy import InconsistentOntology, UnsupportedConstruct

EX = "https://example.org/"
THING = "http://www.w3.org/2002/07/owl#Thing"


def graph_from(turtle: str) -> Graph:
    graph = Graph()
    graph.parse(
        data="""\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""
        + turtle,
        format="turtle",
    )
    graph.bind("ex", EX)
    graph.bind("rdfs", RDFS)
    return graph


class HermiTReasonerTests(unittest.TestCase):
    def test_hermit_profile_is_registered(self):
        reasoner = default_reasoners().get("hermit")
        self.assertIsInstance(reasoner, HermiTReasoner)
        self.assertEqual(reasoner.name, "hermitpy-v1")

    def test_materialize_adds_inferred_direct_subclasses(self):
        graph = graph_from(
            """
            ex:Dog owl:equivalentClass ex:Canine .
            ex:Canine rdfs:subClassOf ex:Animal .
            """
        )
        materialized = HermiTReasoner().materialize(graph)
        dog = URIRef(EX + "Dog")
        canine = URIRef(EX + "Canine")
        animal = URIRef(EX + "Animal")
        self.assertIn((dog, RDFS.subClassOf, canine), materialized)
        self.assertIn((canine, RDFS.subClassOf, dog), materialized)
        self.assertIn((dog, RDFS.subClassOf, animal), materialized)
        self.assertIn((canine, RDFS.subClassOf, animal), materialized)
        self.assertNotIn((dog, RDFS.subClassOf, URIRef(THING)), materialized)

    def test_graph_path_walks_the_classified_hierarchy(self):
        graph = graph_from(
            """
            ex:Dog owl:equivalentClass ex:Canine .
            ex:Canine rdfs:subClassOf ex:Animal .
            """
        )
        case = BenchmarkCase(
            id="superclasses",
            level=BenchmarkLevel.COMPLEX_REASONING,
            task_type="deduction",
            prompt="What is Dog classified under?",
            query=QuerySpec(
                language="graph_path",
                parameters={
                    "source": "ex:Dog",
                    "predicate": "rdfs:subClassOf",
                    "min_hops": 1,
                    "max_hops": 5,
                },
            ),
            expected=ExpectedResult(kind="result_set", values=[]),
        )
        answers = {answer.value for answer in HermiTReasoner().reason(case, graph)}
        self.assertEqual(
            answers,
            {URIRef(EX + "Canine"), URIRef(EX + "Animal"), URIRef(THING)},
        )

    def test_inconsistent_ontology_is_not_classified(self):
        graph = graph_from(
            """
            ex:Dog owl:disjointWith ex:Cat .
            ex:fido a ex:Dog, ex:Cat .
            """
        )
        with self.assertRaises(InconsistentOntology):
            HermiTReasoner().materialize(graph)

    def test_unsupported_construct_is_not_ignored(self):
        graph = graph_from(
            """
            ex:C rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:p ;
                owl:maxCardinality 1
            ] .
            """
        )
        with self.assertRaises(UnsupportedConstruct):
            HermiTReasoner().materialize(graph)


if __name__ == "__main__":
    unittest.main()
