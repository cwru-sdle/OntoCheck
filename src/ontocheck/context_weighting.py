"""
Context-weighted normalisation of OntoCheck metrics.

Every metric in OntoCheck treats each class and property as equally
important: OOPS! P08 reports 77 unannotated terms out of 318 whether those 77
are the terms a scientist's questions depend on or terms nobody will ever
query.  This module re-weights the metrics by *context*, so that a defect
counts in proportion to how much the entity it affects matters.

Two contexts are supported, alone or together:

* **Query context** -- the competency questions (natural language and/or
  SPARQL).  Query terms are anchored to ontology entities by exact IRI
  resolution or by a similarity metric over labels, then the anchor weights
  are spread through the class hierarchy to the terms the answers depend on.
* **Instance context** -- the ABox.  A class with more instances gets more
  weight, since defects on heavily populated classes affect more data.

The question the normalised score answers is "how well does this ontology
answer *these* questions?", so query weight spreads along dependency -- to
the entities a query's answer depends on -- not to whatever is nearby.

Pipeline
--------
1. ``anchor_queries``   query text  -> seed similarities s(e) in [0, 1]
2. ``spread_weights``   seeds       -> w_Q(e) along query dependencies
3. ``instance_weights`` ABox        -> w_I(e) = 1 + f(instance count)
4. ``build_context``    w(e) = w_Q(e) * w_I(e)  (either factor optional)
5. ``normalize_results`` re-score each ``MetricResult`` under w

Definitions
-----------
- Weighted defect rate: for a metric over population P with affected set
  A, ``sum(w[a] for a in A) / sum(w[p] for p in P)``.  With uniform weights
  this is exactly ``|A| / |P|``, so every normalised value has an unweighted
  counterpart (``uniform_rate``) computed over the same population.

- Weighted OQuaRE value: the OQuaRE metrics are means of a per-class
  quantity, so the contextual value is the weighted mean of that quantity.
  With uniform weights it reproduces the unweighted metric.

- Effective support: Kish's effective sample size ``(sum w)^2 / sum w^2``
  over the population.  A weighted score resting on two classes is reported
  as such, rather than looking as authoritative as one over three hundred.

- Ontology-level metrics (FOOPS! metadata and accessibility tests, OOPS! P37
  to P41) concern the ontology document, not any term.  No entity weighting
  can change them, so they are passed through with ``normalizable=False``.

Version: 0.0.1
"""

import json
import logging
import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rdflib import Graph, Literal, OWL, RDF, RDFS, SKOS, URIRef

from .helpers.oops_helpers import (
    _is_foundational,
    _local_name,
    _named_classes,
    _named_properties,
    _own_namespace,
    _split_identifier,
)
from .helpers.semantic_helpers import _individuals, _is_opaque_identifier
from .metric_registry import METRIC_REGISTRY, MetricResult, Scale

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entity universe
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset("""
a an and any are as at be been by can do does for from has have how in into
is it its of on or that the their them there these this those to was what
when where which who whom whose why will with within without all each every
our we you your i me my they which per than then also not no more most
""".split())


def _norm_text(text):
    """Lower-case word tokens of an identifier or label, space-joined."""
    return " ".join(_split_identifier(re.sub(r"[^\w\s\-]", " ", str(text))))


class EntityUniverse:
    """
    The entities a context weight can be attached to, and their structure.

    Definitions
    -----------
    - Classes: named classes (as in OQuaRE's primitives), excluding
      ``owl:Thing`` and foundational-namespace terms.
    - Properties: named object, datatype, annotation and RDF properties,
      excluding foundational-namespace terms.
    - Individuals: as returned by
      :func:`~ontocheck.helpers.semantic_helpers._individuals`.
    - Neighbours: ``rdfs:subClassOf`` and ``rdfs:subPropertyOf`` edges
      (directional, up/down), plus attachment edges between a property and
      its declared domain and range classes.

    Version: 0.0.1

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph, optionally with instance data.
    """

    def __init__(self, g):
        self.g = g
        self.classes = {
            c for c in _named_classes(g)
            if c != OWL.Thing and not _is_foundational(c)
        }
        self.properties = {
            p for p in _named_properties(g) if not _is_foundational(p)
        }
        self.individuals = {
            i: {t for t in types if t in self.classes}
            for i, types in _individuals(g).items()
            if isinstance(i, URIRef)
        }
        own = _own_namespace(g)
        self.own_namespace = own

        self.up = defaultdict(set)
        self.down = defaultdict(set)
        self.attach = defaultdict(set)
        for pred, members in ((RDFS.subClassOf, self.classes),
                              (RDFS.subPropertyOf, self.properties)):
            for s, o in g.subject_objects(pred):
                if s in members and o in members and s != o:
                    self.up[s].add(o)
                    self.down[o].add(s)
        for p in self.properties:
            for pred in (RDFS.domain, RDFS.range):
                for c in g.objects(p, pred):
                    if c in self.classes:
                        self.attach[p].add(c)
                        self.attach[c].add(p)

        self.by_local_name = defaultdict(set)
        for e in self.terms:
            self.by_local_name[_local_name(e)].add(e)

    @property
    def terms(self):
        """Classes and properties."""
        return self.classes | self.properties

    @property
    def entities(self):
        """Classes, properties and individuals."""
        return self.terms | set(self.individuals)

    def is_own(self, entity):
        """Whether *entity* is minted in the ontology's own namespace."""
        if not self.own_namespace:
            return True
        return str(entity).startswith(self.own_namespace)

    def lexical_forms(self, entity):
        """
        Return the normalised surface forms used to match query text.

        The local name (unless opaque, e.g. ``ont00001857``) and every
        ``rdfs:label``, ``skos:prefLabel`` and ``skos:altLabel``.
        """
        forms = set()
        name = _local_name(entity)
        if name and not _is_opaque_identifier(name):
            forms.add(_norm_text(name))
        for p in (RDFS.label, SKOS.prefLabel, SKOS.altLabel):
            for o in self.g.objects(entity, p):
                if isinstance(o, Literal) and str(o).strip():
                    forms.add(_norm_text(o))
        forms.discard("")
        return forms


# ---------------------------------------------------------------------------
# Similarity backends
# ---------------------------------------------------------------------------

class LexicalMatcher:
    """
    Character-trigram TF-IDF cosine similarity between query spans and labels.

    Dependency-free and robust to the lexical variation common in ontology
    labels -- camel case, hyphenation, plurals -- so ``"x-ray detectors"``
    matches ``XrayDetector``.  Identical normalised strings score 1.0.

    Version: 0.0.1

    Parameters
    ----------
    threshold : float, optional
        Minimum cosine similarity for a span to anchor an entity.  The
        default 0.8 is deliberately strict: query context should begin from
        *exact* anchors and reach related terms through the hierarchy, not
        through loose string similarity.
    """

    name = "lexical"

    def __init__(self, threshold=0.8):
        self.threshold = threshold
        self._forms = []
        self._index = defaultdict(list)
        self._exact = defaultdict(set)
        self._idf = {}

    @staticmethod
    def _grams(text):
        padded = f" {text} "
        out = defaultdict(int)
        for i in range(len(padded) - 2):
            out[padded[i:i + 3]] += 1
        return out

    def _vector(self, text):
        vec = {g: tf * self._idf.get(g, self._default_idf)
               for g, tf in self._grams(text).items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {g: v / norm for g, v in vec.items()}

    def fit(self, forms):
        """
        Index entity surface forms.

        Parameters
        ----------
        forms : dict
            Mapping from entity to a set of normalised surface forms.
        """
        self._forms = [(e, f) for e, fs in forms.items() for f in fs]
        df = defaultdict(int)
        for _, f in self._forms:
            for g in self._grams(f):
                df[g] += 1
        n = max(len(self._forms), 1)
        self._idf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in df.items()}
        self._default_idf = math.log(1 + n) + 1
        self._index = defaultdict(list)
        self._exact = defaultdict(set)
        for i, (e, f) in enumerate(self._forms):
            self._exact[f].add(e)
            for g, v in self._vector(f).items():
                self._index[g].append((i, v))
        return self

    def score(self, span):
        """
        Return ``[(entity, form, similarity)]`` for forms above threshold.
        """
        hits = {e: (span, 1.0) for e in self._exact.get(span, ())}
        dots = defaultdict(float)
        for g, v in self._vector(span).items():
            for i, w in self._index.get(g, ()):
                dots[i] += v * w
        for i, sim in dots.items():
            if sim < self.threshold:
                continue
            e, f = self._forms[i]
            if e not in hits or hits[e][1] < sim:
                hits[e] = (f, min(sim, 1.0))
        return [(e, f, s) for e, (f, s) in hits.items()]


class EmbeddingMatcher:
    """
    Cosine similarity in an embedding space.

    Version: 0.0.1

    Parameters
    ----------
    embed : callable
        ``embed(list_of_str) -> list of vectors``.  Any sentence-embedding
        model fits; see :func:`sentence_transformer_matcher`.
    threshold : float, optional
        Minimum cosine similarity.  Embedding similarities run higher than
        lexical ones for unrelated text, so the default is 0.75; calibrate it
        for the model in use.
    """

    name = "embedding"

    def __init__(self, embed, threshold=0.75):
        self.embed = embed
        self.threshold = threshold
        self._forms = []
        self._vectors = []

    @staticmethod
    def _unit(v):
        v = [float(x) for x in v]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def fit(self, forms):
        self._forms = [(e, f) for e, fs in forms.items() for f in fs]
        texts = [f for _, f in self._forms]
        self._vectors = [self._unit(v) for v in self.embed(texts)] if texts else []
        return self

    def score(self, span):
        q = self._unit(self.embed([span])[0])
        hits = {}
        for (e, f), v in zip(self._forms, self._vectors):
            sim = sum(a * b for a, b in zip(q, v))
            if sim >= self.threshold and (e not in hits or hits[e][1] < sim):
                hits[e] = (f, min(sim, 1.0))
        return [(e, f, s) for e, (f, s) in hits.items()]


def sentence_transformer_matcher(model_name="all-MiniLM-L6-v2", threshold=0.75):
    """
    Build an :class:`EmbeddingMatcher` backed by ``sentence-transformers``.

    Raises
    ------
    ImportError
        If ``sentence-transformers`` is not installed.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError(
            "sentence_transformer_matcher requires sentence-transformers "
            "(pip install sentence-transformers)"
        ) from e
    model = SentenceTransformer(model_name)
    return EmbeddingMatcher(lambda texts: model.encode(list(texts)), threshold)


# ---------------------------------------------------------------------------
# Query loading and anchoring
# ---------------------------------------------------------------------------

_SPARQL_KEYWORDS = re.compile(
    r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE|PREFIX)\b", re.IGNORECASE
)
_PREFIX_DECL = re.compile(r"PREFIX\s+([A-Za-z][\w\-]*)?:\s*<([^>]*)>", re.I)
_FULL_IRI = re.compile(r"<([^<>\s]+)>")
_PREFIXED = re.compile(
    r"(?<![\w?$<:/#])([A-Za-z][\w\-]*)?:([A-Za-z_][\w\-.]*)"
)


def load_queries(source):
    """
    Normalise any supported query source to a list of query strings.

    Accepted forms: a list of strings or of dicts; a ``.json`` file holding a
    list of competency questions (``question`` and/or ``sparql_query`` keys)
    or a benchmark suite (``cases[].prompt`` and ``cases[].query.text``); a
    ``.md`` file with fenced ``sparql`` blocks; or a single string.  A dict
    contributes its natural-language question and its SPARQL as one query,
    so both anchor the same question.

    Returns
    -------
    list of str
    """
    if isinstance(source, (str, Path)) and Path(str(source)).suffix in (
        ".json", ".md"
    ) and Path(str(source)).exists():
        path = Path(str(source))
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            return re.findall(r"```sparql\s*(.*?)```", text, re.DOTALL)
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cases" in data:
            data = [
                {"question": c.get("prompt", ""),
                 "sparql_query": (c.get("query") or {}).get("text", "")}
                for c in data["cases"]
            ]
        return load_queries(data)
    if isinstance(source, str):
        return [source]
    out = []
    for item in source or []:
        if isinstance(item, dict):
            parts = [item.get(k) for k in ("question", "prompt", "sparql_query")]
            text = "\n".join(p for p in parts if isinstance(p, str) and p)
            if text:
                out.append(text)
        elif item:
            out.append(str(item))
    return out


@dataclass
class Anchor:
    """
    One query-to-entity match.

    Attributes
    ----------
    entity : rdflib.URIRef
    similarity : float
        In [0, 1]; 1.0 for an exact IRI or exact label match.
    query_index : int
    span : str
        The query text or term that matched.
    form : str
        The entity's surface form (or IRI) it matched.
    method : str
        ``"iri"``, ``"local_name"``, or the matcher's name.
    """

    entity: URIRef
    similarity: float
    query_index: int
    span: str
    form: str
    method: str


def _sparql_anchors(text, universe, bindings):
    """Exact anchors for the IRIs and prefixed names in a SPARQL query."""
    prefixes = dict(bindings)
    for p, ns in _PREFIX_DECL.findall(text):
        prefixes[p or ""] = ns
    body = _PREFIX_DECL.sub(" ", text)
    body = re.sub(r'"[^"]*"|\'[^\']*\'', " ", body)   # drop literals

    candidates = [(iri, iri, _local_name(iri)) for iri in _FULL_IRI.findall(body)]
    for p, local in _PREFIXED.findall(_FULL_IRI.sub(" ", body)):
        local = local.rstrip(".-")
        ns = prefixes.get(p or "")
        candidates.append((f"{p}:{local}", (ns + local) if ns else None, local))

    out = []
    for span, iri, local in candidates:
        if iri and _is_foundational(iri):
            continue
        if iri and URIRef(iri) in universe.entities:
            out.append((URIRef(iri), 1.0, span, iri, "iri"))
            continue
        # The query's namespace often differs from the ontology's own (the
        # MDS files embed one IRI inside another), so fall back to the local
        # name, which is how ``task_based_metric`` matches terms too.
        for e in universe.by_local_name.get(local, ()):
            out.append((e, 1.0, span, str(e), "local_name"))
    return out


def _spans(text, max_len=4):
    """Contiguous token n-grams that neither start nor end on a stopword."""
    tokens = _norm_text(text).split()
    out = []
    for n in range(min(max_len, len(tokens)), 0, -1):
        for i in range(len(tokens) - n + 1):
            gram = tokens[i:i + n]
            if gram[0] in _STOPWORDS or gram[-1] in _STOPWORDS:
                continue
            if all(t.isdigit() for t in gram):
                continue
            out.append((i, i + n, " ".join(gram)))
    return out


def _text_anchors(text, matcher, top_k):
    """
    Anchors for natural-language text, by maximal munch over spans.

    Longer spans are matched first; a shorter span inside an already matched
    one is skipped, so "x-ray detector" anchors ``XrayDetector`` and not also
    ``Detector`` -- the latter is reached through the hierarchy instead.
    """
    covered = set()
    out = []
    for start, end, span in _spans(text):
        if any(i in covered for i in range(start, end)):
            continue
        hits = sorted(matcher.score(span), key=lambda h: -h[2])[:top_k]
        if not hits:
            continue
        covered.update(range(start, end))
        out.extend((e, s, span, f, matcher.name) for e, f, s in hits)
    return out


def anchor_queries(universe, queries, matcher=None, top_k=3):
    """
    Match query terms to ontology entities.

    Definitions
    -----------
    - SPARQL: every full IRI and prefixed name is resolved against the
      query's ``PREFIX`` declarations and the ontology's bindings, then
      against local names.  These are exact anchors (similarity 1.0).
    - Natural language: spans are scored against every entity's labels and
      local name with *matcher*; at most *top_k* entities per span.
    - A query containing both (a competency question with its SPARQL) is
      anchored by both.

    Version: 0.0.1

    Parameters
    ----------
    universe : EntityUniverse
    queries : list of str
    matcher : LexicalMatcher or EmbeddingMatcher, optional
        Defaults to :class:`LexicalMatcher`.
    top_k : int, optional

    Returns
    -------
    list of Anchor
    """
    matcher = matcher or LexicalMatcher()
    matcher.fit({e: universe.lexical_forms(e) for e in universe.terms})
    bindings = {p: str(ns) for p, ns in universe.g.namespaces()}

    anchors = []
    for qi, text in enumerate(queries):
        found = []
        if _SPARQL_KEYWORDS.search(text):
            found.extend(_sparql_anchors(text, universe, bindings))
            # Natural-language lines that accompany the SPARQL.
            nl = "\n".join(
                line for line in text.splitlines()
                if not _SPARQL_KEYWORDS.search(line)
                and not re.search(r"[{}?<>]|\w:\w", line)
            )
            if nl.strip():
                found.extend(_text_anchors(nl, matcher, top_k))
        else:
            found.extend(_text_anchors(text, matcher, top_k))
        best = {}
        for e, s, span, form, method in found:
            if e not in best or best[e].similarity < s:
                best[e] = Anchor(e, s, qi, span, form, method)
        anchors.extend(best.values())
    return anchors


# ---------------------------------------------------------------------------
# Weight construction
# ---------------------------------------------------------------------------

def spread_weights(universe, seeds, decay_up=0.5, decay_down=1.0,
                   decay_attach=1.0, max_hops=None):
    """
    Spread seed weights to the entities a query's answer depends on.

    Definitions
    -----------
    Spreading follows *dependency*, not proximity: an entity gets weight only
    if a defect there can change what the query returns.

    - Down (subclasses, subproperties), full strength by default: instances
      of every subclass of an anchored class answer the query.
    - Attach (property to its domain and range classes), full strength by
      default: a query using a property depends on those classes, and then on
      their subclasses.
    - Up (superclasses, superproperties), decayed: an anchor inherits the
      axioms of its ancestors, but each step up matters less.

    Paths are monotone: once a path moves up it only moves up, and once it
    moves down it only moves down.  So siblings and cousins -- reachable only
    by going up and then down -- are not reached; they do not affect the
    query's answers.

    - w_Q(e): the largest ``seed weight * path weight`` over seeds, where a
      path's weight is the product of its decays.  A maximum, not a sum, so a
      generic ancestor shared by many anchors cannot outweigh the anchors.

    Version: 0.0.2

    Parameters
    ----------
    universe : EntityUniverse
    seeds : dict
        Entity to seed weight.
    decay_up, decay_down, decay_attach : float, optional
        Per-hop multipliers for the three moves.
    max_hops : int or None, optional
        Maximum path length; ``None`` (default) for unlimited.

    Returns
    -------
    dict
        Entity to weight; entities not reached are absent (weight 0).
    """
    weights = defaultdict(float)
    for seed, s in seeds.items():
        # State: (entity, mode).  "seed" may go up, down or attach;
        # "attached" (a class reached from a property) may go up or down.
        best = {(seed, "seed"): 1.0}
        frontier = deque([(seed, "seed", 1.0, 0)])
        while frontier:
            node, mode, m, hops = frontier.popleft()
            if best.get((node, mode), 0.0) > m:
                continue
            if max_hops is not None and hops >= max_hops:
                continue
            moves = []
            if mode in ("seed", "attached", "up"):
                moves.append((universe.up.get(node, ()), decay_up, "up"))
            if mode in ("seed", "attached", "down"):
                moves.append((universe.down.get(node, ()), decay_down, "down"))
            if mode == "seed" and node in universe.properties:
                moves.append((universe.attach.get(node, ()), decay_attach,
                              "attached"))
            for nbrs, d, nmode in moves:
                nm = m * d
                for nb in nbrs:
                    if nm > best.get((nb, nmode), 0.0):
                        best[(nb, nmode)] = nm
                        frontier.append((nb, nmode, nm, hops + 1))
        for (e, _), m in best.items():
            weights[e] = max(weights[e], s * m)
    return dict(weights)


def instance_counts(universe, propagate=True):
    """
    Count instances per class and ABox usages per property.

    Parameters
    ----------
    universe : EntityUniverse
    propagate : bool, optional
        Whether an instance of a class also counts for its superclasses
        (each individual is counted once per ancestor, however many paths
        lead there).  Default ``True``.

    Returns
    -------
    dict
        Entity to count.
    """
    members = defaultdict(set)
    for ind, types in universe.individuals.items():
        for t in types:
            members[t].add(ind)
            if propagate:
                seen, queue = set(), deque(universe.up.get(t, ()))
                while queue:
                    a = queue.popleft()
                    if a in seen:
                        continue
                    seen.add(a)
                    members[a].add(ind)
                    queue.extend(universe.up.get(a, ()))
    counts = {c: len(m) for c, m in members.items()}
    for s, p, _ in universe.g:
        if p in universe.properties and s in universe.individuals:
            counts[p] = counts.get(p, 0) + 1
    return counts


_INSTANCE_TRANSFORMS = {
    "log": math.log1p,
    "sqrt": math.sqrt,
    "linear": float,
}


def instance_weights(universe, mode="log", propagate=True):
    """
    Weight entities by how much instance data they carry.

    ``w_I(e) = 1 + f(n(e))`` with ``f`` one of ``log1p`` (default),
    ``sqrt`` or identity.  The baseline of 1 keeps an uninstantiated class in
    the population rather than discarding it; the logarithm keeps one class
    with ten thousand instances from drowning out everything else, since
    instance counts are typically heavy-tailed.

    Returns
    -------
    dict
        Entity to weight, for every entity in the universe.
    """
    f = _INSTANCE_TRANSFORMS[mode]
    counts = instance_counts(universe, propagate)
    return {e: 1.0 + f(counts.get(e, 0)) for e in universe.entities}


@dataclass
class ContextWeights:
    """
    Per-entity weights for one assessment context.

    Attributes
    ----------
    universe : EntityUniverse
    weights : dict
        Final weight per entity; absent means 0.
    query_weights : dict or None
        ``w_Q`` before combination, rescaled to a maximum of 1.
    instance_weights : dict or None
        ``w_I`` before combination.
    anchors : list of Anchor
    params : dict
        Every setting used, for reporting alongside the scores.
    """

    universe: EntityUniverse
    weights: Dict[Any, float]
    query_weights: Optional[Dict[Any, float]] = None
    instance_weights: Optional[Dict[Any, float]] = None
    anchors: List[Anchor] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, entity):
        return self.weights.get(URIRef(str(entity)), 0.0)

    def top(self, n=10):
        """The *n* highest-weighted entities."""
        return sorted(self.weights.items(), key=lambda kv: -kv[1])[:n]

    def explain(self, entity):
        """Return the components of one entity's weight."""
        e = URIRef(str(entity))
        return {
            "entity": str(e),
            "weight": self.weights.get(e, 0.0),
            "query_weight": (self.query_weights or {}).get(e),
            "instance_weight": (self.instance_weights or {}).get(e),
            "anchors": [a for a in self.anchors if a.entity == e],
        }


def build_context(ttl_files, queries=None, use_instances="auto",
                  matcher=None, top_k=3, decay_up=0.5, decay_down=1.0,
                  decay_attach=1.0, max_hops=None, background=0.0,
                  instance_mode="log", propagate_instances=True):
    """
    Build context weights from competency questions and/or instance data.

    Version: 0.0.1

    Parameters
    ----------
    ttl_files : str, pathlib.Path, list thereof, or rdflib.Graph
        Ontology (and optionally instance data) to weight.
    queries : any form accepted by :func:`load_queries`, optional
        ``None`` disables query context.
    use_instances : bool or ``"auto"``, optional
        ``"auto"`` (default) enables instance context when the graph has
        individuals.
    matcher : LexicalMatcher or EmbeddingMatcher, optional
    top_k : int, optional
        Maximum entities anchored per natural-language span.
    decay_up, decay_down, decay_attach, max_hops : optional
        See :func:`spread_weights`.
    background : float, optional
        Weight added to every term's query weight, so that entities the
        queries never reach still count a little.  Default 0: out-of-context
        entities do not affect the normalised scores at all.
    instance_mode : {"log", "sqrt", "linear"}, optional
    propagate_instances : bool, optional

    Returns
    -------
    ContextWeights
        With neither context the weights are uniform (1.0), and every
        normalised score equals its unweighted counterpart.
    """
    if isinstance(ttl_files, Graph):
        g = ttl_files
    else:
        g = Graph()
        for f in [ttl_files] if isinstance(ttl_files, (str, Path)) else ttl_files:
            g.parse(str(f), format="turtle")
    universe = EntityUniverse(g)

    params = {
        "matcher": getattr(matcher, "name", "lexical"),
        "threshold": getattr(matcher, "threshold", 0.8),
        "top_k": top_k, "decay_up": decay_up, "decay_down": decay_down,
        "decay_attach": decay_attach, "max_hops": max_hops,
        "background": background, "instance_mode": instance_mode,
        "propagate_instances": propagate_instances,
    }

    anchors, w_q = [], None
    if queries is not None:
        qs = load_queries(queries)
        anchors = anchor_queries(universe, qs, matcher, top_k)
        # Seed weight: best similarity, scaled sub-linearly by the number of
        # queries anchoring the entity, so a term central to the question set
        # counts more without a generic relation used in every query
        # swamping the rest.
        best_sim, hits = defaultdict(float), defaultdict(int)
        for a in anchors:
            best_sim[a.entity] = max(best_sim[a.entity], a.similarity)
            hits[a.entity] += 1
        seeds = {e: s * (1.0 + math.log(hits[e])) for e, s in best_sim.items()}
        spread = spread_weights(universe, seeds, decay_up, decay_down,
                                decay_attach, max_hops)
        peak = max(spread.values(), default=0.0)
        w_q = {e: v / peak for e, v in spread.items()} if peak else {}
        # An individual is part of a query's answer exactly when one of its
        # classes is, so it takes the largest query weight among its types.
        for ind, types in universe.individuals.items():
            inherited = max((w_q.get(t, 0.0) for t in types), default=0.0)
            if inherited > w_q.get(ind, 0.0):
                w_q[ind] = inherited
        if background:
            for e in universe.entities:
                w_q[e] = w_q.get(e, 0.0) + background
        params["query_count"] = len(qs)
        params["anchored_entities"] = len(seeds)
        if not seeds:
            logger.warning(
                "No query term matched any ontology entity; every normalised "
                "score will be undefined. Lower the matcher threshold or "
                "check the query prefixes."
            )

    if use_instances == "auto":
        use_instances = bool(universe.individuals)
    w_i = instance_weights(universe, instance_mode, propagate_instances) \
        if use_instances else None
    params["use_instances"] = bool(use_instances)
    params["individuals"] = len(universe.individuals)

    if w_q is None and w_i is None:
        weights = {e: 1.0 for e in universe.entities}
    elif w_i is None:
        weights = dict(w_q)
    elif w_q is None:
        weights = dict(w_i)
    else:
        weights = {e: v * w_i.get(e, 1.0) for e, v in w_q.items()}

    return ContextWeights(universe, weights, w_q, w_i, anchors, params)


# ---------------------------------------------------------------------------
# Metric normalisation
# ---------------------------------------------------------------------------

# Population each entity-level metric is computed over: (kind, own_only).
# ``kind`` is one of "class", "property", "term" (class or property) and
# "entity" (term or individual); ``own_only`` restricts the population to the
# ontology's own namespace, as the metric itself does.  Metrics absent from
# this table have their kind inferred from their affected entities, or are
# treated as ontology-level when they name none.
METRIC_SCOPE = {
    "oopsP01Polysemy": ("term", False),
    "oopsP02SynonymClasses": ("class", False),
    "oopsP03IsRelationship": ("property", False),
    "oopsP04Unconnected": ("term", True),
    "oopsP05WrongInverse": ("property", False),
    "oopsP06Cycles": ("class", False),
    "oopsP07MergedConcepts": ("class", False),
    "oopsP08MissingAnnotations": ("term", True),
    "oopsP10Disjointness": ("class", False),
    "oopsP11MissingDomainRange": ("property", True),
    "oopsP12UndeclaredEquivProperty": ("property", False),
    "oopsP13UndeclaredInverse": ("property", False),
    "oopsP14MisusedAllValuesFrom": ("class", False),
    "oopsP15SomeNot": ("class", False),
    "oopsP16PrimitiveNotDefined": ("class", False),
    "oopsP17OverspecializedHierarchy": ("class", False),
    "oopsP18OverspecializedDomainRange": ("property", False),
    "oopsP19MultipleDomainRange": ("property", False),
    "oopsP20MisusedAnnotations": ("term", False),
    "oopsP21MiscellaneousClass": ("class", False),
    "oopsP22NamingConventions": ("term", True),
    "oopsP23DuplicatedDatatype": ("class", False),
    "oopsP24RecursiveDefinition": ("term", False),
    "oopsP25SelfInverse": ("property", False),
    "oopsP26SymmetricWithInverse": ("property", False),
    "oopsP27WrongEquivProperty": ("property", False),
    "oopsP28WrongSymmetric": ("property", False),
    "oopsP29WrongTransitive": ("property", False),
    "oopsP30UndeclaredEquivClass": ("class", False),
    "oopsP31WrongEquivClass": ("class", False),
    "oopsP32SameLabel": ("class", False),
    "oopsP33SinglePropertyChain": ("property", False),
    "oopsP34UntypedClass": ("class", False),
    "oopsP35UntypedProperty": ("property", False),
    "oopsP36UriFileExtension": ("term", False),
    "oopsP40NamespaceHijacking": ("term", False),
    "foopsVOC3AllTermsLabelled": ("entity", True),
    "foopsVOC4AllTermsDefined": ("entity", True),
}

# Metrics whose affected list is not a set of ontology entities.  P09 lists
# query terms the ontology lacks -- there is nothing in the ontology to weight.
_NOT_ENTITY_LEVEL = {"oopsP09MissingDomainInfo"}


@dataclass
class NormalizedMetric:
    """
    A metric re-scored under a context.

    Attributes
    ----------
    metric_id : str
    raw_score : object
        The metric's own score, unchanged.
    normalizable : bool
        ``False`` for ontology-level metrics and those that did not run.
    scope : str
        Population kind, ``"oquare"``, or ``"ontology"``.
    population : int
        Number of entities in the population.
    uniform_value : float or None
        The quantity under uniform weights over the same population: a defect
        rate for entity metrics, the metric itself for OQuaRE.
    weighted_value : float or None
        The same quantity under the context weights.  ``None`` when no
        population entity has positive weight.
    weighted_score : object
        *weighted_value* expressed in the metric's own direction: ``1 - rate``
        for proportion metrics, the rate for counts, the weighted OQuaRE
        value for OQuaRE.
    effective_support : float
        Kish effective sample size of the weights over the population.
    affected_in_context : int
        Affected entities with positive weight.
    passed_in_context : bool or None
        For pass/fail metrics: whether no affected entity has positive weight.
    top_affected : list of (str, float)
        The highest-weighted affected entities -- the defects that matter
        most in this context.
    detail : dict
    """

    metric_id: str
    raw_score: Any
    normalizable: bool
    scope: str
    population: int = 0
    uniform_value: Optional[float] = None
    weighted_value: Optional[float] = None
    weighted_score: Any = None
    effective_support: float = 0.0
    affected_in_context: int = 0
    passed_in_context: Optional[bool] = None
    top_affected: List[Any] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def unweighted_score(self):
        """
        The value without context, in the same form as ``weighted_score``.

        For entity metrics this is the uniform rate (or ``1 - rate`` for
        proportion metrics), for OQuaRE the metric itself, and for metrics
        that cannot be weighted the raw score.
        """
        if not self.normalizable or self.uniform_value is None:
            return self.raw_score
        if self.detail.get("proportion"):
            return 1.0 - self.uniform_value
        return self.uniform_value

    @property
    def display_weighted(self):
        """
        The value to show in a weighted column.

        Ontology-level metrics concern the document, so a defect there
        affects every question equally and the weighted value is the raw
        score.  Metrics that did not run have no value.
        """
        if self.normalizable:
            return self.weighted_score
        if self.scope == "ontology":
            return self.raw_score
        return None

    @property
    def lift(self):
        """``weighted_value / uniform_value``: >1 means worse in context."""
        if not self.uniform_value or self.weighted_value is None:
            return None
        return self.weighted_value / self.uniform_value


def _effective_support(ws):
    s1 = sum(ws)
    s2 = sum(w * w for w in ws)
    return (s1 * s1 / s2) if s2 else 0.0


def _affected_entities(result):
    """IRIs in ``result.affected``; pair entries ``"A | B"`` are split."""
    out = set()
    for a in result.affected or []:
        s = str(a)
        if s.startswith("<"):
            continue
        for part in s.split(" | "):
            part = part.strip()
            if part:
                out.add(URIRef(part))
    return out


def _population(universe, kind, own_only):
    pop = {
        "class": universe.classes,
        "property": universe.properties,
        "term": universe.terms,
        "entity": universe.entities,
    }[kind]
    if own_only:
        pop = {e for e in pop if universe.is_own(e)}
    return set(pop)


def _infer_kind(universe, affected):
    if not affected:
        return None
    if affected <= universe.classes:
        return "class"
    if affected <= universe.properties:
        return "property"
    if affected & universe.entities:
        return "term" if affected & universe.terms else "entity"
    return None


def _normalize_entity_metric(result, descriptor, ctx):
    universe = ctx.universe
    affected = _affected_entities(result)
    kind, own_only = METRIC_SCOPE.get(
        result.metric_id, (_infer_kind(universe, affected), False)
    )
    if kind is None or result.metric_id in _NOT_ENTITY_LEVEL:
        return None
    # The metric may flag entities outside the nominal population (e.g.
    # P34's untyped classes); including them keeps every rate within [0, 1].
    population = _population(universe, kind, own_only) | affected

    w = {e: ctx.weights.get(e, 0.0) for e in population}
    total = sum(w.values())
    affected_mass = sum(w[e] for e in affected)
    uniform = len(affected) / len(population) if population else 0.0
    rate = affected_mass / total if total else None

    proportion = descriptor is not None and descriptor.scale == Scale.PROPORTION
    if rate is None:
        score = None
    elif proportion:
        score = 1.0 - rate
    else:
        score = rate

    in_ctx = sorted(((str(e), w[e]) for e in affected if w[e] > 0),
                    key=lambda kv: -kv[1])
    return NormalizedMetric(
        metric_id=result.metric_id,
        raw_score=result.score,
        normalizable=True,
        scope=kind + (" (own namespace)" if own_only else ""),
        population=len(population),
        uniform_value=uniform,
        weighted_value=rate,
        weighted_score=score,
        effective_support=_effective_support(list(w.values())),
        affected_in_context=len(in_ctx),
        passed_in_context=(len(in_ctx) == 0) if result.passed is not None
        else None,
        top_affected=in_ctx[:10],
        detail={"affected_mass": affected_mass, "population_mass": total,
                "affected": len(affected), "proportion": proportion},
    )


# --- OQuaRE ----------------------------------------------------------------

def _oquare_terms(prim):
    """
    Per-entity decomposition of each decomposable OQuaRE metric.

    Returns a mapping from abbreviation to ``(population, value_fn)``; the
    metric equals the unweighted mean of ``value_fn`` over ``population``.
    """
    g = prim.g
    props_of = defaultdict(set)
    domain_count = defaultdict(int)
    for p in prim.properties:
        for d in g.objects(p, RDFS.domain):
            if isinstance(d, URIRef):
                props_of[d].add(p)
                domain_count[d] += 1
    annotation_count = {}
    from .oquare_metrics import _ANNOTATION_PREDICATES
    for c in prim.classes:
        annotation_count[c] = sum(
            1 for p in _ANNOTATION_PREDICATES for _ in g.objects(c, p)
        )
    direct_instances = defaultdict(int)
    for s, o in g.subject_objects(RDF.type):
        if isinstance(s, URIRef) and o in prim.classes:
            direct_instances[o] += 1

    classes = prim.classes
    leaves = prim.leaves
    non_leaves = {c for c in classes if prim.children.get(c)}
    tangled = {c for c in classes if len(prim.parents.get(c, ())) > 1}
    n_parents = lambda c: len(prim.parents.get(c, ()))       # noqa: E731
    n_children = lambda c: len(prim.children.get(c, ()))     # noqa: E731
    n_anc = lambda c: len(prim.ancestors(c))                 # noqa: E731

    return {
        "ANOnto": (classes, lambda c: annotation_count[c]),
        "AROnto": (prim.properties,
                   lambda p: 1.0 if p in prim.properties_with_domain else 0.0),
        "CBOnto": (classes, n_parents),
        "CROnto": (classes, lambda c: direct_instances[c]),
        "INROnto": (classes, n_parents),
        "LCOMOnto": (leaves, prim.depth),
        "NACOnto": (leaves, n_anc),
        "NOCOnto": (non_leaves, n_children),
        "NOMOnto": (classes, lambda c: domain_count[c]),
        "POnto": (classes, n_anc),
        "RFCOnto": (classes, lambda c: len(props_of[c]) + n_children(c)),
        "TMOnto": (classes, lambda c: 1.0 if c in tangled else 0.0),
        "TMOnto2": (tangled, n_anc),
        "WMCOnto": (classes, lambda c: len(props_of[c]) + n_parents(c)
                    + n_children(c)),
        "WMCOnto2": (leaves, prim.depth),
    }


def _normalize_oquare(result, ctx, prim, terms):
    from .oquare_metrics import scale_static
    abbrev = (result.detail or {}).get("abbreviation") or \
        result.metric_id.replace("oquare", "")

    def weight(e):
        return ctx.weights.get(e, 0.0)

    if abbrev == "DITOnto":
        support = [c for c in prim.classes if weight(c) > 0]
        value = max((prim.depth(c) for c in support), default=None)
        ws = [weight(c) for c in prim.classes]
        uniform = max((prim.depth(c) for c in prim.classes), default=0)
        note = "maximum depth over classes with positive weight"
        population = prim.classes
    elif abbrev == "PROnto":
        wc = sum(weight(c) for c in prim.classes)
        wp = sum(weight(p) for p in prim.properties)
        value = wp / (wc + wp) if (wc + wp) else None
        n = len(prim.classes) + len(prim.properties)
        uniform = len(prim.properties) / n if n else 0.0
        ws = [weight(e) for e in prim.classes | prim.properties]
        note = "weighted property mass over weighted element mass"
        population = prim.classes | prim.properties
    elif abbrev in terms:
        population, fn = terms[abbrev]
        ws = [weight(e) for e in population]
        total = sum(ws)
        value = (sum(weight(e) * fn(e) for e in population) / total
                 if total else None)
        uniform = (sum(fn(e) for e in population) / len(population)
                   if population else 0.0)
        note = "weighted mean of the per-entity quantity"
    else:
        # RROnto divides property usages by subsumption edges; neither side
        # decomposes over a common entity population, so it is not weighted.
        return NormalizedMetric(
            metric_id=result.metric_id, raw_score=result.score,
            normalizable=False, scope="oquare",
            detail={"reason": f"{abbrev} does not decompose over entities"},
        )

    return NormalizedMetric(
        metric_id=result.metric_id,
        raw_score=result.score,
        normalizable=True,
        scope="oquare",
        population=len(population),
        uniform_value=uniform,
        weighted_value=value,
        weighted_score=None if value is None else round(value, 4),
        effective_support=_effective_support(ws),
        detail={
            "abbreviation": abbrev,
            "computation": note,
            "static_scale": (result.detail or {}).get("static_scale"),
            "weighted_static_scale": scale_static(abbrev, value),
        },
    )


def normalize_results(results, ctx):
    """
    Re-score metric results under a context.

    Version: 0.0.1

    Parameters
    ----------
    results : list of MetricResult
        As returned by
        :func:`~ontocheck.framework_metrics.run_framework_metrics` over the
        same ontology *ctx* was built from.
    ctx : ContextWeights

    Returns
    -------
    list of NormalizedMetric
        One per result, in the same order.
    """
    from .metric_registry import SourceFramework
    from .oquare_metrics import _OntologyPrimitives

    prim = terms = None
    out = []
    for r in results:
        d = METRIC_REGISTRY.get(r.metric_id)
        if r.status != "Success":
            out.append(NormalizedMetric(
                r.metric_id, r.score, False, "not run",
                detail={"reason": r.status},
            ))
            continue
        if d is not None and d.source_framework == SourceFramework.OQUARE:
            if prim is None:
                prim = _OntologyPrimitives(ctx.universe.g)
                terms = _oquare_terms(prim)
            out.append(_normalize_oquare(r, ctx, prim, terms))
            continue
        nm = _normalize_entity_metric(r, d, ctx)
        out.append(nm or NormalizedMetric(
            r.metric_id, r.score, False, "ontology",
            detail={"reason": "concerns the ontology document, not its terms"},
        ))
    return out


def contextual_assessment(ttl_file, queries=None, use_instances="auto",
                          frameworks=None, metrics=None, allow_network=False,
                          as_dataframe=True, **context_kwargs):
    """
    Run the framework metrics and normalise them under a context.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Ontology, optionally with instance data in the same file.
    queries : optional
        Competency questions in any form accepted by :func:`load_queries`.
    use_instances : bool or ``"auto"``, optional
    frameworks, metrics : optional
        Metric selection, as for ``run_framework_metrics``.
    allow_network : bool, optional
        Default ``False``: network tests are ontology-level and cannot be
        normalised, so they are skipped unless asked for.
    as_dataframe : bool, optional
        Return a pandas DataFrame (default) instead of a list.
    **context_kwargs
        Passed to :func:`build_context`.

    Returns
    -------
    (pandas.DataFrame or list of NormalizedMetric, ContextWeights)

    Examples
    --------
    >>> df, ctx = contextual_assessment(                        # doctest: +SKIP
    ...     "XRD.ttl", queries="XRD.json", frameworks=["OOPS!"])
    >>> df[df.normalizable].sort_values("lift", ascending=False)  # doctest: +SKIP
    """
    from .framework_metrics import run_framework_metrics

    ctx = build_context(ttl_file, queries, use_instances, **context_kwargs)
    results = run_framework_metrics(
        str(ttl_file), frameworks=frameworks, metrics=metrics,
        allow_network=allow_network,
        has_abox=bool(ctx.universe.individuals),
    )
    normalized = normalize_results(results, ctx)
    if not as_dataframe:
        return normalized, ctx
    return to_dataframe(normalized), ctx


def to_dataframe(normalized):
    """Tabulate normalised metrics, one row per metric."""
    import pandas as pd
    rows = [{
        "metric_id": n.metric_id,
        "scope": n.scope,
        "normalizable": n.normalizable,
        "raw_score": n.raw_score,
        "unweighted": n.unweighted_score,
        "weighted": n.display_weighted,
        "lift": n.lift,
        "population": n.population,
        "effective_support": round(n.effective_support, 2),
        "affected_in_context": n.affected_in_context,
        "passed_in_context": n.passed_in_context,
        "top_affected": ", ".join(
            _local_name(e) for e, _ in n.top_affected[:3]
        ),
    } for n in normalized]
    return pd.DataFrame(rows).set_index("metric_id")
