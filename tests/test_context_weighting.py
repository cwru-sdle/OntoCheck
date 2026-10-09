"""Tests for context-weighted metric normalisation."""

import tempfile
import unittest
from pathlib import Path

from rdflib import Graph, URIRef

from ontocheck.context_weighting import build_context, normalize_results
from ontocheck.metric_registry import MetricResult
from ontocheck.oquare_metrics import oquare_ponto_v_0_0_1, oquare_rfconto_v_0_0_1


EX = "https://example.org/"

# Instrument > Detector > {XrayDetector > AreaDetector, Camera}; Sample and
# Quantity are unrelated to detectors except through ex:measures.
ONTOLOGY = """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Instrument a owl:Class ; rdfs:label "Instrument" .
ex:Detector a owl:Class ; rdfs:label "Detector" ;
    rdfs:subClassOf ex:Instrument .
ex:XrayDetector a owl:Class ; rdfs:label "X-ray detector" ;
    rdfs:subClassOf ex:Detector .
ex:AreaDetector a owl:Class ; rdfs:label "Area detector" ;
    rdfs:subClassOf ex:XrayDetector .
ex:Camera a owl:Class ; rdfs:label "Camera" ; rdfs:subClassOf ex:Detector .
ex:Sample a owl:Class ; rdfs:label "Sample" .
ex:Quantity a owl:Class ; rdfs:label "Quantity" .
ex:measures a owl:ObjectProperty ; rdfs:label "measures" ;
    rdfs:domain ex:Detector ; rdfs:range ex:Quantity .

ex:d1 a ex:AreaDetector .
ex:d2 a ex:AreaDetector .
ex:d3 a ex:XrayDetector .
ex:s1 a ex:Sample .
"""


def iri(name):
    return URIRef(EX + name)


class ContextWeightingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ttl = Path(cls.tmp.name) / "onto.ttl"
        cls.ttl.write_text(ONTOLOGY, encoding="utf-8")
        cls.graph = Graph().parse(cls.ttl, format="turtle")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sparql_and_natural_language_anchor_the_same_class(self):
        for query in ("SELECT ?d WHERE { ?d a ex:XrayDetector }",
                      "Which x-ray detectors were used?"):
            ctx = build_context(self.graph, queries=[query], use_instances=False)
            anchored = {a.entity for a in ctx.anchors}
            self.assertEqual(anchored, {iri("XrayDetector")}, query)

    def test_weight_spreads_along_dependencies_only(self):
        ctx = build_context(self.graph, queries=["Which x-ray detectors?"],
                            use_instances=False)
        self.assertEqual(ctx[iri("XrayDetector")], 1.0)
        self.assertEqual(ctx[iri("AreaDetector")], 1.0)   # subclass: answers
        self.assertEqual(ctx[iri("Detector")], 0.5)       # ancestor: decayed
        self.assertEqual(ctx[iri("Instrument")], 0.25)
        self.assertEqual(ctx[iri("Camera")], 0.0)         # sibling: no effect
        self.assertEqual(ctx[iri("Sample")], 0.0)

        # A property's answer depends on its domain and range classes.
        ctx = build_context(self.graph, use_instances=False,
                            queries=["SELECT ?x WHERE { ?x ex:measures ?q }"])
        self.assertEqual(ctx[iri("Detector")], 1.0)
        self.assertEqual(ctx[iri("Quantity")], 1.0)
        self.assertEqual(ctx[iri("Camera")], 1.0)         # subclass of domain
        self.assertEqual(ctx[iri("Sample")], 0.0)

    def test_instances_weight_populated_classes(self):
        ctx = build_context(self.graph)                   # "auto" finds ABox
        self.assertTrue(ctx.params["use_instances"])
        # Three detectors, propagated up; one sample; no cameras.
        self.assertGreater(ctx[iri("XrayDetector")], ctx[iri("Sample")])
        self.assertGreater(ctx[iri("Sample")], ctx[iri("Camera")])
        self.assertEqual(ctx[iri("Detector")], ctx[iri("XrayDetector")])
        self.assertEqual(ctx[iri("Camera")], 1.0)          # baseline kept

        # Both contexts over a KG: the questions decide what is relevant,
        # instances decide how much; individuals follow their classes.
        both = build_context(self.graph, queries=["x-ray detector"])
        self.assertEqual(both[iri("XrayDetector")],
                         ctx[iri("XrayDetector")])         # w_Q = 1
        self.assertEqual(both[iri("Sample")], 0.0)
        self.assertGreater(both[iri("d1")], 0.0)
        self.assertEqual(both[iri("s1")], 0.0)

    def test_normalisation(self):
        def defect(*names):
            return MetricResult(
                metric_id="oopsP08MissingAnnotations", score=len(names),
                passed=not names, affected=[EX + n for n in names],
            )

        # Uniform weights reproduce the unweighted values, OQuaRE included.
        ctx = build_context(self.ttl, use_instances=False)
        oquare = [oquare_ponto_v_0_0_1(self.ttl), oquare_rfconto_v_0_0_1(self.ttl)]
        for n in normalize_results([defect("Camera")] + oquare, ctx):
            self.assertAlmostEqual(n.weighted_value, n.uniform_value)
        for r, n in zip(oquare, normalize_results(oquare, ctx)):
            self.assertAlmostEqual(n.weighted_value, r.score, places=4)

        # Under a detector query a defect on Camera does not matter, while one
        # on AreaDetector weighs more than it does unweighted.
        ctx = build_context(self.ttl, queries=["x-ray detector"],
                            use_instances=False)
        camera, area = normalize_results(
            [defect("Camera"), defect("AreaDetector")], ctx
        )
        self.assertEqual(camera.weighted_value, 0.0)
        self.assertTrue(camera.passed_in_context)
        self.assertGreater(area.weighted_value, area.uniform_value)
        self.assertFalse(area.passed_in_context)

        # Ontology-level metrics are passed through untouched.
        doc = MetricResult(metric_id="oopsP38OntologyDeclaration", score=False,
                           passed=False, affected=["<no owl:Ontology>"])
        self.assertFalse(normalize_results([doc], ctx)[0].normalizable)


if __name__ == "__main__":
    unittest.main()
