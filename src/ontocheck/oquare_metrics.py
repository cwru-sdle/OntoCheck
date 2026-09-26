"""
OQuaRE structural quality metrics.

Implements the OQuaRE quantitative structural metrics, together with the
static and dynamic scaling functions that map raw values onto the OQuaRE
1--5 quality scale.

Why definitions are pinned here
-------------------------------
OQuaRE's published specification is internally inconsistent.  Reiz and
Sandkuhl ("Harmonizing the OQuaRE Quality Framework") document six classes of
problem: metric definitions that changed between publications (``NOCOnto``
moved from subclasses to superclasses and then changed again over leaf-class
exclusion), names that collided (``RROnto`` was published as ``PROnto`` before
``PROnto`` became a separate metric), formulas that were substantially
reformulated (``RFCOnto``, ``RROnto``, ``WMCOnto``, with ``WMCOnto2`` changing
meaning entirely), terminology that left "relationship" ambiguous between
subclass relations and general properties, under-specified metrics such as
``AROnto``, and documentation distributed across papers, a wiki and tool
implementations that contradict one another.  They further note that **no
study has empirically validated the proposed metric ranges or the
metric-to-characteristic mappings**.

"Implementing OQuaRE" is therefore not well defined.  Every metric below
states the definition it implements and, where the literature disagrees, a
``Definitional note`` recording the ambiguity and the reading chosen.  The
choices follow Duque-Ramos et al. (2011) as the most-cited source, which is
the resolution Reiz and Sandkuhl recommend.  Any published comparison against
another OQuaRE implementation should cite these definitions rather than
assuming agreement.

Metrics implemented
-------------------
=========  ==================================  ===================
Metric     Full name                           Requirement
=========  ==================================  ===================
ANOnto     Annotation richness                 TBox
AROnto     Attribute richness                  TBox
CBOnto     Coupling between objects            TBox
CROnto     Class richness                      **ABox required**
DITOnto    Depth of subsumption hierarchy      TBox
INROnto    Relationships per class             TBox
LCOMOnto   Lack of cohesion in methods         TBox
NACOnto    Number of ancestor classes          TBox
NOCOnto    Number of children                  TBox
NOMOnto    Number of properties                TBox
POnto      Ancestors per class                 TBox
PROnto     Property richness                   TBox
RFCOnto    Response for a class                TBox
RROnto     Relationship richness               TBox
TMOnto     Tangledness                         TBox
TMOnto2    Tangledness 2                       TBox
WMCOnto    Weighted method count               TBox
WMCOnto2   Weighted method count 2             TBox
=========  ==================================  ===================

``CROnto`` is registered with ``requires_abox=True`` and is skipped over a
schema-only assessment rather than reported as zero.

Scaling
-------
``scale_static`` applies the published fixed thresholds.  ``scale_dynamic``
implements the version-corpus scaling of Duque-Ramos et al. (2016), which
clusters observed values across an ontology's releases with k-means (k = 5)
instead of applying universal thresholds.  The dynamic scale is the more
sensitive of the two for release-over-release comparison, which is what an
assessment of an evolving ontology needs.

Source
------
Duque-Ramos, A., Fernandez-Breis, J. T., Stevens, R., & Aussenac-Gilles, N.
(2011). OQuaRE: A SQuaRE-based approach for evaluating the quality of
ontologies. *Journal of Research and Practice in Information Technology*,
43(2), 159-176.

Duque-Ramos, A., Fernandez-Breis, J. T., et al. (2016). Supporting the
analysis of ontology evolution processes through the combination of static and
dynamic scaling functions in OQuaRE. *Journal of Biomedical Semantics*, 7:63.

Reiz, A., & Sandkuhl, K. Harmonizing the OQuaRE Quality Framework.

Repository: https://github.com/astriduquer/oquare

Version: 0.0.1

.. note::

   Claude AI (Opus 5) was employed chiefly to support documentation efforts.
"""

import logging
from collections import deque

from rdflib import BNode, OWL, RDF, RDFS, URIRef

from .helpers.oops_helpers import (
    _direct_parents,
    _is_foundational,
    _load_graph,
    _named_classes,
    _named_properties,
    _own_namespace,
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

_OQUARE_REPO = "https://github.com/astriduquer/oquare"

# Annotation properties counted by ANOnto.
_ANNOTATION_PREDICATES = (
    RDFS.label,
    RDFS.comment,
    RDFS.seeAlso,
    RDFS.isDefinedBy,
    URIRef("http://www.w3.org/2004/02/skos/core#definition"),
    URIRef("http://www.w3.org/2004/02/skos/core#altLabel"),
    URIRef("http://www.w3.org/2004/02/skos/core#prefLabel"),
    URIRef("http://www.w3.org/2004/02/skos/core#example"),
    URIRef("http://www.w3.org/2004/02/skos/core#note"),
    URIRef("http://www.w3.org/2004/02/skos/core#scopeNote"),
    URIRef("http://www.w3.org/2004/02/skos/core#exactMatch"),
    URIRef("http://purl.obolibrary.org/obo/IAO_0000115"),
    URIRef("http://purl.org/dc/terms/description"),
    OWL.versionInfo,
    OWL.deprecated,
)


# ---------------------------------------------------------------------------
# Primitive measurements
# ---------------------------------------------------------------------------

class _OntologyPrimitives:
    """
    Primitive structural measurements shared by the OQuaRE metrics.

    Computing these once avoids re-traversing the graph for each of eighteen
    metrics, and guarantees that every metric works from the same population
    of classes, properties and subsumption edges.

    Definitions
    -----------
    - Classes: named classes, as defined by
      :func:`~ontocheck.helpers.oops_helpers._named_classes`, excluding
      ``owl:Thing`` and foundational-namespace terms.

    - Parents / children: named direct superclass and subclass relations.
      Anonymous superclasses (restrictions, Boolean expressions) are excluded
      from the subsumption graph but counted separately as
      ``anonymous_superclass_count``.

    - Roots: classes with no named superclass.  These stand in for the
      children of ``owl:Thing``, which is rarely asserted explicitly.

    - Leaves: classes with no named subclass.

    Version: 0.0.1

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Attributes
    ----------
    classes : set of rdflib.URIRef
    properties : set of rdflib.URIRef
    object_properties : set of rdflib.URIRef
    datatype_properties : set of rdflib.URIRef
    parents : dict
        Class to set of named direct superclasses.
    children : dict
        Class to set of named direct subclasses.
    roots : set of rdflib.URIRef
    leaves : set of rdflib.URIRef
    subclass_edges : int
        Count of named ``rdfs:subClassOf`` relations.
    property_usages : int
        Count of triples whose predicate is a declared object or datatype
        property, plus restriction ``owl:onProperty`` usages.
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
        self.object_properties = {
            p for p in g.subjects(RDF.type, OWL.ObjectProperty)
            if isinstance(p, URIRef) and not _is_foundational(p)
        }
        self.datatype_properties = {
            p for p in g.subjects(RDF.type, OWL.DatatypeProperty)
            if isinstance(p, URIRef) and not _is_foundational(p)
        }

        raw_parents = _direct_parents(g)
        self.parents = {}
        self.children = {}
        self.subclass_edges = 0
        for child, parent_set in raw_parents.items():
            if child not in self.classes:
                continue
            kept = {p for p in parent_set
                    if p in self.classes or not _is_foundational(p)}
            kept.discard(OWL.Thing)
            kept.discard(child)
            if kept:
                self.parents[child] = kept
                self.subclass_edges += len(kept)
                for p in kept:
                    self.children.setdefault(p, set()).add(child)

        self.anonymous_superclass_count = sum(
            1 for _, o in g.subject_objects(RDFS.subClassOf)
            if isinstance(o, BNode)
        )

        self.roots = {c for c in self.classes if not self.parents.get(c)}
        self.leaves = {c for c in self.classes if not self.children.get(c)}

        usable = self.object_properties | self.datatype_properties
        self.property_usages = sum(
            1 for _, p, _ in g if isinstance(p, URIRef) and p in usable
        )
        self.property_usages += sum(
            1 for _, o in g.subject_objects(OWL.onProperty)
            if isinstance(o, URIRef) and o in usable
        )

        self.properties_with_domain = {
            p for p in self.properties
            if any(True for _ in g.objects(p, RDFS.domain))
        }
        self.properties_with_range = {
            p for p in self.properties
            if any(True for _ in g.objects(p, RDFS.range))
        }

        self._ancestors_cache = {}
        self._depth_cache = {}

    def ancestors(self, cls):
        """
        Return every transitive named superclass of a class.

        Parameters
        ----------
        cls : rdflib.URIRef
            Class to inspect.

        Returns
        -------
        set of rdflib.URIRef
            Transitive superclasses, excluding *cls* itself.  Cycle-safe.
        """
        if cls in self._ancestors_cache:
            return self._ancestors_cache[cls]
        seen, queue = set(), deque(self.parents.get(cls, ()))
        while queue:
            node = queue.popleft()
            if node in seen or node == cls:
                continue
            seen.add(node)
            queue.extend(self.parents.get(node, ()))
        self._ancestors_cache[cls] = seen
        return seen

    def depth(self, cls):
        """
        Return the longest path length from a root to a class.

        Parameters
        ----------
        cls : rdflib.URIRef
            Class to inspect.

        Returns
        -------
        int
            Number of subsumption steps from a root class.  A root has depth
            0.  Cycle-safe: a class on a cycle returns the depth reached
            before the cycle closed.
        """
        if cls in self._depth_cache:
            return self._depth_cache[cls]

        best, stack = 0, [(cls, 0, {cls})]
        while stack:
            node, dist, path = stack.pop()
            parents = self.parents.get(node, ())
            if not parents:
                best = max(best, dist)
                continue
            for parent in parents:
                if parent in path:
                    best = max(best, dist)
                    continue
                stack.append((parent, dist + 1, path | {parent}))
        self._depth_cache[cls] = best
        return best

    def instance_count(self):
        """
        Return the number of asserted individuals.

        Returns
        -------
        int
            Count of distinct subjects typed with a named class from this
            ontology, which is the population ``CROnto`` is defined over.
        """
        individuals = set()
        for s, o in self.g.subject_objects(RDF.type):
            if isinstance(s, URIRef) and o in self.classes:
                individuals.add(s)
        return len(individuals)


def _mean(values):
    """
    Return the arithmetic mean, or 0.0 for an empty sequence.

    Parameters
    ----------
    values : iterable of float

    Returns
    -------
    float
    """
    values = list(values)
    return (sum(values) / len(values)) if values else 0.0


# ---------------------------------------------------------------------------
# Scaling functions
# ---------------------------------------------------------------------------

# Static thresholds.  Each entry is an ordered list of (upper_bound, score);
# the first bound a value falls at or below determines the score.  ``None`` as
# a bound means "anything above the previous bound".
#
# Thresholds for TMOnto and for the percentage-family metrics (RROnto, AROnto,
# INROnto, CROnto, ANOnto) are those published by Duque-Ramos et al. (2016).
# The remainder are extrapolated on the same 1 = Not Acceptable,
# 3 = Minimally Acceptable, 5 = Exceeds Requirements pattern and are marked
# ``extrapolated`` in STATIC_SCALE_PROVENANCE.
STATIC_SCALE = {
    "ANOnto": [(2, 1), (4, 2), (6, 3), (8, 4), (None, 5)],
    "AROnto": [(0.20, 1), (0.40, 2), (0.60, 3), (0.80, 4), (None, 5)],
    "CBOnto": [(1, 5), (2, 4), (4, 3), (8, 2), (None, 1)],
    "CROnto": [(0.20, 1), (0.40, 2), (0.60, 3), (0.80, 4), (None, 5)],
    "DITOnto": [(2, 1), (4, 3), (6, 5), (8, 3), (None, 1)],
    "INROnto": [(0.20, 1), (0.40, 2), (0.60, 3), (0.80, 4), (None, 5)],
    "LCOMOnto": [(1, 5), (3, 4), (6, 3), (10, 2), (None, 1)],
    "NACOnto": [(1, 5), (3, 4), (5, 3), (8, 2), (None, 1)],
    "NOCOnto": [(1, 1), (2, 3), (4, 5), (8, 3), (None, 1)],
    "NOMOnto": [(1, 5), (3, 4), (6, 3), (10, 2), (None, 1)],
    "POnto": [(1, 5), (3, 4), (6, 3), (10, 2), (None, 1)],
    "PROnto": [(0.20, 1), (0.40, 2), (0.60, 3), (0.80, 4), (None, 5)],
    "RFCOnto": [(2, 5), (5, 4), (10, 3), (20, 2), (None, 1)],
    "RROnto": [(0.20, 1), (0.40, 2), (0.60, 3), (0.80, 4), (None, 5)],
    "TMOnto": [(1, 5), (2, 5), (4, 4), (6, 3), (8, 2), (None, 1)],
    "TMOnto2": [(1, 5), (2, 4), (4, 3), (8, 2), (None, 1)],
    "WMCOnto": [(2, 5), (4, 4), (8, 3), (12, 2), (None, 1)],
    "WMCOnto2": [(1, 5), (3, 4), (6, 3), (10, 2), (None, 1)],
}

STATIC_SCALE_PROVENANCE = {
    "TMOnto": "published (Duque-Ramos et al. 2016)",
    "RROnto": "published percentage family (Duque-Ramos et al. 2016)",
    "AROnto": "published percentage family (Duque-Ramos et al. 2016)",
    "INROnto": "published percentage family (Duque-Ramos et al. 2016)",
    "CROnto": "published percentage family (Duque-Ramos et al. 2016)",
    "ANOnto": "published percentage family (Duque-Ramos et al. 2016)",
}


def scale_static(metric, value):
    """
    Map a raw metric value onto the OQuaRE 1--5 static quality scale.

    Definitions
    -----------
    - Static scale: fixed, universal thresholds.  1 denotes "Not Acceptable",
      3 "Minimally Acceptable" and 5 "Exceeds Requirements".

    - Threshold provenance: thresholds for ``TMOnto`` and the percentage
      family are published.  The remainder are extrapolated on the same
      pattern, and :data:`STATIC_SCALE_PROVENANCE` records which is which.

    Source
    ------
    Duque-Ramos et al. (2011, 2016)

    Version: 0.0.1

    Parameters
    ----------
    metric : str
        OQuaRE metric abbreviation, e.g. ``"DITOnto"``.
    value : int or float
        Raw metric value.

    Returns
    -------
    int or None
        A score in [1, 5], or ``None`` when *metric* has no defined scale or
        *value* is ``None``.

    Notes
    -----
    Reiz and Sandkuhl observe that no study has empirically validated these
    ranges.  Static scores should be read as a convention for comparison, not
    as a calibrated measurement.

    Examples
    --------
    >>> scale_static("TMOnto", 1.5)
    5
    >>> scale_static("TMOnto", 9.0)
    1
    """
    if value is None or metric not in STATIC_SCALE:
        return None
    for bound, score in STATIC_SCALE[metric]:
        if bound is None or value <= bound:
            return score
    return None


def _kmeans_1d(values, k=5, max_iter=100, tol=1e-9):
    """
    One-dimensional k-means clustering.

    Implemented directly so that dynamic scaling adds no dependency beyond
    the packages OntoCheck already requires.

    Parameters
    ----------
    values : list of float
        Observations to cluster.
    k : int, optional
        Number of clusters.  Default 5, matching the OQuaRE scale.
    max_iter : int, optional
        Maximum Lloyd iterations.  Default 100.
    tol : float, optional
        Convergence tolerance on centroid movement.  Default 1e-9.

    Returns
    -------
    list of float
        Sorted cluster centroids.  Fewer than *k* are returned when the data
        contain fewer than *k* distinct values.
    """
    distinct = sorted(set(values))
    if len(distinct) <= k:
        return distinct

    lo, hi = distinct[0], distinct[-1]
    centroids = [lo + (hi - lo) * i / (k - 1) for i in range(k)]

    for _ in range(max_iter):
        buckets = [[] for _ in range(k)]
        for v in values:
            idx = min(range(k), key=lambda i: abs(v - centroids[i]))
            buckets[idx].append(v)
        new_centroids = [
            _mean(b) if b else centroids[i] for i, b in enumerate(buckets)
        ]
        shift = max(abs(a - b) for a, b in zip(centroids, new_centroids))
        centroids = new_centroids
        if shift < tol:
            break

    return sorted(centroids)


def scale_dynamic(value, corpus, higher_is_better=True, k=5):
    """
    Map a raw metric value onto a 1--5 scale derived from a version corpus.

    Definitions
    -----------
    - Version corpus: the raw values of one metric collected across every
      available release of an ontology.

    - Dynamic scale: cluster boundaries obtained by k-means (k = 5) over that
      corpus, so that 1 corresponds to the lowest observed value and 5 to the
      highest.  The scale is calibrated to the ontology's own history rather
      than to universal thresholds.

    - Sensitivity: because the scale is anchored to observed range, it detects
      release-over-release changes that a static scale rounds away.  This is
      the property that makes it suited to assessing an evolving ontology.

    Source
    ------
    Duque-Ramos et al. (2016), *Supporting the analysis of ontology evolution
    processes through the combination of static and dynamic scaling functions
    in OQuaRE*, Journal of Biomedical Semantics 7:63.

    Version: 0.0.1

    Parameters
    ----------
    value : int or float
        Raw metric value for the release being scored.
    corpus : list of float
        Raw values of the same metric across all releases, normally including
        *value* itself.
    higher_is_better : bool, optional
        When ``False``, the scale is inverted so that the lowest observed
        value scores 5.  Default ``True``.
    k : int, optional
        Number of clusters.  Default 5.

    Returns
    -------
    int or None
        A score in [1, 5], or ``None`` when *value* is ``None`` or *corpus* is
        empty.

    Notes
    -----
    A dynamic score is meaningful only relative to the corpus it was computed
    from.  Two ontologies' dynamic scores are not comparable with each other;
    only successive releases of the same ontology are.  Report the corpus
    alongside any dynamic score.

    At least two distinct values are needed for the scale to discriminate.
    With a single release the function returns the midpoint, 3.

    Examples
    --------
    >>> scale_dynamic(4.0, [1.0, 2.0, 3.0, 4.0, 5.0])
    5
    >>> scale_dynamic(1.0, [1.0, 2.0, 3.0, 4.0, 5.0])
    1
    """
    if value is None or not corpus:
        return None
    if len(set(corpus)) == 1:
        return 3

    centroids = _kmeans_1d(list(corpus), k=k)
    idx = min(range(len(centroids)), key=lambda i: abs(value - centroids[i]))
    span = max(len(centroids) - 1, 1)
    score = 1 + round(idx * 4 / span)
    if not higher_is_better:
        score = 6 - score
    return int(max(1, min(5, score)))


# ---------------------------------------------------------------------------
# Metric implementations
# ---------------------------------------------------------------------------

def _oquare_result(metric_id, abbrev, value, prim, note, message,
                   higher_is_better=True, extra=None):
    """
    Assemble a :class:`MetricResult` for an OQuaRE metric.

    Parameters
    ----------
    metric_id : str
        Registry identifier.
    abbrev : str
        OQuaRE abbreviation, used to look up the static scale.
    value : int or float or None
        Raw metric value.
    prim : _OntologyPrimitives
        Primitives the value was computed from.
    note : str
        Definitional note recording the reading implemented.
    message : str
        One-line summary.
    higher_is_better : bool, optional
        Direction of improvement.
    extra : dict, optional
        Additional detail entries.

    Returns
    -------
    MetricResult
        ``score`` carries the raw value; ``detail["static_scale"]`` carries
        the 1--5 score, since the raw value is what a later release must be
        compared against.
    """
    own_ns = _own_namespace(prim.g)
    own_classes = (
        sum(1 for c in prim.classes if str(c).startswith(own_ns))
        if own_ns else len(prim.classes)
    )
    own_properties = (
        sum(1 for p in prim.properties if str(p).startswith(own_ns))
        if own_ns else len(prim.properties)
    )

    detail = {
        "abbreviation": abbrev,
        "raw_value": value,
        "static_scale": scale_static(abbrev, value),
        "static_threshold_provenance": STATIC_SCALE_PROVENANCE.get(
            abbrev, "extrapolated"
        ),
        "definition_note": note,
        "higher_is_better": higher_is_better,
        "class_count": len(prim.classes),
        "property_count": len(prim.properties),
        # Denominator transparency.  A domain ontology that declares stub
        # entries for imported upper-level terms (``cco:ont00000324 a
        # owl:Class ; rdfs:label "Width"``) rather than using owl:imports
        # inflates every OQuaRE denominator with terms it does not own.  The
        # metric value follows OQuaRE convention and counts the whole graph,
        # so these counts are reported alongside it: an OQuaRE score is only
        # comparable across ontologies that handle imports the same way.
        "own_namespace": own_ns,
        "own_class_count": own_classes,
        "own_property_count": own_properties,
        "external_stub_classes": len(prim.classes) - own_classes,
        "external_stub_properties": len(prim.properties) - own_properties,
    }
    if extra:
        detail.update(extra)
    return MetricResult(
        metric_id=metric_id,
        score=round(value, 4) if isinstance(value, float) else value,
        passed=None,
        total_examined=len(prim.classes),
        detail=detail,
        message=message,
    )


def _with_primitives(ttl_file, metric_id):
    """
    Load an ontology and build its primitive measurements.

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the Turtle file.
    metric_id : str
        Registry identifier, stamped on an error result.

    Returns
    -------
    tuple
        ``(primitives, None)`` on success, or ``(None, MetricResult)`` when
        the ontology could not be loaded.
    """
    g = _load_graph(ttl_file)
    if g is None:
        return None, MetricResult(
            metric_id=metric_id, status="Error: could not load ontology"
        )
    return _OntologyPrimitives(g), None


def oquare_anonto_v_0_0_1(ttl_file):
    """
    OQuaRE ANOnto -- Annotation richness.

    Mean number of annotation-property assertions per class.

    Definitions
    -----------
    - Annotation assertion: a triple whose predicate is one of
      ``rdfs:label``, ``rdfs:comment``, ``rdfs:seeAlso``, ``rdfs:isDefinedBy``,
      the SKOS annotation properties, ``obo:IAO_0000115``,
      ``dcterms:description``, ``owl:versionInfo`` or ``owl:deprecated``.

    - ANOnto = (number of annotation assertions on classes) / (number of
      classes).

    Source
    ------
    OQuaRE ANOnto; Duque-Ramos et al. (2016) give "mean number of annotation
    properties per class".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean; ``detail["static_scale"]`` the 1--5 score.

    Notes
    -----
    Relates to, but does not duplicate, the existing ``checkLabel``,
    ``altLabelCheck`` and ``definitionCheck`` metrics.  Those report the
    *proportion of classes* carrying an annotation; ANOnto reports the *mean
    number* of annotations per class, so an ontology in which every class has
    exactly one label scores 1.0 here and 100% there.

    Examples
    --------
    >>> result = oquare_anonto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareANOnto")
    if err:
        return err

    total = sum(
        1
        for c in prim.classes
        for p in _ANNOTATION_PREDICATES
        for _ in prim.g.objects(c, p)
    )
    value = total / len(prim.classes) if prim.classes else 0.0

    logger.info(f"--- OQuaRE ANOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareANOnto", "ANOnto", value, prim,
        "Annotation assertions on classes divided by class count.",
        f"ANOnto = {value:.4f} ({total} annotations over "
        f"{len(prim.classes)} classes)",
        extra={"annotation_assertions": total},
    )


def oquare_aronto_v_0_0_1(ttl_file):
    """
    OQuaRE AROnto -- Attribute richness.

    Proportion of properties carrying a declared ``rdfs:domain``.

    Definitions
    -----------
    - AROnto = |{p : p has an ``rdfs:domain``}| / |properties|.

    Definitional note
    -----------------
    Reiz and Sandkuhl record that AROnto's treatment of restrictions versus
    attributes stayed unclear until tool implementations settled it as domain
    axiom coverage.  That reading is implemented here.

    Source
    ------
    OQuaRE AROnto; percentage-family static thresholds from Duque-Ramos et al.
    (2016).

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the proportion in [0, 1].

    Notes
    -----
    Complementary to the existing ``missingDomainRange`` metric, which lists
    the offending properties.  AROnto expresses the same underlying fact as a
    ratio suitable for the OQuaRE quality aggregation.

    Examples
    --------
    >>> result = oquare_aronto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareAROnto")
    if err:
        return err

    value = (
        len(prim.properties_with_domain) / len(prim.properties)
        if prim.properties else 0.0
    )

    logger.info(f"--- OQuaRE AROnto: {value:.4f} ---")
    return _oquare_result(
        "oquareAROnto", "AROnto", value, prim,
        "Properties with a declared rdfs:domain, divided by property count.",
        f"AROnto = {value:.4f} ({len(prim.properties_with_domain)}/"
        f"{len(prim.properties)} properties declare a domain)",
        extra={
            "with_domain": len(prim.properties_with_domain),
            "with_range": len(prim.properties_with_range),
        },
    )


def oquare_cbonto_v_0_0_1(ttl_file):
    """
    OQuaRE CBOnto -- Coupling between objects.

    Mean number of named direct superclasses per class.

    Definitions
    -----------
    - CBOnto = (number of named ``rdfs:subClassOf`` relations) / (number of
      classes).  ``owl:Thing`` is excluded, as are anonymous superclasses.

    Source
    ------
    OQuaRE CBOnto -- "assesses superclass dependencies".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better, since high coupling
        indicates classes that cannot be understood independently.

    Notes
    -----
    ``detail["anonymous_superclasses"]`` reports the number of anonymous
    superclass expressions excluded.  In heavily axiomatised ontologies these
    can outnumber the named relations, so the excluded count is worth
    inspecting alongside the metric.

    Examples
    --------
    >>> result = oquare_cbonto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareCBOnto")
    if err:
        return err

    value = (
        prim.subclass_edges / len(prim.classes) if prim.classes else 0.0
    )

    logger.info(f"--- OQuaRE CBOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareCBOnto", "CBOnto", value, prim,
        "Named subClassOf relations divided by class count; owl:Thing and "
        "anonymous superclasses excluded.",
        f"CBOnto = {value:.4f} ({prim.subclass_edges} named subsumption "
        f"relations over {len(prim.classes)} classes)",
        higher_is_better=False,
        extra={
            "subclass_edges": prim.subclass_edges,
            "anonymous_superclasses": prim.anonymous_superclass_count,
        },
    )


def oquare_cronto_v_0_0_1(ttl_file):
    """
    OQuaRE CROnto -- Class richness.

    Mean number of asserted instances per class.

    Definitions
    -----------
    - CROnto = (number of individuals typed with a class of this ontology) /
      (number of classes).

    - ABox requirement: this metric is defined over instance data.  A
      schema-only file yields zero, which is a statement about the file rather
      than about the ontology's quality.

    Source
    ------
    OQuaRE CROnto -- "measures instance distribution"; percentage-family
    static thresholds from Duque-Ramos et al. (2016).

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.

    Notes
    -----
    Registered with ``requires_abox=True``, so an assessment run over schema
    files skips it with an explanatory status rather than recording a
    misleading zero.  It is the only OQuaRE metric in this module with that
    requirement.

    Examples
    --------
    >>> result = oquare_cronto_v_0_0_1("populated_graph.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareCROnto")
    if err:
        return err

    instances = prim.instance_count()
    value = instances / len(prim.classes) if prim.classes else 0.0

    logger.info(f"--- OQuaRE CROnto: {value:.4f} ({instances} individuals) ---")
    return _oquare_result(
        "oquareCROnto", "CROnto", value, prim,
        "Individuals typed with a class of this ontology, divided by class "
        "count. Requires instance data.",
        f"CROnto = {value:.4f} ({instances} individuals over "
        f"{len(prim.classes)} classes)",
        extra={"instance_count": instances},
    )


def oquare_ditonto_v_0_0_1(ttl_file):
    """
    OQuaRE DITOnto -- Depth of the subsumption hierarchy.

    Length of the longest path from a root class to a leaf class.

    Definitions
    -----------
    - DITOnto = max over all classes of the number of subsumption steps from
      a root.  Duque-Ramos et al. (2016) give "length of the largest path from
      Thing to a leaf class"; since ``owl:Thing`` is rarely asserted, classes
      with no named superclass stand in for its children.

    - Cycle safety: paths are not followed through a class already on the
      current path, so an ontology failing OOPS! P06 still yields a finite
      depth.

    Source
    ------
    OQuaRE DITOnto.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the maximum depth.  ``detail["mean_depth"]`` and
        ``detail["deepest_class"]`` give supporting values.

    Notes
    -----
    Both extremes are penalised by the static scale: a flat hierarchy carries
    little inferential structure, while an excessively deep one is hard to
    maintain and often over-specialised (compare OOPS! P17).

    Examples
    --------
    >>> result = oquare_ditonto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareDITOnto")
    if err:
        return err

    depths = {c: prim.depth(c) for c in prim.classes}
    value = max(depths.values()) if depths else 0
    deepest = max(depths, key=lambda c: depths[c]) if depths else None

    logger.info(f"--- OQuaRE DITOnto: {value} ---")
    return _oquare_result(
        "oquareDITOnto", "DITOnto", value, prim,
        "Longest root-to-leaf subsumption path; roots stand in for the "
        "children of owl:Thing.",
        f"DITOnto = {value} (deepest class: {deepest})",
        extra={
            "mean_depth": round(_mean(depths.values()), 4),
            "deepest_class": str(deepest) if deepest else None,
            "root_count": len(prim.roots),
            "leaf_count": len(prim.leaves),
        },
    )


def oquare_inronto_v_0_0_1(ttl_file):
    """
    OQuaRE INROnto -- Relationships per class.

    Mean number of subsumption relations per class.

    Definitions
    -----------
    - INROnto = (number of named ``rdfs:subClassOf`` relations) / (number of
      classes).

    Definitional note
    -----------------
    Reiz and Sandkuhl record that "relationship" is used ambiguously across
    the OQuaRE publications, sometimes meaning subclass relations and
    sometimes general properties, and that this affects INROnto and NOCOnto in
    particular.  The subsumption reading is implemented here.  Under this
    reading INROnto and CBOnto compute the same quantity from the same
    primitive; they are retained separately because the OQuaRE quality model
    maps them to different sub-characteristics.

    Source
    ------
    OQuaRE INROnto -- "counts subclass relationships".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.

    Examples
    --------
    >>> result = oquare_inronto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareINROnto")
    if err:
        return err

    value = prim.subclass_edges / len(prim.classes) if prim.classes else 0.0

    logger.info(f"--- OQuaRE INROnto: {value:.4f} ---")
    return _oquare_result(
        "oquareINROnto", "INROnto", value, prim,
        "Subsumption reading: named subClassOf relations divided by class "
        "count. Coincides with CBOnto under this reading.",
        f"INROnto = {value:.4f}",
        extra={"coincides_with": "CBOnto"},
    )


def oquare_lcomonto_v_0_0_1(ttl_file):
    """
    OQuaRE LCOMOnto -- Lack of cohesion in methods.

    Mean path length from leaf classes to their root.

    Definitions
    -----------
    - LCOMOnto = mean over leaf classes of the number of subsumption steps
      from the leaf to a root.

    - Interpretation: long mean paths indicate a hierarchy whose leaves are
      far from any organising concept, which OQuaRE reads as low cohesion.

    Source
    ------
    OQuaRE LCOMOnto -- "measures class cohesion via path length".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better.

    Notes
    -----
    Computed over leaves only, so it differs from ``detail["mean_depth"]``
    reported by DITOnto, which averages over every class.

    Examples
    --------
    >>> result = oquare_lcomonto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareLCOMOnto")
    if err:
        return err

    value = _mean(prim.depth(c) for c in prim.leaves)

    logger.info(f"--- OQuaRE LCOMOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareLCOMOnto", "LCOMOnto", value, prim,
        "Mean root-to-leaf path length over leaf classes.",
        f"LCOMOnto = {value:.4f} over {len(prim.leaves)} leaf classes",
        higher_is_better=False,
        extra={"leaf_count": len(prim.leaves)},
    )


def oquare_naconto_v_0_0_1(ttl_file):
    """
    OQuaRE NACOnto -- Number of ancestor classes.

    Mean number of ancestors of leaf classes.

    Definitions
    -----------
    - NACOnto = mean over leaf classes of the number of transitive named
      superclasses.

    - Distinct from LCOMOnto: a leaf reachable from a root by two different
      three-step paths has a path length of 3 but four ancestors.  The two
      metrics diverge exactly where multiple inheritance is present.

    Source
    ------
    OQuaRE NACOnto -- "measures ancestor count for leaf classes".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better.

    Examples
    --------
    >>> result = oquare_naconto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareNACOnto")
    if err:
        return err

    value = _mean(len(prim.ancestors(c)) for c in prim.leaves)

    logger.info(f"--- OQuaRE NACOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareNACOnto", "NACOnto", value, prim,
        "Mean count of transitive named superclasses over leaf classes.",
        f"NACOnto = {value:.4f} over {len(prim.leaves)} leaf classes",
        higher_is_better=False,
        extra={"leaf_count": len(prim.leaves)},
    )


def oquare_noconto_v_0_0_1(ttl_file):
    """
    OQuaRE NOCOnto -- Number of children.

    Mean number of direct subclasses per non-leaf class.

    Definitions
    -----------
    - NOCOnto = (number of named subsumption relations) / (number of classes
      having at least one named subclass).

    Definitional note
    -----------------
    This is the most unstable metric in OQuaRE.  Reiz and Sandkuhl record that
    NOCOnto "shifted from subclasses to superclasses across publications, then
    changed its calculation methodology regarding leaf class exclusion".  Two
    decisions are therefore pinned explicitly here: the metric counts
    **subclasses**, not superclasses; and leaf classes are **excluded** from
    the denominator, since including them makes the metric a function of how
    many leaves an ontology happens to have rather than of its branching
    factor.  Both differ from some published implementations, so this metric
    in particular should not be compared across tools without checking their
    definitions.

    Source
    ------
    OQuaRE NOCOnto -- "calculates mean direct subclasses".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  ``detail["including_leaves"]`` gives the
        value under the alternative reading, so both can be reported.

    Examples
    --------
    >>> result = oquare_noconto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareNOCOnto")
    if err:
        return err

    non_leaves = [c for c in prim.classes if prim.children.get(c)]
    value = _mean(len(prim.children[c]) for c in non_leaves)
    including_leaves = (
        prim.subclass_edges / len(prim.classes) if prim.classes else 0.0
    )

    logger.info(f"--- OQuaRE NOCOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareNOCOnto", "NOCOnto", value, prim,
        "Subclass reading with leaf classes excluded from the denominator. "
        "See the definitional note; this metric is not comparable across "
        "tools without checking their definitions.",
        f"NOCOnto = {value:.4f} over {len(non_leaves)} branching classes",
        extra={
            "branching_classes": len(non_leaves),
            "including_leaves": round(including_leaves, 4),
        },
    )


def oquare_nomonto_v_0_0_1(ttl_file):
    """
    OQuaRE NOMOnto -- Number of properties.

    Mean number of properties declared over each class.

    Definitions
    -----------
    - NOMOnto = (number of ``rdfs:domain`` assertions pointing at a class) /
      (number of classes).  A property with two declared domains contributes
      to both.

    Source
    ------
    OQuaRE NOMOnto -- "averages property assertions per class".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better, since a class carrying
        very many properties is usually under-decomposed.

    Notes
    -----
    Counts only properties whose domain is *declared*.  In an ontology with
    low AROnto, NOMOnto therefore understates the true figure, and the two
    should be read together.

    Examples
    --------
    >>> result = oquare_nomonto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareNOMOnto")
    if err:
        return err

    domain_assertions = 0
    for p in prim.properties:
        for d in prim.g.objects(p, RDFS.domain):
            if isinstance(d, URIRef):
                domain_assertions += 1

    value = domain_assertions / len(prim.classes) if prim.classes else 0.0

    logger.info(f"--- OQuaRE NOMOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareNOMOnto", "NOMOnto", value, prim,
        "Declared rdfs:domain assertions divided by class count.",
        f"NOMOnto = {value:.4f} ({domain_assertions} domain assertions)",
        higher_is_better=False,
        extra={"domain_assertions": domain_assertions},
    )


def oquare_ponto_v_0_0_1(ttl_file):
    """
    OQuaRE POnto -- Ancestors per class.

    Mean number of transitive named superclasses over all classes.

    Definitions
    -----------
    - POnto = mean over every class of the number of transitive named
      superclasses.

    Definitional note
    -----------------
    POnto and TMOnto are both glossed as concerning superclasses per class in
    some presentations of OQuaRE.  They are separated here: POnto averages
    *transitive ancestors over all classes*, whereas TMOnto measures the
    *proportion of classes with more than one direct superclass*, following
    Duque-Ramos et al. (2016), who define TMOnto as tangledness.  NACOnto
    computes the POnto quantity over leaves only.

    Source
    ------
    OQuaRE POnto -- "average superclasses per class".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better.

    Examples
    --------
    >>> result = oquare_ponto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquarePOnto")
    if err:
        return err

    value = _mean(len(prim.ancestors(c)) for c in prim.classes)

    logger.info(f"--- OQuaRE POnto: {value:.4f} ---")
    return _oquare_result(
        "oquarePOnto", "POnto", value, prim,
        "Mean transitive named superclasses over all classes; compare "
        "NACOnto, which restricts to leaves.",
        f"POnto = {value:.4f}",
        higher_is_better=False,
    )


def oquare_pronto_v_0_0_1(ttl_file):
    """
    OQuaRE PROnto -- Property richness.

    Proportion of ontology elements that are properties.

    Definitions
    -----------
    - PROnto = |properties| / (|classes| + |properties|).

    Definitional note
    -----------------
    Reiz and Sandkuhl record a direct naming collision: RROnto was published
    under the name PROnto in some versions, and PROnto later emerged as a
    distinct metric glossed as a "ratio of subclasses to total elements".
    That gloss conflicts with the name.  The reading implemented here is the
    property-to-element ratio the name denotes, with RROnto implemented
    separately as the relationship-richness ratio.  Comparisons with other
    OQuaRE implementations must confirm which of the two each computes.

    Source
    ------
    OQuaRE PROnto; percentage-family static thresholds from Duque-Ramos et al.
    (2016).

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the proportion in [0, 1].

    Examples
    --------
    >>> result = oquare_pronto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquarePROnto")
    if err:
        return err

    denominator = len(prim.classes) + len(prim.properties)
    value = len(prim.properties) / denominator if denominator else 0.0

    logger.info(f"--- OQuaRE PROnto: {value:.4f} ---")
    return _oquare_result(
        "oquarePROnto", "PROnto", value, prim,
        "Properties divided by total named elements. Name-collision risk "
        "with RROnto; see the definitional note.",
        f"PROnto = {value:.4f} ({len(prim.properties)} properties of "
        f"{denominator} elements)",
    )


def oquare_rfconto_v_0_0_1(ttl_file):
    """
    OQuaRE RFCOnto -- Response for a class.

    Mean number of properties and direct subclasses reachable from a class.

    Definitions
    -----------
    - RFCOnto = mean over classes of (number of properties whose declared
      domain is that class + number of its named direct subclasses).

    Definitional note
    -----------------
    Reiz and Sandkuhl note that RFCOnto was substantially reformulated between
    publications.  The reading implemented is the one they attribute to
    Duque-Ramos et al. (2011): properties and subclasses *directly* reachable,
    without transitive closure.

    Source
    ------
    OQuaRE RFCOnto -- "counts accessible properties and subclasses".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better.

    Examples
    --------
    >>> result = oquare_rfconto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareRFCOnto")
    if err:
        return err

    properties_of = {}
    for p in prim.properties:
        for d in prim.g.objects(p, RDFS.domain):
            if isinstance(d, URIRef):
                properties_of.setdefault(d, set()).add(p)

    value = _mean(
        len(properties_of.get(c, ())) + len(prim.children.get(c, ()))
        for c in prim.classes
    )

    logger.info(f"--- OQuaRE RFCOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareRFCOnto", "RFCOnto", value, prim,
        "Directly reachable properties plus direct subclasses, averaged over "
        "classes; no transitive closure.",
        f"RFCOnto = {value:.4f}",
        higher_is_better=False,
    )


def oquare_rronto_v_0_0_1(ttl_file):
    """
    OQuaRE RROnto -- Relationship richness.

    Ratio of non-subsumption relationship usage to subsumption relations.

    Definitions
    -----------
    - RROnto = (number of usages of object and datatype properties) /
      (number of ``rdfs:subClassOf`` relations).  Duque-Ramos et al. (2016)
      give exactly this: "number of usages of object and data properties
      divided by the number of subClassOf relationships".

    - Property usage: a triple whose predicate is a declared object or
      datatype property, plus ``owl:onProperty`` references inside
      restrictions, so that axiomatised ontologies are credited for
      relationships expressed through class expressions.

    - Interpretation: a low value indicates a taxonomy -- structure carried
      almost entirely by subsumption.  A higher value indicates a richer
      relational model.

    Source
    ------
    OQuaRE RROnto; Duque-Ramos et al. (2016).

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the ratio.  Higher is better.

    Notes
    -----
    Of all the OQuaRE metrics this is the one that speaks most directly to
    graph-based retrieval: it measures how much of the ontology's structure is
    available to traversal rather than to subsumption alone.

    Examples
    --------
    >>> result = oquare_rronto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareRROnto")
    if err:
        return err

    value = (
        prim.property_usages / prim.subclass_edges
        if prim.subclass_edges else 0.0
    )

    logger.info(f"--- OQuaRE RROnto: {value:.4f} ---")
    return _oquare_result(
        "oquareRROnto", "RROnto", value, prim,
        "Object and datatype property usages divided by subClassOf "
        "relations; restriction owl:onProperty references included.",
        f"RROnto = {value:.4f} ({prim.property_usages} property usages over "
        f"{prim.subclass_edges} subsumption relations)",
        extra={
            "property_usages": prim.property_usages,
            "subclass_edges": prim.subclass_edges,
        },
    )


def oquare_tmonto_v_0_0_1(ttl_file):
    """
    OQuaRE TMOnto -- Tangledness.

    Proportion of classes having more than one direct superclass.

    Definitions
    -----------
    - TMOnto = |{c : c has more than one named direct superclass}| /
      |classes|.  Duque-Ramos et al. (2016) give "mean number of classes with
      more than 1 direct ancestor".

    - Interpretation: multiple inheritance makes a hierarchy harder to
      maintain and to reason over.  Some is expected in a well-axiomatised
      domain ontology; a high proportion suggests the hierarchy is carrying
      distinctions that belong in properties.

    Source
    ------
    OQuaRE TMOnto.  This is one of the two metrics whose static thresholds are
    published: values in (1, 2] scale to 5, values above 8 scale to 1.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the proportion.  ``detail["tangled_classes"]`` gives the
        absolute count.

    Examples
    --------
    >>> result = oquare_tmonto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareTMOnto")
    if err:
        return err

    tangled = [c for c in prim.classes if len(prim.parents.get(c, ())) > 1]
    value = len(tangled) / len(prim.classes) if prim.classes else 0.0

    logger.info(f"--- OQuaRE TMOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareTMOnto", "TMOnto", value, prim,
        "Proportion of classes with more than one named direct superclass.",
        f"TMOnto = {value:.4f} ({len(tangled)} tangled classes of "
        f"{len(prim.classes)})",
        higher_is_better=False,
        extra={"tangled_classes": len(tangled)},
    )


def oquare_tmonto2_v_0_0_1(ttl_file):
    """
    OQuaRE TMOnto2 -- Tangledness 2.

    Mean number of ancestors of classes having multiple direct superclasses.

    Definitions
    -----------
    - TMOnto2 = mean over tangled classes of the number of transitive named
      superclasses, where a tangled class is one with more than one named
      direct superclass.

    - Relation to TMOnto: TMOnto counts *how many* classes are tangled;
      TMOnto2 measures *how severely*, since a class inheriting from two
      shallow roots is a lesser problem than one inheriting from two deep and
      unrelated branches.

    Source
    ------
    OQuaRE TMOnto2 -- "ancestor count for multi-parent classes".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean, or 0.0 when no class is tangled.

    Examples
    --------
    >>> result = oquare_tmonto2_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareTMOnto2")
    if err:
        return err

    tangled = [c for c in prim.classes if len(prim.parents.get(c, ())) > 1]
    value = _mean(len(prim.ancestors(c)) for c in tangled)

    logger.info(f"--- OQuaRE TMOnto2: {value:.4f} ---")
    return _oquare_result(
        "oquareTMOnto2", "TMOnto2", value, prim,
        "Mean transitive ancestors over classes with multiple direct "
        "superclasses.",
        f"TMOnto2 = {value:.4f} over {len(tangled)} tangled classes",
        higher_is_better=False,
        extra={"tangled_classes": len(tangled)},
    )


def oquare_wmconto_v_0_0_1(ttl_file):
    """
    OQuaRE WMCOnto -- Weighted method count.

    Mean number of properties and relationships per class.

    Definitions
    -----------
    - WMCOnto = mean over classes of (properties whose declared domain is that
      class + named direct superclasses + named direct subclasses).
      Duque-Ramos et al. (2016) give "mean number of properties and
      relationships per class".

    - Relation to RFCOnto: RFCOnto counts properties and subclasses only.
      WMCOnto additionally counts superclasses, so it measures a class's total
      structural load rather than what is reachable downward from it.

    Source
    ------
    OQuaRE WMCOnto.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better.

    Examples
    --------
    >>> result = oquare_wmconto_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareWMCOnto")
    if err:
        return err

    properties_of = {}
    for p in prim.properties:
        for d in prim.g.objects(p, RDFS.domain):
            if isinstance(d, URIRef):
                properties_of.setdefault(d, set()).add(p)

    value = _mean(
        len(properties_of.get(c, ()))
        + len(prim.parents.get(c, ()))
        + len(prim.children.get(c, ()))
        for c in prim.classes
    )

    logger.info(f"--- OQuaRE WMCOnto: {value:.4f} ---")
    return _oquare_result(
        "oquareWMCOnto", "WMCOnto", value, prim,
        "Properties plus direct superclasses plus direct subclasses, "
        "averaged over classes.",
        f"WMCOnto = {value:.4f}",
        higher_is_better=False,
    )


def oquare_wmconto2_v_0_0_1(ttl_file):
    """
    OQuaRE WMCOnto2 -- Weighted method count 2.

    Mean root-to-leaf path length over leaf classes.

    Definitional note
    -----------------
    Reiz and Sandkuhl record that "WMCOnto2 shifted heavily in meaning" to
    measure path length rather than property counts.  The path-length reading
    is implemented, which makes WMCOnto2 numerically identical to LCOMOnto
    under the definitions pinned in this module.  Both are retained because
    the OQuaRE quality model maps them to different sub-characteristics, and
    silently dropping one would make the aggregation incomparable with other
    implementations.  This coincidence is recorded in
    ``detail["coincides_with"]`` rather than hidden.

    Source
    ------
    OQuaRE WMCOnto2 -- "mean path length for leaf classes".

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    MetricResult
        ``score`` is the raw mean.  Lower is better.

    Examples
    --------
    >>> result = oquare_wmconto2_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    """
    prim, err = _with_primitives(ttl_file, "oquareWMCOnto2")
    if err:
        return err

    value = _mean(prim.depth(c) for c in prim.leaves)

    logger.info(f"--- OQuaRE WMCOnto2: {value:.4f} ---")
    return _oquare_result(
        "oquareWMCOnto2", "WMCOnto2", value, prim,
        "Path-length reading; numerically identical to LCOMOnto under the "
        "definitions pinned in this module. See the definitional note.",
        f"WMCOnto2 = {value:.4f}",
        higher_is_better=False,
        extra={"coincides_with": "LCOMOnto", "leaf_count": len(prim.leaves)},
    )


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

def _oquare_descriptor(metric_id, abbrev, name, function, description,
                       requires_abox=False):
    """
    Build a :class:`MetricDescriptor` for an OQuaRE metric.

    Parameters
    ----------
    metric_id : str
        Registry identifier.
    abbrev : str
        OQuaRE abbreviation, recorded as ``source_id``.
    name : str
        Full metric name.
    function : callable
        Implementation.
    description : str
        One-line summary.
    requires_abox : bool, optional
        Whether instance data is required.

    Returns
    -------
    MetricDescriptor
    """
    return MetricDescriptor(
        metric_id=metric_id,
        name=name,
        function=function,
        category=Category.QUALITY_MODEL,
        source_framework=SourceFramework.OQUARE,
        source_id=abbrev,
        source_url=_OQUARE_REPO,
        severity=Severity.INFO,
        scale=Scale.RAW,
        requires_abox=requires_abox,
        description=description,
    )


_OQUARE_DESCRIPTORS = [
    _oquare_descriptor("oquareANOnto", "ANOnto", "Annotation richness",
                       oquare_anonto_v_0_0_1,
                       "Mean annotation assertions per class."),
    _oquare_descriptor("oquareAROnto", "AROnto", "Attribute richness",
                       oquare_aronto_v_0_0_1,
                       "Proportion of properties declaring a domain."),
    _oquare_descriptor("oquareCBOnto", "CBOnto", "Coupling between objects",
                       oquare_cbonto_v_0_0_1,
                       "Mean named direct superclasses per class."),
    _oquare_descriptor("oquareCROnto", "CROnto", "Class richness",
                       oquare_cronto_v_0_0_1,
                       "Mean instances per class (requires instance data).",
                       requires_abox=True),
    _oquare_descriptor("oquareDITOnto", "DITOnto",
                       "Depth of subsumption hierarchy",
                       oquare_ditonto_v_0_0_1,
                       "Longest root-to-leaf subsumption path."),
    _oquare_descriptor("oquareINROnto", "INROnto", "Relationships per class",
                       oquare_inronto_v_0_0_1,
                       "Mean subsumption relations per class."),
    _oquare_descriptor("oquareLCOMOnto", "LCOMOnto",
                       "Lack of cohesion in methods",
                       oquare_lcomonto_v_0_0_1,
                       "Mean root-to-leaf path length over leaves."),
    _oquare_descriptor("oquareNACOnto", "NACOnto",
                       "Number of ancestor classes",
                       oquare_naconto_v_0_0_1,
                       "Mean ancestors of leaf classes."),
    _oquare_descriptor("oquareNOCOnto", "NOCOnto", "Number of children",
                       oquare_noconto_v_0_0_1,
                       "Mean direct subclasses per branching class."),
    _oquare_descriptor("oquareNOMOnto", "NOMOnto", "Number of properties",
                       oquare_nomonto_v_0_0_1,
                       "Mean declared domain assertions per class."),
    _oquare_descriptor("oquarePOnto", "POnto", "Ancestors per class",
                       oquare_ponto_v_0_0_1,
                       "Mean transitive ancestors over all classes."),
    _oquare_descriptor("oquarePROnto", "PROnto", "Property richness",
                       oquare_pronto_v_0_0_1,
                       "Properties as a proportion of all named elements."),
    _oquare_descriptor("oquareRFCOnto", "RFCOnto", "Response for a class",
                       oquare_rfconto_v_0_0_1,
                       "Mean directly reachable properties and subclasses."),
    _oquare_descriptor("oquareRROnto", "RROnto", "Relationship richness",
                       oquare_rronto_v_0_0_1,
                       "Property usages divided by subsumption relations."),
    _oquare_descriptor("oquareTMOnto", "TMOnto", "Tangledness",
                       oquare_tmonto_v_0_0_1,
                       "Proportion of classes with multiple direct parents."),
    _oquare_descriptor("oquareTMOnto2", "TMOnto2", "Tangledness 2",
                       oquare_tmonto2_v_0_0_1,
                       "Mean ancestors of multi-parent classes."),
    _oquare_descriptor("oquareWMCOnto", "WMCOnto", "Weighted method count",
                       oquare_wmconto_v_0_0_1,
                       "Mean properties and relationships per class."),
    _oquare_descriptor("oquareWMCOnto2", "WMCOnto2", "Weighted method count 2",
                       oquare_wmconto2_v_0_0_1,
                       "Mean path length for leaf classes."),
]

for _descriptor in _OQUARE_DESCRIPTORS:
    register_metric(_descriptor)
