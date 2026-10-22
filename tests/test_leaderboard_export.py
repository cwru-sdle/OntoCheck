"""Tests for the leaderboard results export."""

import json
import tempfile
import unittest
from pathlib import Path

from ontocheck.leaderboard_export import export, load_manifest, score_domain


ONTOLOGY = """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Detector a owl:Class ; rdfs:label "Detector" .
ex:XrayDetector a owl:Class ; rdfs:subClassOf ex:Detector .
ex:Quantity a owl:Class ; rdfs:label "Quantity" .
ex:measures a owl:ObjectProperty ; rdfs:domain ex:Detector ;
    rdfs:range ex:Quantity .
"""

QUESTIONS = [{
    "sparql_query": "PREFIX ex: <https://example.org/> SELECT ?d WHERE { "
                    "?d a ex:XrayDetector . ?d ex:measures ?q . ?q a ex:Quantity }",
}]


class LeaderboardExportTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "onto.ttl").write_text(ONTOLOGY, encoding="utf-8")
        (root / "questions.json").write_text(json.dumps(QUESTIONS), encoding="utf-8")
        cls.manifest = root / "domains.json"
        cls.manifest.write_text(json.dumps({"domains": [{
            "name": "Tiny", "files": ["onto.ttl"],
            "questions": "questions.json", "domain_prefixes": ["ex"],
        }]}), encoding="utf-8")
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_domain_has_four_tables(self):
        [d] = load_manifest(self.manifest)
        entry = score_domain(d["name"], d["files"], d["questions"],
                             domain_prefixes=d["domain_prefixes"])
        self.assertNotIn("error", entry)
        tables = entry["tables"]
        self.assertEqual(set(tables), {"oops", "foops", "oquare", "ontocheck"})

        # Framework rows carry the original score and both weighted views.
        p08 = next(r for r in tables["oops"]["rows"]
                   if r["id"] == "oopsP08MissingAnnotations")
        self.assertEqual(p08["original"], 4)          # no term has a definition
        self.assertEqual(p08["weighting"], "weighted")
        self.assertIsNotNone(p08["weighted"])
        self.assertIn("weighted_penalty_in_context", tables["oops"]["summary"])

        values = {r["id"]: r for r in tables["ontocheck"]["rows"]}
        self.assertEqual(values["recall"]["value"], 1.0)
        self.assertEqual(values["conceptualFitness"]["value"], 1.0)
        self.assertTrue(values["counterfactualImportance"]["status"]
                        .startswith("Not available"))
        self.assertTrue(values["externalLinks"]["status"].startswith("Skipped"))

    def test_update_keeps_other_domains(self):
        out = self.root / "results.json"
        out.write_text(json.dumps({"domains": [{"name": "Other", "files": []}]}),
                       encoding="utf-8")
        payload = export(load_manifest(self.manifest), out, update=True,
                         progress=lambda _: None)
        self.assertEqual([d["name"] for d in payload["domains"]],
                         ["Other", "Tiny"])
        self.assertEqual(json.loads(out.read_text())["schema"],
                         "ontocheck-leaderboard/1")


if __name__ == "__main__":
    unittest.main()
