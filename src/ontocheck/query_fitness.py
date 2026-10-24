"""
Conceptual fitness, structural fitness and counterfactual concept importance.

Definitions
-----------
A workload Q holds queries q.  Each has an ontology-independent task graph
H_q = (V_q, E_q, ...) whose required concepts and properties are C_q and whose
task edges are e = (u, rho, v) in E_q.  Queries are weighted by pi_q, with
sum pi_q = 1; the default is pi_q = 1/|Q|.  Workload scores aggregate
per-query scores as f(O, Q) = sum_q pi_q f(q, O).

- Semantic support mu(c, O) in [0, 1], in three tiers:

  * exact -- explicit identity (the requirement's IRI is in O), or a
    benchmark-authorised canonical mapping: an explicit ``mappings`` entry,
    or a query prefix whose namespace differs from the ontology's binding for
    the same prefix name;
  * entailed -- an equivalence axiom in O links a declared entity to the
    requirement's IRI;
  * aligned -- approximate correspondence found by a matcher: the same local
    name in another namespace, or label similarity.

  Exact and entailed support is 1.  Aligned support is the matcher score.
  The primary score uses exact and entailed support only; the score with
  aligned support is reported separately.

- Conceptual fitness::

      F_C(q, O) = sum_{c in C_q} w_{c,q} mu(c, O) / sum_{c in C_q} w_{c,q}

  Canonical weights are w_{c,q} = 1.  Workload weights::

      w_c^work = sum_q pi_q 1[c in C_q] / |C_q|

- Concept ambiguity::

      A_C(q, O) = (1/|C_q|) sum_{c in C_q} log(1 + |M_tau(c, O)|)

  where M_tau(c, O) is every candidate mapping in any tier at or above the
  matcher threshold tau.  Reported, never folded into F_C.

- Admissible schema path.  For a task edge (u, rho, v) and a
  concept mapping phi, a path from phi(u) to phi(v) is admissible when it
  realises rho:

  * superclass steps from phi(u) (an inherited domain), then
  * one edge of rho, of a subproperty or equivalent property of rho, or of
    rho's inverse read backwards -- or a property chain that O declares for
    rho -- where a property's edges come from its domain and range and from
    restrictions on it, then
  * superclass or subclass steps to phi(v).

  ``rdfs:subClassOf`` requirements are realised by superclass steps alone.
  Only schema edges count: instance data never makes an edge admissible.

- Path cost.  Every step costs 1 (the canonical setting: no semantic,
  inference or genericity penalties).
  d_O(e; phi) is the minimum cost, or infinity.

- Structural support and fitness::

      s(e, O; phi) = 0 if d_O = inf, else exp(-lambda (d_O - 1))
      F_S(q, O)    = max_{phi in Phi_q} sum_e w_e s(e, O; phi) / sum_e w_e

  Phi_q is restricted to validated (exact and entailed) mappings.  Canonical
  edge weights are w_e = 1.

- Diagnostics: PathCoverage(q) is the share of task edges with
  a finite d_O; PathStretch(q) is the mean of d_O(e) / d*_q(e) over them, with
  d*_q(e) = 1 since every task edge names one relation.

- Counterfactual concept importance::

      w_c^impact  proportional to  Z(O) - Z(O^{-c})

  Z is the benchmark score of a suite with expected answers, and O^{-c}
  removes the requirement c from O.  It is used only to validate the
  workload weights, never inside F_C, to avoid circularity.
  The headline score is therefore the rank correlation between w_c^work and
  w_c^impact.

Version: 0.1.0
"""

import json
import logging
import math
import re
from collections import deque
from dataclasses import dataclass, field
from itertools import product
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
_PREFIXED = re.compile(r"(?<![\w?$<:/#])([A-Za-z][\w\-]*):([A-Za-z_][\w\-.]*)")

# Path cost decay: each step beyond the first halves structural support.
# OntoCheck's default.
DEFAULT_LAMBDA = math.log(2)
_MAX_MAPPINGS = 256      # joint mappings tried per query before falling back
_LITERAL = "<literal>"   # sentinel target for datatype properties

EXACT, ENTAILED, ALIGNED = "exact", "entailed", "aligned"


# ---------------------------------------------------------------------------
# Task representation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Term:
    """
    A task requirement: its IRI as written, the IRI an authorised prefix
    mapping gives, and readable text for alignment.
    """

    key: str
    iri: str = None
    mapped: str = None
    text: str = ""


@dataclass
class QueryPattern:
    """The required concepts C_q and task edges E_q of one query."""

    concepts: set = field(default_factory=set)
    edges: set = field(default_factory=set)   # (Term or None, Term, Term or None)
    qid: str = ""
    question: str = ""


def _expand(token, prefixes, ontology_bindings, text=""):
    """Turn ``prefix:local``, ``<iri>`` or a full IRI into a :class:`Term`."""
    token = str(token).strip()
    if token.startswith("<") and token.endswith(">"):
        token = token[1:-1]
    if re.match(r"^[a-z][\w+.-]*://", token):
        return Term(token, token, None, text or _norm_text(_local_name(token)))
    if ":" in token:
        p, local = token.split(":", 1)
        ns = prefixes.get(p)
        if ns:
            onto_ns = ontology_bindings.get(p)
            mapped = onto_ns + local if onto_ns and onto_ns != ns else None
            return Term(ns + local, ns + local, mapped, text or _norm_text(local))
    return Term(token, None, None, text or _norm_text(token))


def _remap(iri, prefixes, ontology_bindings):
    """The authorised prefix mapping of a full IRI, if one applies."""
    for p, ns in prefixes.items():
        onto_ns = ontology_bindings.get(p)
        if onto_ns and onto_ns != ns and iri.startswith(ns):
            return onto_ns + iri[len(ns):]
    return None


def _is_schema(term):
    """Foundational vocabulary (rdf:type, rdfs:subClassOf, xsd:...)."""
    return term is not None and term.iri is not None and _is_foundational(term.iri)


def _from_graph_query(gq, prefixes, bindings):
    nodes = {}
    for n in gq.get("nodes", []):
        cls = n.get("class")
        if n.get("node_type") == "literal" or not cls:
            nodes[n.get("nid")] = None
            continue
        name = n.get("friendly_name", "") if n.get("node_type") == "class" else ""
        term = _expand(cls, prefixes, bindings, _norm_text(name) if name else "")
        nodes[n.get("nid")] = None if _is_schema(term) else term
    pat = QueryPattern()
    pat.concepts.update(t for t in nodes.values() if t is not None)
    for e in gq.get("edges", []):
        rel = _expand(e.get("relation", ""), prefixes, bindings,
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


def _from_sparql(text, prefixes, bindings):
    from rdflib.plugins.sparql import prepareQuery
    try:
        q = prepareQuery(text, initNs=prefixes)
    except Exception as e:                       # noqa: BLE001
        logger.warning(f"Could not parse a SPARQL query; skipped ({e}).")
        return None
    triples = []
    _algebra_triples(q.algebra, triples)

    def term(node):
        s = str(node)
        return Term(s, s, _remap(s, prefixes, bindings),
                    _norm_text(_local_name(node)))

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
        pat.concepts.update(t for t in (a, b) if t and not _is_schema(t))
    return pat


def _suite_case_terms(case, prefixes, bindings):
    """Required concepts of a benchmark case: every IRI its queries name."""
    texts = []

    def walk(value):
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(case.get("query") or {})
    pat = QueryPattern()
    for text in texts:
        for iri in re.findall(r"<([^<>\s]+)>", text):
            t = _expand(iri, prefixes, bindings)
            if not _is_schema(t):
                pat.concepts.add(t)
        for p, local in _PREFIXED.findall(re.sub(r"<[^<>\s]+>", " ", text)):
            if p in prefixes:
                t = _expand(f"{p}:{local.rstrip('.-')}", prefixes, bindings)
                if not _is_schema(t):
                    pat.concepts.add(t)
    return pat


def load_query_patterns(questions, bindings=None):
    """
    Read the required concepts and task edges of each query.

    Parameters
    ----------
    questions : str, pathlib.Path, or list
        A competency-question ``.json`` (items with ``graph_query`` and/or
        ``sparql_query``), a benchmark suite ``.json`` (``cases``), a ``.md``
        file of ``sparql`` blocks, or a list of SPARQL strings or dicts.
    bindings : dict, optional
        The ontology's prefix bindings.  A query prefix bound here to a
        different namespace yields an authorised canonical mapping.

    Returns
    -------
    list of QueryPattern
        One per query, in file order.  Queries with neither concepts nor
        edges are dropped.
    """
    bindings = dict(bindings or {})
    base = dict(_WELL_KNOWN)
    base.update(bindings)

    items = questions
    if isinstance(questions, (str, Path)):
        path = Path(str(questions))
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            items = []
            for m in re.finditer(r"```sparql\s*(.*?)```", text, re.DOTALL):
                head = re.findall(r"\*\*(?:(CQ\d+)\.\s*)?(.+?)\*\*",
                                  text[:m.start()])
                qid, question = head[-1] if head else ("", "")
                items.append({"qid": qid or str(len(items) + 1),
                              "question": question, "sparql_query": m.group(1)})
        else:
            items = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(items, dict) and "cases" in items:
        prefixes = dict(base)
        prefixes.update(items.get("namespaces") or {})
        patterns = []
        for c in items["cases"]:
            p = _suite_case_terms(c, prefixes, bindings)
            if p.concepts:
                p.qid, p.question = c.get("id", ""), c.get("prompt", "")
                patterns.append(p)
        return patterns

    patterns = []
    for n, item in enumerate(items or [], 1):
        sparql = item if isinstance(item, str) else (item.get("sparql_query") or "")
        prefixes = dict(base)
        prefixes.update({p or "": ns for p, ns in _PREFIX_DECL.findall(sparql)})
        pat = None
        if isinstance(item, dict) and item.get("graph_query"):
            pat = _from_graph_query(item["graph_query"], prefixes, bindings)
        elif sparql:
            pat = _from_sparql(sparql, prefixes, bindings)
        if pat and (pat.concepts or pat.edges):
            if isinstance(item, dict):
                pat.qid = str(item.get("qid") or n)
                pat.question = item.get("question") or ""
            else:
                pat.qid = str(n)
            patterns.append(pat)
    return patterns


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class FitnessEvaluator:
    """
    Conceptual and structural fitness of an ontology for a workload.

    Version: 0.1.0

    Parameters
    ----------
    g : rdflib.Graph
        The ontology.  Instance data in the graph is ignored by F_S.
    patterns : list of QueryPattern
    query_weights : list of float, optional
        pi_q, one per pattern.  Normalised to sum to 1.  Default 1/|Q|.
    weighting : {"canonical", "workload"}, optional
        w_{c,q} = 1 (canonical, default) or the workload weights w_c^work.  The same
        choice applies to w_e, with edges in place of concepts.
    mappings : dict, optional
        Benchmark-authorised canonical mappings, requirement IRI (or the
        ``prefix:local`` form) to ontology IRI.  Exact support.
    authorize_prefix_mapping : bool, optional
        Treat a query prefix bound to a different namespace in the ontology
        as an authorised mapping.  Default ``True``.
    lam : float, optional
        lambda in s = exp(-lambda (d - 1)).  Default ln 2.
    max_hops : int, optional
        Longest admissible path searched.  Default 8.
    matcher : LexicalMatcher, optional
        Finds aligned support.  Its threshold is tau in A_C.
    """

    def __init__(self, g, patterns, query_weights=None, weighting="canonical",
                 mappings=None, authorize_prefix_mapping=True,
                 lam=DEFAULT_LAMBDA, max_hops=8, matcher=None):
        if weighting not in ("canonical", "workload"):
            raise ValueError("weighting must be 'canonical' or 'workload'")
        self.g = g
        self.u = EntityUniverse(g)
        self.patterns = patterns
        self.weighting = weighting
        self.mappings = {str(k): URIRef(v) for k, v in (mappings or {}).items()}
        self.authorize_prefix_mapping = authorize_prefix_mapping
        self.lam = lam
        self.max_hops = max_hops
        self.matcher = matcher or LexicalMatcher()
        self.matcher.fit({e: self.u.lexical_forms(e) for e in self.u.terms})

        n = len(patterns)
        pi = list(query_weights) if query_weights is not None else [1.0] * n
        if len(pi) != n:
            raise ValueError("query_weights needs one weight per query")
        total = sum(pi) or 1.0
        self.pi = [p / total for p in pi]

        self.w_work = self._workload_weights([p.concepts for p in patterns])
        self.w_work_edges = self._workload_weights([p.edges for p in patterns])

        self.support = {}
        self.via = {}
        terms = set()
        for p in patterns:
            terms |= p.concepts
            for a, r, b in p.edges:
                terms.update(t for t in (a, r, b) if t is not None)
        for t in terms:
            self.support[t] = self._support(t)

        self._schema = None

    def _workload_weights(self, sets):
        """Workload weights: sum_q pi_q 1[x in S_q] / |S_q|."""
        w = {}
        for pi_q, s in zip(self.pi, sets):
            for x in s:
                w[x] = w.get(x, 0.0) + pi_q / len(s)
        return w

    # -- semantic support --------------------------------------------

    def _present(self, iri):
        """Explicit identity: the IRI is a class, property or individual of
        O, or is used as a predicate.  Being named only inside an axiom
        about another entity (an equivalence, say) is not identity."""
        return iri in self.u.entities or (None, iri, None) in self.g

    def _support(self, term):
        """
        All candidate mappings of a requirement: [(entity, mu, tier)].

        ``self.via[term]`` records how the best exact support was reached:
        ``"identity"``, ``"mapping"`` or ``"prefix mapping"``.
        """
        out, seen = [], set()

        def add(e, mu, tier):
            if e not in seen:
                seen.add(e)
                out.append((e, mu, tier))

        written = [URIRef(x) for x in (term.iri,) if x]
        mapped = []
        for key in (term.key, term.iri):
            if key in self.mappings:
                mapped.append((self.mappings[key], "mapping"))
        if term.mapped and self.authorize_prefix_mapping:
            mapped.append((URIRef(term.mapped), "prefix mapping"))

        for iri, how in [(i, "identity") for i in written] + mapped:
            if self._present(iri):
                if not any(t == EXACT for _, _, t in out):
                    self.via[term] = how
                add(iri, 1.0, EXACT)
        mapped = [iri for iri, _ in mapped]
        for iri in written + mapped:
            for pred in (OWL.equivalentClass, OWL.equivalentProperty, OWL.sameAs):
                for x in list(self.g.subjects(pred, iri)) + \
                        list(self.g.objects(iri, pred)):
                    if isinstance(x, URIRef) and x in self.u.entities:
                        add(x, 1.0, ENTAILED)
        for iri in written + mapped:
            for e in sorted(self.u.by_local_name.get(_local_name(iri), ())):
                add(e, 1.0, ALIGNED)
        if term.text:
            for e, _, s in sorted(self.matcher.score(term.text),
                                  key=lambda h: -h[2]):
                add(e, s, ALIGNED)
        rank = {EXACT: 0, ENTAILED: 1, ALIGNED: 2}
        return sorted(out, key=lambda x: (rank[x[2]], -x[1], str(x[0])))

    def mu(self, term, aligned=False):
        """mu(c, O): best support over the validated tiers (or all tiers)."""
        best = 0.0
        for _, m, tier in self.support.get(term, ()):
            if tier != ALIGNED or aligned:
                best = max(best, m)
        return best

    def validated(self, term, aligned=False):
        """Candidate entities for phi: exact and entailed (or also aligned)."""
        return [e for e, _, tier in self.support.get(term, ())
                if tier != ALIGNED or aligned]

    # -- conceptual fitness ------------------------------------------

    def _w(self, x, edge=False):
        if self.weighting == "canonical":
            return 1.0
        return (self.w_work_edges if edge else self.w_work).get(x, 0.0)

    def conceptual_q(self, q, aligned=False):
        concepts = self.patterns[q].concepts
        total = sum(self._w(c) for c in concepts)
        if not total:
            return None
        return sum(self._w(c) * self.mu(c, aligned) for c in concepts) / total

    def ambiguity_q(self, q):
        concepts = self.patterns[q].concepts
        if not concepts:
            return None
        return sum(math.log(1 + len(self.support.get(c, ())))
                   for c in concepts) / len(concepts)

    def aggregate(self, per_query):
        """sum_q pi_q f(q), renormalising pi over queries where f is defined."""
        pairs = [(p, v) for p, v in zip(self.pi, per_query) if v is not None]
        total = sum(p for p, _ in pairs)
        return sum(p * v for p, v in pairs) / total if total else None

    def conceptual(self, aligned=False):
        return self.aggregate([self.conceptual_q(q, aligned)
                               for q in range(len(self.patterns))])

    # -- schema graph ------------------------------------------------

    def _build_schema(self):
        g, classes = self.g, self.u.classes
        up = {c: set() for c in classes}
        for c in classes:
            up[c] |= {p for p in self.u.up.get(c, ()) if p in classes}
            for pred in (OWL.equivalentClass,):
                for x in list(g.objects(c, pred)) + list(g.subjects(pred, c)):
                    if x in classes and x != c:
                        up[c].add(x)
        down = {c: set() for c in classes}
        for c, ps in up.items():
            for p in ps:
                down.setdefault(p, set()).add(c)

        def named(node):
            if isinstance(node, URIRef):
                if node in classes:
                    return {node}
                return {_LITERAL} if str(node).startswith(str(XSD)) or \
                    node == RDFS.Literal else set()
            if isinstance(node, BNode):
                members = g.value(node, OWL.unionOf)
                if members is not None:
                    out = set()
                    for m in _parse_rdf_list(g, members):
                        out |= named(m)
                    return out
                if (node, RDF.type, RDFS.Datatype) in g:
                    return {_LITERAL}
            if isinstance(node, Literal):
                return {_LITERAL}
            return set()

        edges = {}
        for p in self.u.properties:
            ds = set().union(*(named(d) for d in g.objects(p, RDFS.domain))) \
                if any(True for _ in g.objects(p, RDFS.domain)) else set()
            rs = set().union(*(named(r) for r in g.objects(p, RDFS.range))) \
                if any(True for _ in g.objects(p, RDFS.range)) else set()
            if (p, RDF.type, OWL.DatatypeProperty) in g and not rs and ds:
                rs = {_LITERAL}
            edges[p] = {(d, r) for d in ds if d != _LITERAL for r in rs}
        for c in classes:
            for r in _restrictions_on(g, c):
                p, f = r["property"], r["filler"]
                if p is None or f is None:
                    continue
                targets = named(f) or ({_LITERAL} if r["kind"] == OWL.hasValue
                                       else set())
                edges.setdefault(p, set()).update((c, t) for t in targets)
        # Normalised inverses: an edge of p' read backwards is an edge of p.
        for p in list(edges):
            for inv in set(g.objects(p, OWL.inverseOf)) | \
                    set(g.subjects(OWL.inverseOf, p)):
                for s, o in list(edges.get(inv, ())):
                    if o != _LITERAL:
                        edges.setdefault(p, set()).add((o, s))

        # Subproperty and equivalent-property realisations of each property.
        sub = {}
        for s, o in g.subject_objects(RDFS.subPropertyOf):
            sub.setdefault(o, set()).add(s)
        for s, o in g.subject_objects(OWL.equivalentProperty):
            sub.setdefault(o, set()).add(s)
            sub.setdefault(s, set()).add(o)
        chains = {}
        for p, lst in g.subject_objects(OWL.propertyChainAxiom):
            chains.setdefault(p, []).append(list(_parse_rdf_list(g, lst)))

        self._schema = {"up": up, "down": down, "edges": edges,
                        "sub": sub, "chains": chains}

    def _realisers(self, rho):
        """rho, its subproperties and its equivalent properties."""
        sub = self._schema["sub"]
        seen, queue = {rho}, deque([rho])
        while queue:
            for x in sub.get(queue.popleft(), ()):
                if x not in seen:
                    seen.add(x)
                    queue.append(x)
        return seen

    def _relation_steps(self, rho):
        """Ways to cross rho: lists of properties, each a path segment."""
        steps = [[p] for p in self._realisers(rho)]
        for p in self._realisers(rho):
            steps.extend(self._schema["chains"].get(p, []))
        return steps

    def distance(self, edge, phi):
        """
        d_O(e; phi): fewest steps on an admissible path, or ``math.inf``.

        ``phi`` maps each endpoint Term to an entity; a missing endpoint (a
        literal or untyped node) matches anything.
        """
        if self._schema is None:
            self._build_schema()
        up, down, E = self._schema["up"], self._schema["down"], \
            self._schema["edges"]
        a_t, rho_t, b_t = edge
        a = phi.get(a_t) if a_t is not None else None
        b = phi.get(b_t) if b_t is not None else None
        if (a_t is not None and a is None) or (b_t is not None and b is None):
            return math.inf          # zero concept support forces zero here

        if rho_t.iri == str(RDFS.subClassOf):
            if a is None or b is None:
                known = a if a is not None else b
                return 1 if (up.get(known) or down.get(known)) else math.inf
            if a == b:
                return 1
            dist, queue = {a: 0}, deque([a])
            while queue:
                x = queue.popleft()
                if dist[x] >= self.max_hops:
                    continue
                for y in up.get(x, ()):
                    if y not in dist:
                        dist[y] = dist[x] + 1
                        if y == b:
                            return dist[y]
                        queue.append(y)
            return math.inf
        if rho_t.iri == str(RDF.type):
            return 1 if b is None or b in self.u.classes else math.inf

        rhos = self.validated(rho_t)
        if not rhos:
            return math.inf

        # Phase 0: superclass steps from phi(u).  Then one relation crossing.
        # Phase 1: superclass or subclass steps to phi(v).
        if a is not None:
            start = {a: 0}
            queue = deque([a])
            while queue:
                x = queue.popleft()
                for y in up.get(x, ()):
                    if y not in start and start[x] + 1 < self.max_hops:
                        start[y] = start[x] + 1
                        queue.append(y)
        else:
            start = None

        def cross(step, origins):
            """Nodes reached by following the properties of ``step`` in order."""
            frontier = origins
            for i, p in enumerate(step):
                nxt = {}
                for s, o in E.get(p, ()):
                    if frontier is None and i == 0:
                        base = 0
                    elif frontier is not None and s in frontier:
                        base = frontier[s]
                    else:
                        continue
                    cost = base + 1
                    if o not in nxt or cost < nxt[o]:
                        nxt[o] = cost
                frontier = nxt
                if not frontier:
                    return {}
            return frontier

        landed = {}
        for rho in rhos:
            for step in self._relation_steps(rho):
                for node, cost in cross(step, start).items():
                    if node not in landed or cost < landed[node]:
                        landed[node] = cost
        if not landed:
            return math.inf
        if b is None:
            return min(landed.values())

        best = math.inf
        dist = dict(landed)
        queue = deque(sorted(landed, key=lambda n: landed[n]))
        while queue:
            x = queue.popleft()
            if x == b:
                best = min(best, dist[x])
            if x == _LITERAL or dist[x] >= self.max_hops:
                continue
            for y in up.get(x, set()) | down.get(x, set()):
                if y not in dist or dist[x] + 1 < dist[y]:
                    dist[y] = dist[x] + 1
                    queue.append(y)
        return best

    def support_s(self, d):
        """s = 0 if d is infinite, else exp(-lambda (d - 1))."""
        return 0.0 if d == math.inf else math.exp(-self.lam * (d - 1))

    # -- structural fitness ------------------------------------------

    def _mappings(self, q):
        """Phi_q: joint validated mappings of the query's edge endpoints."""
        ends = sorted({t for a, _, b in self.patterns[q].edges
                       for t in (a, b) if t is not None}, key=lambda t: t.key)
        choices = [self.validated(t) or [None] for t in ends]
        count = 1
        for c in choices:
            count *= len(c)
        if count > _MAX_MAPPINGS:
            # Too many joint mappings: score each edge with its best mapping.
            return None, ends
        return [dict(zip(ends, combo)) for combo in product(*choices)], ends

    def structural_q(self, q):
        """F_S(q, O) and the per-edge distances of the best mapping."""
        edges = sorted(self.patterns[q].edges,
                       key=lambda e: tuple("" if t is None else t.key for t in e))
        if not edges:
            return None, {}
        total = sum(self._w(e, edge=True) for e in edges)
        if not total:
            return None, {}
        phis, ends = self._mappings(q)

        def score(phi):
            ds = {e: self.distance(e, phi) for e in edges}
            s = sum(self._w(e, edge=True) * self.support_s(d)
                    for e, d in ds.items()) / total
            return s, ds

        if phis is None:
            ds = {}
            for e in edges:
                best = math.inf
                ends_e = [t for t in (e[0], e[2]) if t is not None]
                for combo in product(*[self.validated(t) or [None]
                                       for t in ends_e]):
                    best = min(best, self.distance(e, dict(zip(ends_e, combo))))
                ds[e] = best
            s = sum(self._w(e, edge=True) * self.support_s(d)
                    for e, d in ds.items()) / total
            return s, ds
        return max((score(phi) for phi in phis), key=lambda x: x[0])

    def structural(self):
        return self.aggregate([self.structural_q(q)[0]
                               for q in range(len(self.patterns))])


def _load(ttl_file):
    g = Graph()
    for f in [ttl_file] if isinstance(ttl_file, (str, Path)) else ttl_file:
        g.parse(str(f), format="turtle")
    return g


def _evaluator(ttl_file, questions, **kwargs):
    g = _load(ttl_file)
    bindings = {p: str(ns) for p, ns in g.namespaces()}
    return FitnessEvaluator(g, load_query_patterns(questions, bindings), **kwargs)


def _name(t):
    return "*" if t is None else t.key.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def _edge_label(edge):
    a, p, b = edge
    return f"{_name(a)} --{_name(p)}--> {_name(b)}"


def _r(x):
    return None if x is None else round(x, 4)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def conceptual_fitness_v_0_1_0(ttl_file, questions=None, domain_prefixes=None,
                               domain_ns_fragments=None, weighting="canonical",
                               query_weights=None, mappings=None,
                               authorize_prefix_mapping=True):
    """
    Conceptual fitness F_C.

    Parameters
    ----------
    ttl_file : str, pathlib.Path, or list thereof
    questions : str, pathlib.Path, or list
        Any form accepted by :func:`load_query_patterns`.
    domain_prefixes, domain_ns_fragments : optional
        Accepted for the registry's calling convention; unused.
    weighting : {"canonical", "workload"}, optional
    query_weights : list of float, optional
        pi_q.  Default 1/|Q|.
    mappings : dict, optional
        Benchmark-authorised canonical mappings.
    authorize_prefix_mapping : bool, optional

    Returns
    -------
    MetricResult
        ``score`` is the workload F_C over exact and entailed support.
        ``detail`` holds ``aligned_score`` (F_C including aligned support),
        ``ambiguity`` (workload A_C), ``per_query`` values, and each
        requirement's support tier, mapping and workload weight.
        ``affected`` lists requirements with no exact or entailed support.
    """
    ev = _evaluator(ttl_file, questions, weighting=weighting,
                    query_weights=query_weights, mappings=mappings,
                    authorize_prefix_mapping=authorize_prefix_mapping)
    n = len(ev.patterns)
    score = ev.conceptual()
    aligned = ev.conceptual(aligned=True)
    ambiguity = ev.aggregate([ev.ambiguity_q(q) for q in range(n)])

    concepts = {}
    for c in sorted(set().union(*[p.concepts for p in ev.patterns]) if n
                    else (), key=lambda t: t.key):
        cands = ev.support.get(c, [])
        top = cands[0] if cands else None
        concepts[c.key] = {
            "tier": top[2] if top else None,
            "via": ev.via.get(c),
            "element": str(top[0]) if top else None,
            "mu": _r(ev.mu(c)),
            "mu_aligned": _r(ev.mu(c, aligned=True)),
            "candidates": len(cands),
            "w_work": _r(ev.w_work.get(c, 0.0)),
        }
    unsupported = [k for k, v in concepts.items() if not v["mu"]]
    tiers = {t: sum(1 for v in concepts.values() if v["tier"] == t)
             for t in (EXACT, ENTAILED, ALIGNED)}
    tiers["exact_via_prefix_mapping"] = sum(
        1 for v in concepts.values() if v["via"] == "prefix mapping")
    return MetricResult(
        metric_id="conceptualFitness", score=_r(score), passed=None,
        affected=unsupported, total_examined=len(concepts),
        detail={
            "aligned_score": _r(aligned),
            "ambiguity": _r(ambiguity),
            "weighting": weighting,
            "queries": n,
            "per_query": [
                {"qid": p.qid, "question": p.question,
                 "F_C": _r(ev.conceptual_q(q)),
                 "F_C_aligned": _r(ev.conceptual_q(q, aligned=True)),
                 "A_C": _r(ev.ambiguity_q(q)),
                 "unsupported": sorted(c.key for c in p.concepts
                                       if not ev.mu(c))}
                for q, p in enumerate(ev.patterns)],
            "tiers": tiers,
            "concepts": concepts,
        },
        message=f"F_C = {_r(score)} (exact/entailed), {_r(aligned)} with "
                f"aligned support; {len(unsupported)} of {len(concepts)} "
                f"requirements lack validated support",
    )


def structural_fitness_v_0_1_0(ttl_file, questions=None, domain_prefixes=None,
                               domain_ns_fragments=None, weighting="canonical",
                               query_weights=None, mappings=None,
                               authorize_prefix_mapping=True,
                               lam=DEFAULT_LAMBDA, max_hops=8):
    """
    Structural fitness F_S.

    Parameters
    ----------
    As :func:`conceptual_fitness_v_0_1_0`, plus:

    lam : float, optional
        lambda in s = exp(-lambda (d - 1)).  Default ln 2, so each step beyond
        the first halves
        the support.
    max_hops : int, optional

    Returns
    -------
    MetricResult
        ``score`` is the workload F_S.  ``detail`` holds ``path_coverage``
        and ``path_stretch`` (workload averages), ``per_query``
        values, and each task edge's distance d_O and support s under the
        best mapping.  ``affected`` lists edges with no admissible path.
    """
    ev = _evaluator(ttl_file, questions, weighting=weighting,
                    query_weights=query_weights, mappings=mappings,
                    authorize_prefix_mapping=authorize_prefix_mapping,
                    lam=lam, max_hops=max_hops)
    per_query, coverage, stretch, edges, missing_q = [], [], [], {}, []
    for q in range(len(ev.patterns)):
        s, ds = ev.structural_q(q)
        per_query.append(s)
        missing_q.append(sorted(_edge_label(e) for e, d in ds.items()
                                if d == math.inf))
        if not ds:
            coverage.append(None)
            stretch.append(None)
            continue
        finite = [d for d in ds.values() if d != math.inf]
        coverage.append(len(finite) / len(ds))
        stretch.append(sum(finite) / len(finite) if finite else None)
        for e, d in ds.items():
            label = _edge_label(e)
            prev = edges.get(label)
            if prev is None or (d != math.inf and
                                (prev["d"] is None or d < prev["d"])):
                edges[label] = {"d": None if d == math.inf else d,
                                "s": _r(ev.support_s(d))}
    score = ev.aggregate(per_query)
    missing = [k for k, v in edges.items() if v["d"] is None]
    return MetricResult(
        metric_id="structuralFitness", score=_r(score), passed=None,
        affected=missing, total_examined=len(edges),
        detail={
            "path_coverage": _r(ev.aggregate(coverage)),
            "path_stretch": _r(ev.aggregate(stretch)),
            "lambda": lam, "weighting": weighting,
            "per_query": [{"qid": p.qid, "question": p.question,
                           "F_S": _r(s), "path_coverage": _r(c),
                           "path_stretch": _r(t), "unrealised": m}
                          for p, s, c, t, m in zip(ev.patterns, per_query,
                                                   coverage, stretch,
                                                   missing_q)],
            "edges": edges,
        },
        message=f"F_S = {_r(score)}; {len(edges) - len(missing)} of "
                f"{len(edges)} task edges have an admissible schema path",
    )


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def _spearman(x, y):
    if len(x) < 2:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / math.sqrt(vx * vy) if vx and vy else None


def counterfactual_importance_v_0_1_0(ttl_file, questions=None,
                                      domain_prefixes=None,
                                      domain_ns_fragments=None,
                                      benchmark=None, mappings=None,
                                      authorize_prefix_mapping=True):
    """
    Counterfactual concept importance w_c^impact.

    Z is the score of a benchmark suite with expected answers, run by
    :func:`ontocheck.benchmark.assess_impact`.  The requirements C_Q are the
    IRIs the suite's queries name, mapped to the ontology through exact and
    entailed support.  Removing a requirement uses the benchmark's own
    concept and relation ablation.

    Parameters
    ----------
    ttl_file : str, pathlib.Path, or list thereof
    questions : optional
        A benchmark suite may be passed here instead of *benchmark*.
    benchmark : str or pathlib.Path, optional
        The benchmark suite ``.json``.
    mappings, authorize_prefix_mapping : optional
        As for :func:`conceptual_fitness_v_0_1_0`.

    Returns
    -------
    MetricResult
        ``score`` is the Spearman correlation between w_c^work and
        w_c^impact over the requirements, which validates the workload
        weights.  ``None`` when every removal leaves Z unchanged.
        ``detail["weights"]`` gives each requirement's raw drop
        Z(O) - Z(O^{-c}), w_c^impact (positive drops normalised to sum to 1)
        and w_c^work.  ``affected`` lists requirements by importance.
    """
    from .benchmark import assess_impact, load_suite
    from .benchmark.impact import ontology_concepts, ontology_relations

    suite_path = benchmark
    if suite_path is None and isinstance(questions, (str, Path)):
        try:
            data = json.loads(Path(str(questions)).read_text(encoding="utf-8"))
            if isinstance(data, dict) and "cases" in data:
                suite_path = questions
        except (OSError, ValueError):
            pass
    if suite_path is None:
        return MetricResult(
            metric_id="counterfactualImportance",
            status="Skipped (requires a benchmark suite with expected answers)",
            message="Counterfactual importance needs Z, a downstream score; "
                    "pass a benchmark suite.",
        )

    ev = _evaluator(ttl_file, suite_path, mappings=mappings,
                    authorize_prefix_mapping=authorize_prefix_mapping)
    classes = set(ontology_concepts(ev.g))
    relations = set(ontology_relations(ev.g))
    requirement = {}
    for p in ev.patterns:
        for c in p.concepts:
            targets = ev.validated(c)
            if targets:
                requirement[c] = targets[0]

    report = assess_impact(
        load_suite(suite_path), ev.g,
        concepts=sorted({e for e in requirement.values() if e in classes},
                        key=str),
        relations=sorted({e for e in requirement.values()
                          if e in relations and e not in classes}, key=str),
    )
    drop = {URIRef(row.symbol): row.delta for row in report.rows}
    positive = sum(max(d, 0.0) for d in drop.values())

    weights, x, y = {}, [], []
    for c, e in sorted(requirement.items(), key=lambda kv: kv[0].key):
        if e not in drop:
            continue
        impact = max(drop[e], 0.0) / positive if positive else 0.0
        work = ev.w_work.get(c, 0.0)
        weights[c.key] = {"element": str(e), "drop": _r(drop[e]),
                          "w_impact": _r(impact), "w_work": _r(work)}
        x.append(work)
        y.append(impact)
    rho = _spearman(x, y) if positive else None
    ranked = sorted(weights, key=lambda k: -(weights[k]["w_impact"] or 0))
    return MetricResult(
        metric_id="counterfactualImportance", score=_r(rho), passed=None,
        affected=[k for k in ranked if weights[k]["w_impact"]],
        total_examined=len(weights),
        detail={"Z_baseline": _r(report.baseline), "weights": weights,
                "unmapped_requirements": sorted(
                    c.key for p in ev.patterns for c in p.concepts
                    if c not in requirement)},
        message=(f"Spearman(w_work, w_impact) = {_r(rho)} over "
                 f"{len(weights)} requirements; Z(O) = {_r(report.baseline)}"
                 if positive else
                 f"No single removal changes Z(O) = {_r(report.baseline)}; "
                 f"w_impact is zero for all {len(weights)} requirements"),
    )


# Plain names, as the metrics are called in the CLI.  The
# version suffix follows the package convention.
conceptual_fitness = conceptual_fitness_v_0_1_0
structural_fitness = structural_fitness_v_0_1_0
counterfactual_importance = counterfactual_importance_v_0_1_0


for _id, _name_, _fn, _scale, _desc in (
    ("conceptualFitness", "Conceptual fitness", conceptual_fitness,
     Scale.PROPORTION, "F_C: weighted exact/entailed support for the "
     "workload's required concepts."),
    ("structuralFitness", "Structural fitness", structural_fitness,
     Scale.PROPORTION, "F_S: support of the task edges by minimum-cost "
     "admissible schema paths."),
    ("counterfactualImportance", "Counterfactual concept importance",
     counterfactual_importance, Scale.RAW, "Agreement of workload weights "
     "with benchmark impact weights; needs a benchmark suite."),
):
    register_metric(MetricDescriptor(
        metric_id=_id, name=_name_, function=_fn, category=Category.TASK_BASED,
        source_framework=SourceFramework.ONTOCHECK, severity=Severity.INFO,
        scale=_scale, higher_is_better=True, requires_questions=True,
        description=_desc,
    ))
