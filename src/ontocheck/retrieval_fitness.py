"""
Retrieval fitness F_R: how well an ontology guides evidence retrieval.

For each query q with gold evidence E*_q, a retriever R returns at most b
triples S_q^(b) from the knowledge graph K.  Then

    ER@b = |S ∩ E*| / |E*|          evidence recall
    EP@b = |S ∩ E*| / |S|           evidence precision
    DR@b = |S \\ E*| / |S|           distractor rate
    SupportPathRecall = max over gold paths π* of |π* ∩ S| / |π*|

and the retrieval cost is |S| triples and |V(S)| nodes.  F_R(q) is the
profile <ER, EP, DR, cost>; workload values are the mean over queries with
gold evidence.

Gold evidence comes from each query's SPARQL: every triple pattern
instantiated with a solution's bindings and present in K.  The triples of one
solution form one gold path π*; E*_q is their union.  Queries with no
solutions have no gold evidence and are not scored.

Two retrievers, both given only the question text and the budget:

* ``ontology`` -- anchors the question's terms to ontology classes and
  properties, spreads weight along the ontology's dependency paths
  (:func:`ontocheck.context_weighting.spread_weights`) and through
  restriction fillers, and returns the highest-weighted triples about the
  weighted entities.
* ``lexical`` -- the no-ontology baseline: anchors the question's terms to
  any labelled node and returns the triples touching those nodes.

Version: 0.1.0
"""

import json
import logging
from itertools import product
from pathlib import Path

from rdflib import BNode, Graph, OWL, RDF, RDFS, Literal, URIRef, Variable
from rdflib.paths import Path as RdfPath

from .context_weighting import (
    EntityUniverse,
    LexicalMatcher,
    _text_anchors,
    spread_weights,
)
from .metric_registry import (
    Category,
    MetricDescriptor,
    MetricResult,
    Scale,
    Severity,
    SourceFramework,
    register_metric,
)

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 20
FILLER_DECAY = 0.5


def _r(x):
    return None if x is None else round(x, 4)


def _patterns(sparql, bindings):
    """Every triple pattern in a SPARQL query, OPTIONAL blocks included."""
    from rdflib.plugins.sparql import prepareQuery

    out = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "triples" and isinstance(v, list):
                    out.extend(t for t in v if len(t) == 3)
                else:
                    walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(prepareQuery(sparql, initNs=bindings).algebra)
    return out


def _blank_matches(g, patterns, values):
    """Graph nodes for each query blank node, given the named bindings."""
    found = {}
    blanks = {x for t in patterns for x in t if isinstance(x, BNode)}
    for b in blanks:
        own = [t for t in patterns if b in t]

        def bound(x):
            return values.get(str(x)) if isinstance(x, Variable) else x

        candidates = None
        for s, p, o in own:
            if s == b and not isinstance(bound(o), (BNode, type(None))):
                c = set(g.subjects(p, bound(o)))
            elif o == b and bound(s) is not None and not isinstance(s, BNode):
                c = set(g.objects(bound(s), p))
            else:
                continue
            candidates = c if candidates is None else candidates & c
        found[b] = sorted(candidates or (), key=str)
    return found


def gold_evidence(g, sparql):
    """
    Gold evidence paths of one query.

    Parameters
    ----------
    g : rdflib.Graph
        The knowledge graph.
    sparql : str

    Returns
    -------
    list of frozenset
        One gold path π* per solution: the triples its bindings instantiate,
        with the query's blank nodes (restrictions) matched in the graph.
        Property-path patterns are not instantiated.
    """
    import re

    bindings = {p: str(ns) for p, ns in g.namespaces()}
    patterns = [t for t in _patterns(sparql, bindings)
                if not isinstance(t[1], RdfPath)]
    if not patterns:
        return []
    select_all = re.sub(r"SELECT\s+(DISTINCT\s+)?(\?\w+\s*)+", "SELECT * ",
                        sparql, count=1, flags=re.IGNORECASE)
    paths = []
    for row in g.query(select_all, initNs=bindings):
        values = row.asdict()
        blanks = _blank_matches(g, patterns, values)

        def choices(x):
            if isinstance(x, BNode):
                return blanks.get(x, [])
            return [values.get(str(x))] if isinstance(x, Variable) else [x]

        path = {t for pattern in patterns
                for t in product(*map(choices, pattern))
                if None not in t and t in g}
        if path:
            paths.append(frozenset(path))
    return list(dict.fromkeys(paths))


def _bnode_closure(g, node, seen=None):
    """Triples describing a blank node, recursively (restrictions, lists)."""
    seen = set() if seen is None else seen
    if node in seen:
        return []
    seen.add(node)
    out = []
    for p, o in g.predicate_objects(node):
        out.append((node, p, o))
        if isinstance(o, BNode):
            out.extend(_bnode_closure(g, o, seen))
    return out


def _groups_about(g, node):
    """
    Evidence about *node*: each triple with *node* as subject, with the
    closure of a blank object (a restriction) attached, and the triples
    naming *node* as a superclass or type.

    Yields ``(other, triples)``: the node at the other end (for a
    restriction, its filler classes) and the triples retrieved together.
    """
    for p, o in g.predicate_objects(node):
        if isinstance(o, BNode):
            closure = _bnode_closure(g, o)
            fillers = [x for _, q, x in closure
                       if q in (OWL.someValuesFrom, OWL.allValuesFrom,
                                OWL.hasValue) and isinstance(x, URIRef)]
            yield fillers, [(node, p, o)] + closure
        else:
            yield [o], [(node, p, o)]
    for s in g.subjects(RDFS.subClassOf, node):
        if isinstance(s, URIRef):
            yield [s], [(s, RDFS.subClassOf, node)]
    for s in g.subjects(RDF.type, node):
        yield [s], [(s, RDF.type, node)]


def _restriction_fillers(g, cls):
    """Classes reached from *cls* through ``rdfs:subClassOf`` restrictions."""
    for r in g.objects(cls, RDFS.subClassOf):
        if isinstance(r, BNode):
            for p in (OWL.someValuesFrom, OWL.allValuesFrom, OWL.hasValue):
                for f in g.objects(r, p):
                    if isinstance(f, URIRef):
                        yield f


# Ties go to named axioms, then labels, then restrictions, then other
# annotations.
_STRUCTURAL = {RDFS.subClassOf, RDF.type, RDFS.subPropertyOf, RDFS.domain,
               RDFS.range, OWL.equivalentClass}


def _tie(triple):
    _, predicate, obj = triple
    if isinstance(obj, BNode):
        return 2
    if predicate in _STRUCTURAL:
        return 0
    return 1 if predicate == RDFS.label else 3


def _rank(g, weights, budget):
    """
    The highest-scoring evidence about the weighted nodes, at most *budget*
    triples.  A group scores the weight of its node plus that of the other
    end; a restriction is retrieved whole or not at all.
    """
    best = {}
    for node, w in weights.items():
        for others, triples in _groups_about(g, node):
            score = w + max((weights.get(x, 0.0) for x in others), default=0.0)
            key = triples[0]
            if score > best.get(key, (-1.0,))[0]:
                best[key] = (score, triples)
    ranked = sorted(best.values(), key=lambda v: (
        -v[0], _tie(v[1][0]), tuple(map(str, v[1][0]))))
    out, seen = [], set()
    for _, triples in ranked:
        new = [t for t in triples if t not in seen]
        if len(out) + len(new) > budget:
            continue
        out.extend(new)
        seen.update(new)
    return out


class Retriever:
    """
    Question-text retrievers over one knowledge graph.

    Parameters
    ----------
    g : rdflib.Graph
        The knowledge graph; its schema is the ontology.
    """

    def __init__(self, g):
        self.g = g
        self.universe = EntityUniverse(g)
        self.term_matcher = LexicalMatcher()
        self.term_matcher.fit({e: self.universe.lexical_forms(e)
                               for e in self.universe.terms})
        nodes = {s for s in g.subjects() if isinstance(s, URIRef)}
        self.node_matcher = LexicalMatcher()
        self.node_matcher.fit({e: self.universe.lexical_forms(e) for e in nodes})

    def ontology(self, question, budget=DEFAULT_BUDGET):
        seeds = {}
        for e, s, *_ in _text_anchors(question, self.term_matcher, 3):
            seeds[e] = max(seeds.get(e, 0.0), s)
        weights = spread_weights(self.universe, seeds, max_hops=3)
        # The classes an anchored class is restricted to, one step, decayed
        # like a step up the hierarchy.
        for c, w in seeds.items():
            for f in _restriction_fillers(self.g, c):
                weights[f] = max(weights.get(f, 0.0), FILLER_DECAY * w)
        return _rank(self.g, weights, budget)

    def lexical(self, question, budget=DEFAULT_BUDGET):
        seeds = {}
        for e, s, *_ in _text_anchors(question, self.node_matcher, 3):
            seeds[e] = max(seeds.get(e, 0.0), s)
        return _rank(self.g, seeds, budget)


def score_retrieval(retrieved, paths):
    """ER, EP, DR, SupportPathRecall and cost for one query."""
    s = set(retrieved)
    gold = set().union(*paths)
    hit = len(s & gold)
    nodes = {x for t in s for x in (t[0], t[2]) if not isinstance(x, Literal)}
    return {
        "ER": hit / len(gold),
        "EP": hit / len(s) if s else None,
        "DR": len(s - gold) / len(s) if s else None,
        "support_path_recall": max(len(p & s) / len(p) for p in paths),
        "triples": len(s),
        "nodes": len(nodes),
    }


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def retrieval_fitness_v_0_1_0(ttl_file, questions=None, domain_prefixes=None,
                              domain_ns_fragments=None,
                              budget=DEFAULT_BUDGET):
    """
    Retrieval fitness F_R.

    Parameters
    ----------
    ttl_file : str, pathlib.Path, or list thereof
        The ontology with its instance data (the knowledge graph).
    questions : str or pathlib.Path
        Competency questions ``.json`` with ``question`` and
        ``sparql_query``.
    domain_prefixes, domain_ns_fragments : optional
        Accepted for the registry's calling convention; unused.
    budget : int, optional
        b, the most triples a retriever may return.  Default 20.

    Returns
    -------
    MetricResult
        ``score`` is the workload ER@b of the ontology-guided retriever.
        ``detail`` holds the workload EP, DR, support-path recall and cost,
        the same for the no-ontology baseline (``lexical``), and
        ``per_query`` values.  Queries without gold evidence are listed in
        ``unscored``.
    """
    g = Graph()
    for f in [ttl_file] if isinstance(ttl_file, (str, Path)) else ttl_file:
        g.parse(str(f), format="turtle")
    items = json.loads(Path(str(questions)).read_text(encoding="utf-8"))
    retriever = Retriever(g)

    per_query, unscored = [], []
    for item in items:
        qid = str(item.get("qid", len(per_query) + len(unscored) + 1))
        sparql = item.get("sparql_query") or ""
        try:
            paths = gold_evidence(g, sparql) if sparql else []
        except Exception as e:                   # noqa: BLE001
            logger.warning(f"Query {qid}: no gold evidence ({e}).")
            paths = []
        if not paths:
            unscored.append(qid)
            continue
        text = item.get("question") or ""
        onto = score_retrieval(retriever.ontology(text, budget), paths)
        base = score_retrieval(retriever.lexical(text, budget), paths)
        per_query.append({"qid": qid, "question": text,
                          "gold_triples": len(set().union(*paths)),
                          **{k: _r(v) for k, v in onto.items()},
                          "lexical": {k: _r(v) for k, v in base.items()}})

    if not per_query:
        return MetricResult(
            metric_id="retrievalFitness",
            status="Skipped (no query has gold evidence in the graph)",
            detail={"unscored": unscored})

    def workload(key, rows):
        return _r(_mean([r[key] for r in rows]))

    base_rows = [r["lexical"] for r in per_query]
    detail = {
        "budget": budget,
        "queries": len(per_query),
        "evidence_precision": workload("EP", per_query),
        "distractor_rate": workload("DR", per_query),
        "support_path_recall": workload("support_path_recall", per_query),
        "triples": workload("triples", per_query),
        "nodes": workload("nodes", per_query),
        "lexical": {k: workload(k, base_rows)
                    for k in ("ER", "EP", "DR", "support_path_recall",
                              "triples", "nodes")},
        "per_query": per_query,
        "unscored": unscored,
    }
    score = workload("ER", per_query)
    return MetricResult(
        metric_id="retrievalFitness", score=score, passed=None,
        total_examined=len(per_query), detail=detail,
        message=f"ER@{budget} = {score} with the ontology, "
                f"{detail['lexical']['ER']} without, over {len(per_query)} "
                f"queries with gold evidence ({len(unscored)} without)")


retrieval_fitness = retrieval_fitness_v_0_1_0

register_metric(MetricDescriptor(
    metric_id="retrievalFitness", name="Retrieval fitness",
    function=retrieval_fitness, category=Category.TASK_BASED,
    source_framework=SourceFramework.ONTOCHECK, severity=Severity.INFO,
    scale=Scale.PROPORTION, higher_is_better=True, requires_questions=True,
    description="F_R: evidence recall of ontology-guided retrieval under a "
                "triple budget; needs instance data and competency questions.",
))
