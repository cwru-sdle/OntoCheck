"""Tests for the optional owlready2 HermiT profile."""

import shutil
import unittest

from rdflib import Graph, RDFS, URIRef

from ontocheck.benchmark import OwlreadyReasoner, default_reasoners

try:
    import owlready2
except ImportError:  # pragma: no cover - optional dependency
    owlready2 = None

EX = "https://example.org/"
THING = "http://www.w3.org/2002/07/owl#Thing"


def graph_from(turtle: str) -> Graph:
    graph = Graph()
    graph.parse(
        data="""\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""
        + turtle,
        format="turtle",
    )
    graph.bind("ex", EX)
    return graph


@unittest.skipUnless(shutil.which("java") and owlready2, "Java and owlready2")
class OwlreadyReasonerTests(unittest.TestCase):
    def test_owlready_profile_is_registered(self):
        reasoner = default_reasoners().get("owlready")
        self.assertIsInstance(reasoner, OwlreadyReasoner)
        self.assertEqual(reasoner.name, "owlready2-hermit")

    def test_materialize_adds_direct_subclasses(self):
        graph = graph_from(
            """
            ex:Dog rdfs:subClassOf ex:Animal .
            ex:Animal rdfs:subClassOf ex:Organism .
            """
        )
        materialized = OwlreadyReasoner().materialize(graph)
        dog = URIRef(EX + "Dog")
        animal = URIRef(EX + "Animal")
        organism = URIRef(EX + "Organism")
        self.assertIn((dog, RDFS.subClassOf, animal), materialized)
        self.assertIn((animal, RDFS.subClassOf, organism), materialized)
        self.assertIn((organism, RDFS.subClassOf, URIRef(THING)), materialized)
        self.assertNotIn((dog, RDFS.subClassOf, URIRef(THING)), materialized)

    def test_equivalence_is_classified(self):
        graph = graph_from(
            """
            ex:Dog owl:equivalentClass ex:Canine .
            ex:Canine rdfs:subClassOf ex:Animal .
            """
        )
        materialized = OwlreadyReasoner().materialize(graph)
        dog = URIRef(EX + "Dog")
        canine = URIRef(EX + "Canine")
        animal = URIRef(EX + "Animal")
        self.assertIn((dog, RDFS.subClassOf, canine), materialized)
        self.assertIn((canine, RDFS.subClassOf, dog), materialized)
        self.assertIn((dog, RDFS.subClassOf, animal), materialized)

    def test_inconsistent_ontology_raises(self):
        graph = graph_from(
            """
            ex:Dog owl:disjointWith ex:Cat .
            ex:fido a ex:Dog, ex:Cat .
            """
        )
        with self.assertRaises(owlready2.OwlReadyInconsistentOntologyError):
            OwlreadyReasoner().materialize(graph)

    def test_datatype_restriction_is_accepted(self):
        graph = graph_from(
            """
            ex:Adult rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:age ;
                owl:someValuesFrom [
                    a rdfs:Datatype ;
                    owl:onDatatype xsd:integer ;
                    owl:withRestrictions ( [ xsd:minInclusive 18 ] )
                ]
            ] .
            ex:age a owl:DatatypeProperty .
            """
        )
        materialized = OwlreadyReasoner().materialize(graph)
        self.assertTrue(any(subj == URIRef(EX + "Adult") for subj, _, _ in materialized))


if __name__ == "__main__":
    unittest.main()
