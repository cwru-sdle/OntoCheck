"""
Query fitness metrics: conceptual fitness, structural fitness and
counterfactual importance.

Recall and Precision ask whether the terms of the competency questions exist
in the ontology.  These metrics ask two further questions, and a third about
the ontology's own elements:

* **Conceptual fitness** -- how well do the concepts the questions use match
  the ontology?
* **Structural fitness** -- does the ontology contain the relationships
  (edges) the questions traverse?
* **Counterfactual importance** -- which ontology elements does that fitness
  rest on?  An element's importance is the fitness lost when it is removed.

Definitions
-----------
For a set of queries Q, where query q uses the concepts C_q and the edges
E_q, and Q_lm is the largest query in Q:

- Conceptual fitness::

      f_c(Q, O) = sum_c w_c * m(c, O) / sum_c w_c
      w_c       = sum over queries q containing c of |C_q| / |C_lm|

  where ``m(c, O)`` is 1 for an exact match (IRI or local name), the label
  similarity for a near match, and 0 otherwise.

- Structural fitness::

      f_s(Q, O) = sum_e w_e * s(e, O) / sum_e w_e
      w_e       = sum over queries q containing e of |E_q| / |E_lm|

  where ``s(e, O)`` is 1 if the edge belongs to the ontology and 0
  otherwise.  ``f_s(q, O)`` for a single query sums over ``E_q`` only.

- Edge membership: a query edge ``A --p--> B`` belongs to the ontology when
  the ontology states that ``p`` can link an ``A`` to a ``B``, by any of:

  * domain and range: ``p`` (or a superproperty) has a domain ``D`` and a
    range ``R`` with ``A`` a subclass of ``D`` and ``B`` a subclass of ``R``;
  * restriction: ``A`` or an ancestor carries ``p some/only/value F``, with
    ``F`` and ``B`` on one subclass chain;
  * data: an instance of ``A`` is linked by ``p`` to an instance of ``B``.

  ``rdfs:subClassOf`` edges belong when the subsumption holds, ``rdf:type``
  edges when the class exists.  A literal or untyped endpoint matches
  anything.

- Counterfactual importance::

      CI(x) = F(O) - F(O without x),   F = (f_c + f_s) / 2

  Removing ``x`` makes it unavailable as a match, a property, a domain or
  range, a restriction owner or a link in a subclass chain.  Only elements
  whose removal lowers F are reported.

Queries are read from the ``graph_query`` of a competency-question JSON when
present (typed nodes and edges), and otherwise from the triple patterns of the
SPARQL.

Version: 0.0.1
"""

import json
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import BNode, Graph, Literal, OWL, RDF, RDFS, URIRef, Variable
from rdflib.namespace import XSD

from .context_weighting import EntityUniverse, LexicalMatcher, _norm_text
from .helpers.oops_helpers import _is_foundational, _local_name, _parse_rdf_list
from .helpers.semantic_helpers import _restrictions_on
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

_WELL_KNOWN = {
    "rdf": str(RDF), "rdfs": str(RDFS), "owl": str(OWL), "xsd": str(XSD),
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "obo": "http://purl.obolibrary.org/obo/",
    "cco": "https://www.commoncoreontologies.org/",
}
_PREFIX_DECL = re.compile(r"PREFIX\s+([A-Za-z][\w\-]*)?:\s*<([^>]*)>", re.I)


# ---------------------------------------------------------------------------
# Query patterns
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Term:
    """A query term: its expanded IRI (if it has one) and readable text."""

    key: str
    iri: str = None
    text: str = ""


@dataclass
class QueryPattern:
    """The concepts and edges one query uses."""

    concepts: set = field(default_factory=set)
    edges: set = field(default_factory=set)   # (Term or None, Term, Term or None)


def _expand(token, prefixes, text=""):
    """Turn ``prefix:local``, ``<iri>`` or a full IRI into a :class:`Term`."""
    token = str(token).strip()
    if token.startswith("<") and token.endswith(">"):
        token = token[1:-1]
    if re.match(r"^[a-z][\w+.-]*://", token):
        return Term(token, token, text or _norm_text(_local_name(token)))
    if ":" in token:
        p, local = token.split(":", 1)
        ns = prefixes.get(p)
        if ns:
            return Term(ns + local, ns + local, text or _norm_text(local))
    return Term(token, None, text or _norm_text(token))


def _is_schema(term):
    """Foundational vocabulary (rdf:type, rdfs:subClassOf, xsd:...)."""
    return term is not None and term.iri is not None and _is_foundational(term.iri)


def _from_graph_query(gq, prefixes):
    nodes = {}
    for n in gq.get("nodes", []):
        cls = n.get("class")
        if n.get("node_type") == "literal" or not cls:
            nodes[n.get("nid")] = None
            continue
        name = n.get("friendly_name", "") if n.get("node_type") == "class" else ""
        term = _expand(cls, prefixes, _norm_text(name) if name else "")
        nodes[n.get("nid")] = None if _is_schema(term) else term
    pat = QueryPattern()
    pat.concepts.update(t for t in nodes.values() if t is not None)
    for e in gq.get("edges", []):
        rel = _expand(e.get("relation", ""), prefixes,
                      _norm_text(e.get("friendly_name", "")))
        pat.edges.add((nodes.get(e.get("start")), rel, nodes.get(e.get("end"))))
        if not _is_schema(rel):
            pat.concepts.add(rel)
    return pat


def _algebra_triples(node, out):
    """Collect every BGP triple from an rdflib SPARQL algebra tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "triples" and isinstance(v, list):
                out.extend(t for t in v if len(t) == 3)
            else:
                _algebra_triples(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _algebra_triples(v, out)


def _from_sparql(text, prefixes):
    from rdflib.plugins.sparql import prepareQuery
    try:
        q = prepareQuery(text, initNs=prefixes)
    except Exception as e:                       # noqa: BLE001
        logger.warning(f"Could not parse a SPARQL query; skipped ({e}).")
        return None
    triples = []
    _algebra_triples(q.algebra, triples)

    def term(node):
        return Term(str(node), str(node), _norm_text(_local_name(node)))

    types = {}
    for s, p, o in triples:
        if p == RDF.type and isinstance(o, URIRef):
            types.setdefault(s, []).append(o)

    def endpoint(node):
        if isinstance(node, Literal):
            return None
        if isinstance(node, Variable):
            ts = sorted(types.get(node, []))
            return term(ts[0]) if ts else None
        return term(node)

    pat = QueryPattern()
    for s, p, o in triples:
        if not isinstance(p, URIRef):
            continue
        if p == RDF.type:
            if isinstance(o, URIRef) and not _is_foundational(o):
                pat.concepts.add(term(o))
            continue
        a, b = endpoint(s), endpoint(o)
        pat.edges.add((a, term(p), b))
        if not _is_foundational(p):
            pat.concepts.add(term(p))
        if p == RDFS.subClassOf:
            pat.concepts.update(t for t in (a, b) if t and not _is_schema(t))
    return pat


def load_query_patterns(questions, bindings=None):
    """
    Read the concepts and edges of each competency question.

    Parameters
    ----------
    questions : str, pathlib.Path, or list
        A competency-question ``.json`` (items with ``graph_query`` and/or
        ``sparql_query``), a benchmark suite ``.json`` (``cases``), a ``.md``
        file of ``sparql`` blocks, or a list of SPARQL strings or dicts.
    bindings : dict, optional
        Prefix bindings of the ontology, used for prefixes a query does not
        declare.

    Returns
    -------
    list of QueryPattern
    """
    base = dict(_WELL_KNOWN)
    base.update(bindings or {})

    items = questions
    if isinstance(questions, (str, Path)):
        path = Path(str(questions))
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            items = re.findall(r"```sparql\s*(.*?)```", text, re.DOTALL)
        else:
            items = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(items, dict) and "cases" in items:
                items = [(c.get("query") or {}).get("text", "")
                         for c in items["cases"]]

    patterns = []
    for item in items or []:
        sparql = item if isinstance(item, str) else (item.get("sparql_query") or "")
        prefixes = dict(base)
        prefixes.update({p or "": ns for p, ns in _PREFIX_DECL.findall(sparql)})
        pat = None
        if isinstance(item, dict) and item.get("graph_query"):
            pat = _from_graph_query(item["graph_query"], prefixes)
        elif sparql:
            pat = _from_sparql(sparql, prefixes)
        if pat and (pat.concepts or pat.edges):
            patterns.append(pat)
    return patterns


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class FitnessEvaluator:
    """
    Compute conceptual and structural fitness, optionally with some ontology
    elements removed (for counterfactual importance).

    Version: 0.0.1

    Parameters
    ----------
    g : rdflib.Graph
        The ontology, with instance data if any.
    patterns : list of QueryPattern
    matcher : LexicalMatcher, optional
        Used for concepts with no exact match.  Defaults to
        ``LexicalMatcher()`` (threshold 0.8).
    """

    def __init__(self, g, patterns, matcher=None):
        self.g = g
        self.u = EntityUniverse(g)
        self.patterns = patterns
        self.matcher = matcher or LexicalMatcher()
        self.matcher.fit({e: self.u.lexical_forms(e) for e in self.u.terms})
        self._restrictions = {}

        def weights(sets):
            largest = max((len(s) for s in sets), default=0) or 1
            w = {}
            for s in sets:
                for x in s:
                    w[x] = w.get(x, 0.0) + len(s) / largest
            return w

        self.w_c = weights([p.concepts for p in patterns])
        self.w_e = weights([p.edges for p in patterns])

        # Ranked candidates per term: exact resolutions (1.0) first, then
        # label matches.  Removing a candidate falls back to the next one.
        self.candidates = {}
        terms = set(self.w_c)
        for a, p, b in self.w_e:
            terms.update(t for t in (a, p, b) if t is not None)
        for t in terms:
            self.candidates[t] = self._rank(t)

    def _rank(self, term):
        out = []
        if term.iri is not None:
            iri = URIRef(term.iri)
            if iri in self.u.entities or (iri, None, None) in self.g:
                out.append((iri, 1.0))
            else:
                for e in sorted(self.u.by_local_name.get(_local_name(iri), ())):
                    out.append((e, 1.0))
        if term.text:
            seen = {e for e, _ in out}
            hits = sorted(self.matcher.score(term.text), key=lambda h: -h[2])
            out.extend((e, s) for e, _, s in hits if e not in seen)
        return out

    def _match(self, term, removed):
        for e, s in self.candidates.get(term, ()):
            if e not in removed:
                return e, s
        return None, 0.0

    # -- structure ----------------------------------------------------------

    def _ancestors(self, x, removed):
        """x and its told superclasses (or superproperties), avoiding removed."""
        seen, queue = {x}, deque([x])
        while queue:
            for p in self.u.up.get(queue.popleft(), ()):
                if p not in seen and p not in removed:
                    seen.add(p)
                    queue.append(p)
        return seen

    def _named(self, node):
        """A class expression's named classes (unions expanded)."""
        if isinstance(node, URIRef):
            return {node}
        members = self.g.value(node, OWL.unionOf)
        return set(_parse_rdf_list(self.g, members)) if members else set()

    def _restrictions_of(self, cls):
        if cls not in self._restrictions:
            self._restrictions[cls] = _restrictions_on(self.g, cls)
        return self._restrictions[cls]

    def edge_holds(self, edge, removed=frozenset()):
        """
        Return the evidence for an edge (``"subsumption"``, ``"type"``,
        ``"domain/range"``, ``"restriction"``, ``"data"``), or ``None``.
        """
        a_t, p_t, b_t = edge
        a = b = None
        if a_t is not None:
            a, _ = self._match(a_t, removed)
            if a is None:
                return None
        if b_t is not None:
            b, _ = self._match(b_t, removed)
            if b is None:
                return None

        if p_t.iri == str(RDFS.subClassOf):
            ok = a is None or b is None or b in self._ancestors(a, removed)
            return "subsumption" if ok else None
        if p_t.iri == str(RDF.type):
            return "type"

        p, _ = self._match(p_t, removed)
        if p is None or p not in self.u.properties:
            return None
        if a is None and b is None:
            return "property"
        props = self._ancestors(p, removed)
        anc_a = self._ancestors(a, removed) if a is not None else None
        anc_b = self._ancestors(b, removed) if b is not None else None

        def fits(declared, anc):
            if anc is None:
                return True
            return any(c in anc and c not in removed
                       for d in declared for c in self._named(d))

        domains = [d for q in props for d in self.g.objects(q, RDFS.domain)]
        ranges = [r for q in props for r in self.g.objects(q, RDFS.range)]
        if domains and ranges and fits(domains, anc_a) and fits(ranges, anc_b):
            return "domain/range"
        if domains and b is None and fits(domains, anc_a):
            return "domain/range"
        if ranges and a is None and fits(ranges, anc_b):
            return "domain/range"

        # An untyped source: any class may carry the restriction.
        owners = anc_a if anc_a is not None else (self.u.classes - removed)
        if owners:
            for owner in owners:
                for r in self._restrictions_of(owner):
                    if r["property"] not in props or r["filler"] is None:
                        continue
                    if anc_b is None:
                        return "restriction"
                    for f in self._named(r["filler"]):
                        if f in removed:
                            continue
                        if f in anc_b or b in self._ancestors(f, removed):
                            return "restriction"

        if self.u.individuals and a is not None and b is not None:
            for s, o in self.g.subject_objects(p):
                ts = self.u.individuals.get(s, ())
                to = self.u.individuals.get(o, ())
                if any(a in self._ancestors(t, removed) for t in ts) and \
                        any(b in self._ancestors(t, removed) for t in to):
                    return "data"
        return None

    # -- scores -------------------------------------------------------------

    def conceptual(self, removed=frozenset()):
        total = sum(self.w_c.values())
        if not total:
            return 0.0
        return sum(w * self._match(c, removed)[1]
                   for c, w in self.w_c.items()) / total

    def structural(self, removed=frozenset()):
        total = sum(self.w_e.values())
        if not total:
            return 0.0
        return sum(w for e, w in self.w_e.items()
                   if self.edge_holds(e, removed)) / total

    def structural_per_query(self):
        out = []
        for pat in self.patterns:
            total = sum(self.w_e[e] for e in pat.edges)
            held = sum(self.w_e[e] for e in pat.edges if self.edge_holds(e))
            out.append(held / total if total else None)
        return out

    def importance(self):
        """
        Counterfactual importance of every element the fitness could rest on.

        Returns
        -------
        dict
            Element to ``{"conceptual", "structural", "total"}`` losses,
            for elements whose removal lowers the combined fitness.
        """
        base_c, base_s = self.conceptual(), self.structural()
        relevant = set()
        for cands in self.candidates.values():
            relevant.update(e for e, _ in cands[:1])
        for c in list(relevant):
            relevant |= self._ancestors(c, frozenset())
        for p in [e for e in relevant if e in self.u.properties]:
            for q in self._ancestors(p, frozenset()):
                for pred in (RDFS.domain, RDFS.range):
                    for d in self.g.objects(q, pred):
                        relevant |= self._named(d)
        for c in [e for e in relevant if e in self.u.classes]:
            for r in self._restrictions_of(c):
                if r["filler"] is not None:
                    relevant |= self._named(r["filler"])
        relevant = {e for e in relevant
                    if isinstance(e, URIRef) and not _is_foundational(e)}

        out = {}
        for x in relevant:
            removed = frozenset({x})
            dc = base_c - self.conceptual(removed)
            ds = base_s - self.structural(removed)
            total = (dc + ds) / 2
            if total > 1e-12:
                out[x] = {"conceptual": round(dc, 4), "structural": round(ds, 4),
                          "total": round(total, 4)}
        return out


def _evaluator(ttl_file, questions):
    g = Graph()
    for f in [ttl_file] if isinstance(ttl_file, (str, Path)) else ttl_file:
        g.parse(str(f), format="turtle")
    bindings = {p: str(ns) for p, ns in g.namespaces()}
    return FitnessEvaluator(g, load_query_patterns(questions, bindings))


def _edge_label(edge):
    a, p, b = edge
    name = lambda t: "*" if t is None else (t.key.rsplit("/", 1)[-1]  # noqa: E731
                                            .rsplit("#", 1)[-1])
    return f"{name(a)} --{name(p)}--> {name(b)}"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def conceptual_fitness_v_0_0_1(ttl_file, questions=None, domain_prefixes=None,
                               domain_ns_fragments=None):
    """
    Conceptual fitness: weighted match quality of the questions' concepts.

    See the module docstring for the definition.

    Returns
    -------
    MetricResult
        ``score`` in [0, 1].  ``affected`` lists concepts with no match;
        ``detail["concepts"]`` gives each concept's weight, match score and
        matched element.
    """
    ev = _evaluator(ttl_file, questions)
    score = ev.conceptual()
    concepts = {}
    for c, w in sorted(ev.w_c.items(), key=lambda kv: -kv[1]):
        e, m = ev._match(c, frozenset())
        concepts[c.key] = {"weight": round(w, 4), "match": round(m, 4),
                           "element": str(e) if e else None}
    missing = [k for k, v in concepts.items() if not v["match"]]
    return MetricResult(
        metric_id="conceptualFitness", score=round(score, 4), passed=None,
        affected=missing, total_examined=len(concepts),
        detail={"concepts": concepts, "queries": len(ev.patterns)},
        message=f"f_c = {score:.4f} over {len(concepts)} concepts in "
                f"{len(ev.patterns)} queries; {len(missing)} unmatched",
    )


def structural_fitness_v_0_0_1(ttl_file, questions=None, domain_prefixes=None,
                               domain_ns_fragments=None):
    """
    Structural fitness: weighted share of the questions' edges that belong to
    the ontology.

    See the module docstring for the definition.

    Returns
    -------
    MetricResult
        ``score`` in [0, 1].  ``affected`` lists the missing edges;
        ``detail["edges"]`` gives each edge's weight and evidence, and
        ``detail["per_query"]`` gives f_s(q, O) for each query.
    """
    ev = _evaluator(ttl_file, questions)
    score = ev.structural()
    edges = {}
    for e, w in sorted(ev.w_e.items(), key=lambda kv: -kv[1]):
        edges[_edge_label(e)] = {"weight": round(w, 4),
                                 "evidence": ev.edge_holds(e)}
    missing = [k for k, v in edges.items() if v["evidence"] is None]
    return MetricResult(
        metric_id="structuralFitness", score=round(score, 4), passed=None,
        affected=missing, total_examined=len(edges),
        detail={"edges": edges, "per_query": [
            None if v is None else round(v, 4)
            for v in ev.structural_per_query()]},
        message=f"f_s = {score:.4f}; {len(edges) - len(missing)} of "
                f"{len(edges)} query edges belong to the ontology",
    )


def counterfactual_importance_v_0_0_1(ttl_file, questions=None,
                                      domain_prefixes=None,
                                      domain_ns_fragments=None):
    """
    Counterfactual importance: the fitness each ontology element carries.

    See the module docstring for the definition.

    Returns
    -------
    MetricResult
        ``score`` is the number of elements whose removal lowers fitness.
        ``affected`` lists them, most important first, and
        ``detail["importance"]`` gives each one's conceptual, structural and
        total loss.
    """
    ev = _evaluator(ttl_file, questions)
    imp = ev.importance()
    ranked = sorted(imp, key=lambda x: -imp[x]["total"])
    return MetricResult(
        metric_id="counterfactualImportance", score=len(ranked), passed=None,
        affected=[str(x) for x in ranked],
        total_examined=len(ev.u.terms),
        detail={"importance": {str(x): imp[x] for x in ranked},
                "conceptual_fitness": round(ev.conceptual(), 4),
                "structural_fitness": round(ev.structural(), 4)},
        message=f"{len(ranked)} elements carry the questions' fitness; "
                f"most important: "
                + ", ".join(_local_name(x) for x in ranked[:3]),
    )


# Plain names, as the metrics are called in the paper and the CLI.
conceptual_fitness = conceptual_fitness_v_0_0_1
structural_fitness = structural_fitness_v_0_0_1
counterfactual_importance = counterfactual_importance_v_0_0_1


for _id, _name, _fn, _scale, _hib, _desc in (
    ("conceptualFitness", "Conceptual fitness", conceptual_fitness_v_0_0_1,
     Scale.PROPORTION, True,
     "Weighted match quality of the competency questions' concepts."),
    ("structuralFitness", "Structural fitness", structural_fitness_v_0_0_1,
     Scale.PROPORTION, True,
     "Weighted share of the questions' edges present in the ontology."),
    ("counterfactualImportance", "Counterfactual importance",
     counterfactual_importance_v_0_0_1, Scale.RAW, False,
     "Elements whose removal lowers the questions' fitness."),
):
    register_metric(MetricDescriptor(
        metric_id=_id, name=_name, function=_fn, category=Category.TASK_BASED,
        source_framework=SourceFramework.ONTOCHECK, severity=Severity.INFO,
        scale=_scale, higher_is_better=_hib, requires_questions=True,
        description=_desc,
    ))
