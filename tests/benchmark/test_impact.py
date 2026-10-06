"""Leave-one-out concept and relation impact."""

import unittest

from rdflib import OWL, RDF, RDFS, Graph, URIRef

from ontocheck.benchmark import assess_impact, parse_suite, remove_concept, remove_relation


EX = "https://example.org/"
ALLOY = URIRef(EX + "Alloy")
UNUSED = URIRef(EX + "Unused")
HAS_PART = URIRef(EX + "hasPart")
UNUSED_RELATION = URIRef(EX + "unusedRelation")
SAMPLE = URIRef(EX + "Sample")
GRAIN = URIRef(EX + "Grain")
LEAF = URIRef(EX + "Leaf")
MIDDLE = URIRef(EX + "Middle")
ROOT = URIRef(EX + "Root")

ONTOLOGY = """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Alloy a owl:Class .
ex:Unused a owl:Class .
ex:hasPart a owl:ObjectProperty ;
    rdfs:domain ex:Alloy ;
    rdfs:range ex:Grain .
ex:unusedRelation a owl:ObjectProperty .
ex:Sample a ex:Alloy ;
    ex:hasPart ex:Grain .
ex:Alloy rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:hasPart ;
    owl:someValuesFrom ex:Grain
] .
"""

HIERARCHY = """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Leaf rdfs:subClassOf ex:Middle .
ex:Middle rdfs:subClassOf ex:Root .
ex:Unused a owl:Class .
"""


def _graph(text):
    graph = Graph()
    graph.parse(data=text, format="turtle")
    return graph


def _suite(profile, cases):
    return parse_suite(
        {
            "schema_version": "1.0",
            "suite_id": "impact-v1",
            "domain": "test",
            "namespaces": {
                "ex": EX,
                "rdfs": str(RDFS),
                "owl": str(OWL),
            },
            "inference": {"profile": profile},
            "cases": cases,
        }
    )


def _ask(case_id, prompt, where, expected):
    return {
        "id": case_id,
        "level": "fact_retrieval",
        "task_type": "fact_retrieval",
        "prompt": prompt,
        "query": {"language": "sparql", "text": "ASK { %s }" % where},
        "expected": {"kind": "boolean", "values": expected},
    }


def _row(report, kind, symbol):
    matches = [
        row
        for row in report.rows
        if row.kind == kind and row.symbol == str(symbol)
    ]
    if len(matches) != 1:
        raise AssertionError("Expected one %s row for %s" % (kind, symbol))
    return matches[0]


class RemovalTests(unittest.TestCase):
    def test_concept_removal_drops_its_restriction_and_keeps_the_rest(self):
        graph = _graph(ONTOLOGY)
        before = set(graph)
        ablated = remove_concept(graph, ALLOY)

        self.assertEqual(set(graph), before)
        self.assertFalse(any(ALLOY in triple for triple in ablated))
        self.assertNotIn((SAMPLE, RDF.type, ALLOY), set(ablated))
        self.assertFalse(any(obj == OWL.Restriction for _, _, obj in ablated))
        self.assertFalse(any(predicate == OWL.onProperty for _, predicate, _ in ablated))
        self.assertIn((SAMPLE, HAS_PART, GRAIN), set(ablated))
        self.assertIn((UNUSED, RDF.type, OWL.Class), set(ablated))

    def test_shared_restriction_stays_when_another_class_uses_it(self):
        graph = _graph(
            """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Alloy rdfs:subClassOf _:shared .
ex:Other rdfs:subClassOf _:shared .
_:shared a owl:Restriction ;
    owl:onProperty ex:hasPart ;
    owl:someValuesFrom ex:Grain .
"""
        )
        ablated = remove_concept(graph, ALLOY)
        self.assertTrue(any(predicate == OWL.onProperty for _, predicate, _ in ablated))
        self.assertTrue(
            any(subject == URIRef(EX + "Other") and predicate == RDFS.subClassOf
                for subject, predicate, _ in ablated)
        )

    def test_relation_removal_drops_domain_range_and_restrictions(self):
        graph = _graph(ONTOLOGY)
        ablated = remove_relation(graph, HAS_PART)

        self.assertFalse(any(HAS_PART in triple for triple in ablated))
        self.assertIn((SAMPLE, RDF.type, ALLOY), set(ablated))
        self.assertIn((UNUSED_RELATION, RDF.type, OWL.ObjectProperty), set(ablated))


class AssertedImpactTests(unittest.TestCase):
    def test_load_bearing_symbols_have_delta_one_and_unused_symbols_do_not(self):
        suite = _suite(
            "none",
            [
                _ask(
                    "needs-alloy-and-part",
                    "Is the sample an alloy with a grain?",
                    "ex:Sample a ex:Alloy ; ex:hasPart ex:Grain .",
                    True,
                ),
                _ask(
                    "needs-alloy-and-part-again",
                    "Does that same pattern still hold?",
                    "ex:Sample a ex:Alloy ; ex:hasPart ex:Grain .",
                    True,
                ),
            ],
        )
        report = assess_impact(suite, _graph(ONTOLOGY))

        alloy = _row(report, "concept", ALLOY)
        unused = _row(report, "concept", UNUSED)
        part = _row(report, "relation", HAS_PART)
        unused_relation = _row(report, "relation", UNUSED_RELATION)

        self.assertEqual(report.baseline, 1.0)
        self.assertEqual(alloy.delta, 1.0)
        self.assertEqual(alloy.ablated, 0.0)
        self.assertEqual(
            alloy.changed_questions,
            ("needs-alloy-and-part", "needs-alloy-and-part-again"),
        )
        self.assertEqual(unused.delta, 0.0)
        self.assertEqual(unused.changed_questions, ())
        self.assertEqual(part.delta, 1.0)
        self.assertEqual(part.question_deltas["needs-alloy-and-part"], 1.0)
        self.assertEqual(unused_relation.delta, 0.0)
        self.assertGreater(report.attributed_drop, report.baseline)

    def test_one_question_fails_and_one_still_succeeds(self):
        suite = _suite(
            "none",
            [
                _ask(
                    "needs-alloy",
                    "Is the sample an alloy?",
                    "ex:Sample a ex:Alloy .",
                    True,
                ),
                _ask(
                    "needs-part",
                    "Does the sample have a grain?",
                    "ex:Sample ex:hasPart ex:Grain .",
                    True,
                ),
            ],
        )
        report = assess_impact(suite, _graph(ONTOLOGY))
        alloy = _row(report, "concept", ALLOY)
        part = _row(report, "relation", HAS_PART)

        self.assertEqual(alloy.question_deltas["needs-alloy"], 1.0)
        self.assertEqual(alloy.question_deltas["needs-part"], 0.0)
        self.assertEqual(alloy.changed_questions, ("needs-alloy",))
        self.assertEqual(alloy.delta, 0.5)
        self.assertEqual(part.question_deltas["needs-part"], 1.0)
        self.assertEqual(part.question_deltas["needs-alloy"], 0.0)
        self.assertEqual(part.changed_questions, ("needs-part",))

    def test_knowledge_graph_triples_are_not_ablated(self):
        ontology = Graph()
        ontology.parse(
            data=(
                "@prefix ex: <https://example.org/> .\n"
                "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
                "ex:Alloy a owl:Class .\n"
                "ex:Unused a owl:Class .\n"
            ),
            format="turtle",
        )
        knowledge = Graph()
        knowledge.parse(
            data=(
                "@prefix ex: <https://example.org/> .\n"
                "ex:Sample a ex:Alloy .\n"
            ),
            format="turtle",
        )
        suite = _suite(
            "none",
            [
                _ask(
                    "kg-type",
                    "Is the sample an alloy?",
                    "ex:Sample a ex:Alloy .",
                    True,
                )
            ],
        )
        report = assess_impact(suite, ontology, knowledge)
        self.assertEqual(_row(report, "concept", ALLOY).delta, 0.0)
        self.assertEqual(_row(report, "concept", UNUSED).delta, 0.0)
        self.assertNotIn(HAS_PART, {URIRef(row.symbol) for row in report.rows})


class GraphPathImpactTests(unittest.TestCase):
    def test_inferred_parent_carries_impact(self):
        suite = _suite(
            "graph_path",
            [
                _ask(
                    "inferred-parent",
                    "Is Leaf a Root after the subclass walk?",
                    "ex:Leaf rdfs:subClassOf ex:Root .",
                    True,
                )
            ],
        )
        report = assess_impact(suite, _graph(HIERARCHY))
        middle = _row(report, "concept", MIDDLE)
        unused = _row(report, "concept", UNUSED)
        subclass = _row(report, "relation", RDFS.subClassOf)

        self.assertEqual(report.baseline, 1.0)
        self.assertEqual(middle.delta, 1.0)
        self.assertEqual(middle.ablated, 0.0)
        self.assertEqual(middle.changed_questions, ("inferred-parent",))
        self.assertEqual(unused.delta, 0.0)
        self.assertEqual(subclass.delta, 1.0)
        emitted = report.as_dict()
        self.assertEqual(emitted["rows"][0]["kind"], "concept")
        self.assertIn("changed_questions", emitted["rows"][0])

    def test_deduction_keeps_the_two_hop_predicate(self):
        suite = _suite(
            "graph_path",
            [
                {
                    "id": "two-hop",
                    "level": "complex_reasoning",
                    "task_type": "deduction",
                    "prompt": "What is Leaf after two subclass steps?",
                    "query": {
                        "language": "graph_path",
                        "source": "ex:Leaf",
                        "predicate": "rdfs:subClassOf",
                        "min_hops": 2,
                        "max_hops": 2,
                    },
                    "expected": {"kind": "result_set", "values": ["ex:Root"]},
                }
            ],
        )
        report = assess_impact(suite, _graph(HIERARCHY))
        middle = _row(report, "concept", MIDDLE)

        self.assertEqual(report.baseline, 1.0)
        self.assertEqual(middle.delta, 1.0)
        self.assertEqual(middle.ablated, 0.0)
