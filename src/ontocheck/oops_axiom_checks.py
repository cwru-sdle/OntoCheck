"""
OOPS!-derived axiom-pattern, task-based and availability pitfall checks.

Implements the OOPS! pitfalls that are decided by inspecting logical axioms
(restrictions, property characteristics, inverse/equivalence axioms), by a
DL reasoner, by competency questions, or by dereferencing the ontology on the
Web.

Pitfalls implemented here
-------------------------
======  ==========================================  ==========
Code    Pitfall                                     Importance
======  ==========================================  ==========
P05     Defining wrong inverse relationships        critical
P09     Missing domain information                  minor
P14     Misusing owl:allValuesFrom                  critical
P15     Using "some not" in place of "not some"     critical
P16     Using a primitive class in place of a
        defined one                                 critical
P17     Overspecializing a hierarchy                important
P18     Overspecializing the domain or range        important
P27     Defining wrong equivalent properties        critical
P28     Defining wrong symmetric relationships      critical
P29     Defining wrong transitive relationships     critical
P31     Defining wrong equivalent classes           critical
P37     Ontology not available on the Web           critical
======  ==========================================  ==========

Requirements
------------
- P09 needs competency questions (SPARQL) and is skipped without them.  It is
  the pitfall that ties OOPS! to OntoCheck's task-based evaluation: the
  "intended domain" is operationalised as the terms the tasks need.
- P17 needs instance data and is skipped for TBox-only files.
- P37 needs network access.
- P31 runs a HermiT classification through ``owlready2`` when a Java runtime
  is available and reports ``detail["reasoner"] = False`` otherwise.

Heuristic checks
----------------
P05, P14, P16, P18, P27, P28, P29 and P31 detect axiom patterns that are
*usually* modelling errors; whether a given axiom is wrong depends on the
modeller's intent, exactly as in OOPS!.  Each sets
``detail["heuristic"] = True``.

Source
------
OOPS! Pitfall Catalogue -- https://oops.linkeddata.es/catalogue.jsp

Poveda-Villalon, M., Gomez-Perez, A., & Suarez-Figueroa, M. C. (2014).
OOPS! (OntOlogy Pitfall Scanner!): An on-line tool for ontology evaluation.
*International Journal on Semantic Web and Information Systems*, 10(2), 7-34.

Rector, A. et al. (2004).  OWL Pizzas: Practical experience of teaching
OWL-DL: Common errors & common patterns.  *EKAW 2004*, LNCS 3257, 63-81
(source of the P14, P15 and P16 error patterns).

Version: 0.0.1

.. note::

   Claude AI (Opus 5) was employed chiefly to support documentation efforts.
"""

import logging
from collections import defaultdict

from rdflib import Literal, OWL, RDF, RDFS, URIRef, XSD

from .helpers.oops_helpers import (
    _disjoint_pairs,
    _is_foundational,
    _load_graph,
    _named_classes,
    _ontology_iri,
    _own_namespace,
)
from .helpers.semantic_helpers import (
    _http_get,
    _individuals,
    _object_and_datatype_properties,
    _owning_class,
    _parse_rdf_response,
    _restrictions_on,
    _run_reasoner,
    _subsumed,
    _told_superclasses,
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
from .oops_lexical_checks import _is_own, _load_error, _own_classes

logger = logging.getLogger(__name__)

_CATALOGUE = "https://oops.linkeddata.es/catalogue.jsp"


def _values(g, s, p):
    """
    Return the named (URI) objects of ``(s, p, ?)``.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    s : rdflib.term.Node
        Subject.
    p : rdflib.URIRef
        Predicate.

    Returns
    -------
    set of rdflib.URIRef
        URI objects; anonymous class expressions are ignored.
    """
    return {o for o in g.objects(s, p) if isinstance(o, URIRef)}


def _related(supers, a_set, b_set):
    """
    Test whether two sets of classes are related by told subsumption.

    Parameters
    ----------
    supers : callable
        Closure returned by ``_told_superclasses``.
    a_set, b_set : set of rdflib.URIRef
        Declared domains or ranges.  An empty set means "not declared".

    Returns
    -------
    bool
        ``True`` if either set is empty, or if every member of one set is
        subsumed by some member of the other (in either direction).
    """
    if not a_set or not b_set:
        return True
    a_in_b = all(any(_subsumed(supers, a, b) for b in b_set) for a in a_set)
    b_in_a = all(any(_subsumed(supers, b, a) for a in a_set) for b in b_set)
    return a_in_b or b_in_a


def _equal_sets(supers, a_set, b_set):
    """
    Test whether two sets of classes are equal up to told subsumption.

    Parameters
    ----------
    supers : callable
        Closure returned by ``_told_superclasses``.
    a_set, b_set : set of rdflib.URIRef
        Declared domains or ranges.

    Returns
    -------
    bool
        ``True`` when each member of each set is subsumed by some member of
        the other set.
    """
    return (all(any(_subsumed(supers, a, b) for b in b_set) for a in a_set)
            and all(any(_subsumed(supers, b, a) for a in a_set) for b in b_set))


# ---------------------------------------------------------------------------
# P05 -- Defining wrong inverse relationships
# ---------------------------------------------------------------------------

def oops_p05_wrong_inverse_v_0_0_1(ttl_file):
    """
    OOPS! P05 -- Defining wrong inverse relationships.

    Identify ``owl:inverseOf`` pairs whose declared domains and ranges do
    not mirror each other.

    Definitions
    -----------
    - Mirroring: if ``p owl:inverseOf q``, every ``(x, y)`` in ``p`` is
      ``(y, x)`` in ``q``, so the domain of ``p`` must match the range of
      ``q`` and the range of ``p`` the domain of ``q``.

    - Wrong inverse: a pair where a declared domain of one property and a
      declared range of the other are unrelated by told subsumption in
      either direction, or where one member is a datatype property (which
      cannot have an inverse in OWL 2).

    Source
    ------
    OOPS! P05 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of wrong inverse pairs; ``passed`` is
        ``True`` when there are none.

    Output Information
    ------------------
    - Each flagged pair with the mismatching domain/range

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    Pairs where one side is merely narrower than the other (told
    subsumption holds) are reported in ``detail["narrower"]`` but not
    counted.

    Examples
    --------
    >>> r = oops_p05_wrong_inverse_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP05WrongInverse"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    supers = _told_superclasses(g)
    datatype = set(g.subjects(RDF.type, OWL.DatatypeProperty))

    pairs = {tuple(sorted((s, o), key=str))
             for s, o in g.subject_objects(OWL.inverseOf)
             if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o}
    flagged, narrower = [], []
    for p, q in sorted(pairs, key=lambda x: (str(x[0]), str(x[1]))):
        reasons = []
        if p in datatype or q in datatype:
            reasons.append("datatype property declared with an inverse")
        for a, b, what in ((p, q, "domain(p)/range(q)"),
                           (q, p, "domain(q)/range(p)")):
            dom, rng = _values(g, a, RDFS.domain), _values(g, b, RDFS.range)
            if not _related(supers, dom, rng):
                reasons.append(f"{what} unrelated: "
                               f"{sorted(map(str, dom))} vs "
                               f"{sorted(map(str, rng))}")
            elif dom and rng and not _equal_sets(supers, dom, rng):
                narrower.append({"pair": [str(p), str(q)], "where": what})
        if reasons:
            flagged.append({"pair": [str(p), str(q)], "reasons": reasons})

    logger.info("--- OOPS! P05: wrong inverse relationships ---")
    logger.info(f"Inverse pairs: {len(pairs)}; flagged: {len(flagged)}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=sorted({x for f in flagged for x in f["pair"]}),
        total_examined=len(pairs),
        detail={"flagged": flagged, "narrower": narrower, "heuristic": True},
        message=(f"{len(flagged)} inverse pair(s) with non-mirroring "
                 f"domain/range" if flagged
                 else "All inverse pairs mirror domain and range"),
    )


# ---------------------------------------------------------------------------
# P09 -- Missing domain information
# ---------------------------------------------------------------------------

def oops_p09_missing_domain_information_v_0_0_1(ttl_file, questions=None,
                                                domain_prefixes=None,
                                                domain_ns_fragments=None):
    """
    OOPS! P09 -- Missing domain information.

    Identify domain terms that the competency questions need but the
    ontology does not define.

    Definitions
    -----------
    - Required terms (T_a): local names referenced under the domain prefixes
      in the SPARQL competency questions.

    - Defined terms (T_o): local names of the non-foundational terms declared
      in the ontology.

    - Missing domain information: ``T_a \\ T_o``.  The OOPS! catalogue
      defines P09 against "the Ontology Requirement Specification Document";
      competency questions are that document's executable form.

    Source
    ------
    OOPS! P09 (minor) -- https://oops.linkeddata.es/catalogue.jsp.
    OOPS! cannot detect P09 because it has no access to requirements;
    OntoCheck can, through its task-based metric.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    questions : str, pathlib.Path, list of str, or None
        Competency questions in any form accepted by
        ``task_based_metric_v_0_0_1``.
    domain_prefixes : list of str or None
        SPARQL prefixes marking domain terms (e.g. ``["mds"]``).
    domain_ns_fragments : list of str or None, optional
        Namespace fragments restricting T_o.

    Returns
    -------
    MetricResult
        ``score`` is ``|T_a \\ T_o|``; ``passed`` is ``True`` when every
        required term is defined.  ``total_examined`` is ``|T_a|``.

    Output Information
    ------------------
    - The required terms that the ontology does not define

    Error Handling
    --------------
    - Without questions or prefixes the result has a ``"Skipped"`` status.
    - Errors raised by the task-based metric are reported in ``status``.

    Examples
    --------
    >>> r = oops_p09_missing_domain_information_v_0_0_1(       # doctest: +SKIP
    ...     "xrd.ttl", questions="xrd_cqs.json", domain_prefixes=["mds"])
    """
    mid = "oopsP09MissingDomainInfo"
    if not questions or not domain_prefixes:
        return MetricResult(metric_id=mid,
                            status="Skipped (requires competency questions)",
                            message="No competency questions supplied")
    try:
        from .task_based_metric import task_based_metric_v_0_0_1
    except ImportError as e:
        return MetricResult(metric_id=mid, status=f"Error: {e}")
    try:
        tb = task_based_metric_v_0_0_1(ttl_file, questions, domain_prefixes,
                                       domain_ns_fragments=domain_ns_fragments)
    except Exception as e:
        return MetricResult(metric_id=mid, status=f"Error: {e}")
    missing = sorted(tb.get("missing_from_onto", ()))

    logger.info("--- OOPS! P09: missing domain information ---")
    logger.info(f"Required terms: {tb.get('T_a_count')}; missing: {len(missing)}")
    for m in missing:
        logger.info(f"  {m}")

    return MetricResult(
        metric_id=mid,
        score=len(missing),
        passed=not missing,
        affected=missing,
        total_examined=tb.get("T_a_count", 0),
        detail={"missing_terms": missing, "recall": tb.get("recall"),
                "query_count": tb.get("query_count")},
        message=(f"{len(missing)} term(s) required by the competency "
                 f"questions are not defined" if missing
                 else "Every term required by the competency questions is "
                      "defined"),
    )


# ---------------------------------------------------------------------------
# P14 -- Misusing owl:allValuesFrom
# ---------------------------------------------------------------------------

_EXISTENTIAL_KINDS = {
    OWL.someValuesFrom, OWL.hasValue, OWL.minCardinality, OWL.cardinality,
    OWL.minQualifiedCardinality, OWL.qualifiedCardinality,
}


def oops_p14_misused_allvaluesfrom_v_0_0_1(ttl_file):
    """
    OOPS! P14 -- Misusing ``owl:allValuesFrom``.

    Identify universal restrictions used where an existential restriction
    was probably intended.

    Definitions
    -----------
    - Unsupported universal: a restriction ``C ⊑ ∀p.D`` on an own class
      where neither ``C`` nor any of its told superclasses also asserts an
      existential commitment on ``p`` (``∃p``, ``hasValue``, or a minimum or
      exact cardinality ≥ 1).  A universal alone is satisfied by individuals
      with no ``p`` value at all, so it does not say that ``C`` *has* a
      ``p`` -- the classic "only without some" error.

    Source
    ------
    OOPS! P14 (critical) -- https://oops.linkeddata.es/catalogue.jsp;
    Rector et al. (2004), "OWL Pizzas", common error 3.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of unsupported universal restrictions;
        ``passed`` is ``True`` when there are none.
        ``detail["universal_restrictions"]`` counts all universals examined.

    Output Information
    ------------------
    - Each flagged ``(class, property, filler)``

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p14_misused_allvaluesfrom_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP14MisusedAllValuesFrom"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    supers = _told_superclasses(g)
    classes = _own_classes(g, own_ns)

    restr = {c: _restrictions_on(g, c) for c in _named_classes(g)}
    universals, flagged = 0, []
    for c in sorted(classes, key=str):
        for r in restr.get(c, ()):
            if r["kind"] != OWL.allValuesFrom:
                continue
            universals += 1
            p = r["property"]
            supported = any(
                other["property"] == p and other["kind"] in _EXISTENTIAL_KINDS
                for anc in supers(c) for other in restr.get(anc, ())
            )
            if not supported:
                flagged.append({"class": str(c), "property": str(p),
                                "filler": str(r["filler"])})

    logger.info("--- OOPS! P14: misused owl:allValuesFrom ---")
    logger.info(f"Universal restrictions: {universals}; unsupported: "
                f"{len(flagged)}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=sorted({f["class"] for f in flagged}),
        total_examined=len(classes),
        detail={"flagged": flagged, "universal_restrictions": universals,
                "heuristic": True},
        message=(f"{len(flagged)} owl:allValuesFrom restriction(s) without "
                 f"an existential counterpart" if flagged
                 else "No misused owl:allValuesFrom"),
    )


# ---------------------------------------------------------------------------
# P15 -- Using "some not" in place of "not some"
# ---------------------------------------------------------------------------

def oops_p15_some_not_v_0_0_1(ttl_file):
    """
    OOPS! P15 -- Using "some not" in place of "not some".

    Identify existential restrictions over a complement class.

    Definitions
    -----------
    - "Some not": a restriction ``∃p.¬D`` (``owl:someValuesFrom`` whose
      filler is an ``owl:complementOf`` expression).  It states that at
      least one ``p``-value is not a ``D``, which is almost never what is
      meant; the intended statement is usually ``¬∃p.D`` ("has no
      ``p``-value that is a ``D``").

    Source
    ------
    OOPS! P15 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of "some not" restrictions; ``passed`` is
        ``True`` when there are none.

    Output Information
    ------------------
    - Each flagged restriction with its owning class, property and the
      complemented class

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p15_some_not_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP15SomeNot"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)

    flagged = []
    restrictions = list(g.subjects(RDF.type, OWL.Restriction))
    for r in restrictions:
        filler = g.value(r, OWL.someValuesFrom)
        if filler is None:
            continue
        neg = g.value(filler, OWL.complementOf)
        if neg is not None:
            owner = _owning_class(g, r)
            flagged.append({"class": str(owner) if owner else None,
                            "property": str(g.value(r, OWL.onProperty)),
                            "complement_of": str(neg)})

    logger.info("--- OOPS! P15: 'some not' restrictions ---")
    logger.info(f"Flagged: {len(flagged)} of {len(restrictions)} restrictions")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=sorted({f["class"] or "<anonymous>" for f in flagged}),
        total_examined=len(restrictions),
        detail={"flagged": flagged},
        message=(f"{len(flagged)} 'some not' restriction(s)" if flagged
                 else "No 'some not' restrictions"),
    )


# ---------------------------------------------------------------------------
# P16 -- Using a primitive class in place of a defined one
# ---------------------------------------------------------------------------

def oops_p16_primitive_instead_of_defined_v_0_0_1(ttl_file):
    """
    OOPS! P16 -- Using a primitive class in place of a defined one.

    Identify primitive classes whose necessary conditions another class
    already satisfies, so that a reasoner would classify that class under
    it -- if only the conditions were stated as sufficient.

    Definitions
    -----------
    - Primitive class: an own class with necessary conditions only
      (``rdfs:subClassOf``) and no ``owl:equivalentClass`` axiom.

    - Signature: the set of ``(property, filler)`` pairs of the existential
      and ``hasValue`` restrictions a class asserts, together with its named
      direct superclasses.

    - Missed classification: a primitive class ``C`` with a non-empty
      restriction signature and another class ``D``, not told to be a
      subclass of ``C``, whose signature (including inherited restrictions)
      contains all of ``C``'s restrictions and whose superclasses include
      all of ``C``'s named superclasses.  Were ``C`` defined, the reasoner
      would infer ``D ⊑ C``; as a primitive class it cannot.

    Source
    ------
    OOPS! P16 (critical) -- https://oops.linkeddata.es/catalogue.jsp;
    Rector et al. (2004), "OWL Pizzas", common error 1.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of primitive classes with at least one missed
        classification; ``passed`` is ``True`` when there are none.
        ``detail`` also reports how many own classes are defined.

    Output Information
    ------------------
    - Each flagged class with the classes that satisfy its conditions

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    Heuristic.  Whether automatic classification is *intended* is a design
    decision; a flagged class may equally reveal that its conditions are too
    weak to characterise it.

    Examples
    --------
    >>> r = oops_p16_primitive_instead_of_defined_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "oopsP16PrimitiveNotDefined"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    supers = _told_superclasses(g)
    classes = sorted(_own_classes(g, own_ns), key=str)

    def own_sig(c):
        """Return the ``(property, filler)`` pairs of ``c``'s existential restrictions."""
        return {(r["property"], r["filler"]) for r in _restrictions_on(g, c)
                if r["kind"] in (OWL.someValuesFrom, OWL.hasValue)
                and r["axiom"] == "subClassOf" and r["filler"] is not None}

    sig = {c: own_sig(c) for c in classes}
    inherited = {c: set().union(*(sig.get(a, set()) for a in supers(c)))
                 for c in classes}
    parents = {c: {o for o in g.objects(c, RDFS.subClassOf)
                   if isinstance(o, URIRef)} for c in classes}
    defined = [c for c in classes
               if any(True for _ in g.objects(c, OWL.equivalentClass))]
    primitive = [c for c in classes if c not in defined and sig[c]]

    flagged = []
    for c in primitive:
        hits = [d for d in classes
                if d != c and c not in supers(d)
                and sig[c] <= inherited[d]
                and all(_subsumed(supers, d, p) for p in parents[c])]
        if hits:
            flagged.append({"class": str(c),
                            "would_classify": sorted(map(str, hits))})

    logger.info("--- OOPS! P16: primitive instead of defined classes ---")
    logger.info(f"Defined own classes: {len(defined)}; primitive classes with "
                f"restrictions: {len(primitive)}; flagged: {len(flagged)}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=[f["class"] for f in flagged],
        total_examined=len(primitive),
        detail={"flagged": flagged, "defined_classes": len(defined),
                "primitive_with_restrictions": len(primitive),
                "heuristic": True},
        message=(f"{len(flagged)} primitive class(es) whose conditions other "
                 f"classes already meet" if flagged
                 else "No missed classifications from primitive classes"),
    )


# ---------------------------------------------------------------------------
# P17 -- Overspecializing a hierarchy
# ---------------------------------------------------------------------------

def oops_p17_overspecialized_hierarchy_v_0_0_1(ttl_file):
    """
    OOPS! P17 -- Overspecializing a hierarchy.

    Identify leaf classes that have no instances in the knowledge graph.

    Definitions
    -----------
    - Leaf class: an own class with no named subclass.

    - Overspecialised leaf: a leaf class with no asserted instance, when the
      graph does contain instance data.  The OOPS! definition is "final leaf
      classes will not have instances"; with the data present this can be
      tested rather than guessed.

    Source
    ------
    OOPS! P17 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology plus instance data, as Turtle.

    Returns
    -------
    MetricResult
        ``score`` is the number of leaf classes without instances; ``passed``
        is ``True`` when every leaf class is instantiated.

    Output Information
    ------------------
    - Leaf classes without instances, and the number of individuals seen

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - A file with no individuals yields a ``"Skipped"`` status.

    Notes
    -----
    Registered with ``requires_abox=True``.  Useful for the evolving,
    data-contextualised setting OntoCheck targets: running it against each
    new data release shows which parts of the hierarchy the data actually
    reaches.

    Examples
    --------
    >>> r = oops_p17_overspecialized_hierarchy_v_0_0_1("kg.ttl")  # doctest: +SKIP
    """
    mid = "oopsP17OverspecializedHierarchy"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    individuals = _individuals(g)
    if not individuals:
        return MetricResult(metric_id=mid,
                            status="Skipped (requires instance data / ABox)",
                            message="No individuals in the graph")
    classes = _own_classes(g, own_ns)
    has_sub = {o for s, o in g.subject_objects(RDFS.subClassOf)
               if isinstance(s, URIRef)}
    leaves = {c for c in classes if c not in has_sub}
    instantiated = {t for types in individuals.values() for t in types}
    empty = sorted(str(c) for c in leaves if c not in instantiated)

    logger.info("--- OOPS! P17: overspecialized hierarchy ---")
    logger.info(f"Individuals: {len(individuals)}; leaf classes: {len(leaves)}; "
                f"without instances: {len(empty)}")

    return MetricResult(
        metric_id=mid,
        score=len(empty),
        passed=not empty,
        affected=empty,
        total_examined=len(leaves),
        detail={"individuals": len(individuals), "leaf_classes": len(leaves)},
        message=(f"{len(empty)} of {len(leaves)} leaf class(es) have no "
                 f"instances" if empty else "Every leaf class is instantiated"),
    )


# ---------------------------------------------------------------------------
# P18 -- Overspecializing the domain or range
# ---------------------------------------------------------------------------

def _is_datatype(node):
    """
    Test whether a node names an XSD or RDF datatype.

    Parameters
    ----------
    node : rdflib.term.Node
        Node to test.

    Returns
    -------
    bool
        ``True`` for ``xsd:*`` and ``rdf:langString``/``rdfs:Literal``.
    """
    return isinstance(node, URIRef) and (
        str(node).startswith(str(XSD)) or node in (RDF.langString, RDFS.Literal,
                                                   RDF.PlainLiteral))


_NUMERIC = {XSD.decimal, XSD.integer, XSD.int, XSD.long, XSD.short, XSD.byte,
            XSD.nonNegativeInteger, XSD.positiveInteger, XSD.negativeInteger,
            XSD.nonPositiveInteger, XSD.unsignedInt, XSD.unsignedLong}


def _datatype_fits(actual, declared):
    """
    Test whether a datatype is compatible with a declared range datatype.

    Parameters
    ----------
    actual, declared : rdflib.URIRef
        Datatypes.

    Returns
    -------
    bool
        ``True`` if equal, if the declared range is ``rdfs:Literal``, or if
        ``actual`` is an XSD integer type and ``declared`` is
        ``xsd:decimal`` (the XSD derivation hierarchy).
    """
    if actual == declared or declared in (RDFS.Literal, None):
        return True
    if declared == XSD.decimal and actual in _NUMERIC:
        return True
    if declared == XSD.string and actual in (XSD.normalizedString, XSD.token):
        return True
    return False


def oops_p18_overspecialized_domain_range_v_0_0_1(ttl_file):
    """
    OOPS! P18 -- Overspecializing the domain or range.

    Identify properties whose declared domain or range is narrower than the
    way the ontology (and its data) actually uses them.

    Definitions
    -----------
    - Restriction use: a restriction on property ``p`` inside the
      description of named class ``C``, with filler ``F``.  The restriction
      says ``C``-instances are ``p``-subjects and (for ``∃``/``∀``/qualified
      cardinalities) that ``F``-instances are ``p``-objects.

    - Domain too narrow: ``C`` is not told-subsumed by a declared domain of
      ``p``.  OWL will silently infer ``C ⊑ domain(p)`` -- or report an
      inconsistency if they are disjoint -- instead of the domain covering
      ``C``.

    - Range too narrow: a class filler ``F`` not told-subsumed by a declared
      class range, or a datatype filler incompatible with a declared
      datatype range (e.g. ``xsd:decimal`` against ``xsd:integer``).

    - Instance use: when the graph holds instance data, an assertion
      ``(s, p, o)`` whose subject (object) has asserted types none of which
      is told-subsumed by the domain (range), or whose literal datatype does
      not fit a datatype range.

    Source
    ------
    OOPS! P18 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse; may include
        instance data.

    Returns
    -------
    MetricResult
        ``score`` is the number of properties with an overspecialised domain
        or range; ``passed`` is ``True`` when there are none.

    Output Information
    ------------------
    - Per property, the uses that fall outside the declared domain or range

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    - Undetermined use: the declared domain or range is an imported class
      (outside the own namespace) and the use class's told superclasses reach
      an imported class that has no superclass in the file.  The imported
      hierarchy (e.g. CCO up to BFO) that would decide the question is not
      in the file, so the use is reported in ``detail["undetermined"]`` and
      not counted.

    Notes
    -----
    Told subsumption only: a use covered through a complex class expression
    that only a reasoner would recognise is reported, so review flagged
    properties before narrowing or widening anything.

    Examples
    --------
    >>> r = oops_p18_overspecialized_domain_range_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "oopsP18OverspecializedDomainRange"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    supers = _told_superclasses(g)
    props = _object_and_datatype_properties(g)
    domains = {p: _values(g, p, RDFS.domain) for p in props}
    ranges = {p: _values(g, p, RDFS.range) for p in props}

    own_ns = _own_namespace(g)
    has_parent = {s for s in g.subjects(RDFS.subClassOf, None)}
    undetermined = []

    def open_chain(c, declared):
        """True when the told hierarchy above ``c`` is cut off at an import."""
        if all(_is_own(d, own_ns) for d in declared):
            return False
        return any(isinstance(a, URIRef) and not _is_own(a, own_ns)
                   and a not in has_parent
                   for a in supers(c))

    issues = defaultdict(list)

    def report(p, kind, use, declared):
        """Record a use as an issue, or as undetermined when the hierarchy is cut off."""
        if isinstance(use, URIRef) and open_chain(use, declared):
            undetermined.append({"property": str(p), "kind": kind,
                                 "use": str(use),
                                 "declared": sorted(map(str, declared))})
        else:
            issues[p].append({"kind": kind, "use": str(use),
                              "declared": sorted(map(str, declared))})

    for r in g.subjects(RDF.type, OWL.Restriction):
        p = g.value(r, OWL.onProperty)
        if p not in props:
            continue
        owner = _owning_class(g, r)
        if isinstance(owner, URIRef) and domains[p]:
            if not any(_subsumed(supers, owner, d) for d in domains[p]):
                report(p, "domain", owner, domains[p])
        filler = None
        for fp in (OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass,
                   OWL.onDataRange):
            filler = g.value(r, fp) or filler
        hv = g.value(r, OWL.hasValue)
        if ranges[p]:
            if isinstance(filler, URIRef) and _is_datatype(filler):
                dts = {x for x in ranges[p] if _is_datatype(x)}
                if dts and not any(_datatype_fits(filler, d) for d in dts):
                    issues[p].append({"kind": "range", "use": str(filler),
                                      "declared": sorted(map(str, dts))})
            elif isinstance(filler, URIRef) and filler != OWL.Thing:
                cls_rng = {x for x in ranges[p] if not _is_datatype(x)}
                if cls_rng and not any(_subsumed(supers, filler, x)
                                       for x in cls_rng):
                    report(p, "range", filler, cls_rng)
            if isinstance(hv, Literal) and hv.datatype:
                dts = {x for x in ranges[p] if _is_datatype(x)}
                if dts and not any(_datatype_fits(hv.datatype, d) for d in dts):
                    issues[p].append({"kind": "range", "use": str(hv.datatype),
                                      "declared": sorted(map(str, dts))})

    individuals = _individuals(g)
    abox_uses = 0
    for p in props:
        for s, o in g.subject_objects(p):
            if s not in individuals:
                continue
            abox_uses += 1
            s_types = individuals.get(s, set())
            if domains[p] and s_types and not any(
                    _subsumed(supers, t, d) for t in s_types for d in domains[p]):
                issues[p].append({"kind": "domain (data)",
                                  "use": sorted(map(str, s_types)),
                                  "declared": sorted(map(str, domains[p]))})
            if not ranges[p]:
                continue
            if isinstance(o, Literal):
                dts = {x for x in ranges[p] if _is_datatype(x)}
                dt = o.datatype or (RDF.langString if o.language else XSD.string)
                if dts and not any(_datatype_fits(dt, d) for d in dts):
                    issues[p].append({"kind": "range (data)", "use": str(dt),
                                      "declared": sorted(map(str, dts))})
            elif o in individuals and individuals[o]:
                cls_rng = {x for x in ranges[p] if not _is_datatype(x)}
                if cls_rng and not any(_subsumed(supers, t, x)
                                       for t in individuals[o] for x in cls_rng):
                    issues[p].append({"kind": "range (data)",
                                      "use": sorted(map(str, individuals[o])),
                                      "declared": sorted(map(str, cls_rng))})

    dedup = {}
    for p, lst in issues.items():
        seen, out = set(), []
        for i in lst:
            key = (i["kind"], str(i["use"]))
            if key not in seen:
                seen.add(key)
                out.append(i)
        dedup[str(p)] = out

    logger.info("--- OOPS! P18: overspecialized domain or range ---")
    for p, lst in dedup.items():
        logger.info(f"  {p}: {len(lst)} use(s) outside declared domain/range")

    return MetricResult(
        metric_id=mid,
        score=len(dedup),
        passed=not dedup,
        affected=sorted(dedup),
        total_examined=sum(1 for p in props if domains[p] or ranges[p]),
        detail={"issues": dedup, "undetermined": undetermined,
                "instance_assertions_checked": abox_uses, "heuristic": True},
        message=(f"{len(dedup)} property(ies) used outside their declared "
                 f"domain or range" if dedup
                 else "All uses fall inside declared domains and ranges"),
    )


# ---------------------------------------------------------------------------
# P27 -- Defining wrong equivalent properties
# ---------------------------------------------------------------------------

def oops_p27_wrong_equivalent_properties_v_0_0_1(ttl_file):
    """
    OOPS! P27 -- Defining wrong equivalent properties.

    Identify ``owl:equivalentProperty`` axioms between properties that
    cannot have the same extension.

    Definitions
    -----------
    - Kind mismatch: an object property stated equivalent to a datatype
      property.

    - Declared disjointness: the two properties are also related by
      ``owl:propertyDisjointWith`` -- a definite contradiction.

    - Unrelated signatures: the declared domains, or the declared ranges, of
      the two properties are unrelated by told subsumption in either
      direction.  Equivalent properties have identical extensions, so their
      domains and ranges coincide.

    Source
    ------
    OOPS! P27 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of flagged equivalence axioms; ``passed`` is
        ``True`` when there are none.

    Output Information
    ------------------
    - Each flagged pair with its reasons

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p27_wrong_equivalent_properties_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "oopsP27WrongEquivProperty"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    supers = _told_superclasses(g)
    obj = set(g.subjects(RDF.type, OWL.ObjectProperty))
    dat = set(g.subjects(RDF.type, OWL.DatatypeProperty))

    pairs = {tuple(sorted((s, o), key=str))
             for s, o in g.subject_objects(OWL.equivalentProperty)
             if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o}
    flagged = []
    for a, b in sorted(pairs, key=lambda x: (str(x[0]), str(x[1]))):
        reasons = []
        if (a in obj and b in dat) or (a in dat and b in obj):
            reasons.append("object property equivalent to datatype property")
        if (a, OWL.propertyDisjointWith, b) in g or \
                (b, OWL.propertyDisjointWith, a) in g:
            reasons.append("also declared disjoint")
        for pred, what in ((RDFS.domain, "domains"), (RDFS.range, "ranges")):
            if not _related(supers, _values(g, a, pred), _values(g, b, pred)):
                reasons.append(f"unrelated {what}")
        if reasons:
            flagged.append({"pair": [str(a), str(b)], "reasons": reasons})

    logger.info("--- OOPS! P27: wrong equivalent properties ---")
    logger.info(f"Equivalence axioms: {len(pairs)}; flagged: {len(flagged)}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=sorted({x for f in flagged for x in f["pair"]}),
        total_examined=len(pairs),
        detail={"flagged": flagged, "heuristic": True},
        message=(f"{len(flagged)} suspicious owl:equivalentProperty axiom(s)"
                 if flagged else "No wrong equivalent properties detected"),
    )


# ---------------------------------------------------------------------------
# P28 -- Defining wrong symmetric relationships
# ---------------------------------------------------------------------------

def oops_p28_wrong_symmetric_v_0_0_1(ttl_file):
    """
    OOPS! P28 -- Defining wrong symmetric relationships.

    Identify properties declared ``owl:SymmetricProperty`` whose domain and
    range differ.

    Definitions
    -----------
    - Wrong symmetric property: a symmetric property whose declared domain
      and declared range are not equal up to told subsumption.  Symmetry
      swaps subject and object, so a symmetric relation between different
      kinds of thing forces both into the intersection of domain and range.
      This is the test OOPS! applies.

    - Invalid symmetric property: a datatype property declared symmetric,
      which OWL 2 does not allow.

    Source
    ------
    OOPS! P28 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of flagged symmetric properties; ``passed``
        is ``True`` when there are none.

    Output Information
    ------------------
    - Each flagged property with its domain and range

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p28_wrong_symmetric_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP28WrongSymmetric"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    supers = _told_superclasses(g)
    dat = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    sym = {p for p in g.subjects(RDF.type, OWL.SymmetricProperty)
           if isinstance(p, URIRef)}

    flagged = []
    for p in sorted(sym, key=str):
        dom, rng = _values(g, p, RDFS.domain), _values(g, p, RDFS.range)
        if p in dat:
            flagged.append({"property": str(p),
                            "reason": "datatype property declared symmetric"})
        elif dom and rng and not _equal_sets(supers, dom, rng):
            flagged.append({"property": str(p),
                            "reason": "domain differs from range",
                            "domain": sorted(map(str, dom)),
                            "range": sorted(map(str, rng))})

    logger.info("--- OOPS! P28: wrong symmetric relationships ---")
    logger.info(f"Symmetric properties: {len(sym)}; flagged: {len(flagged)}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=[f["property"] for f in flagged],
        total_examined=len(sym),
        detail={"flagged": flagged, "heuristic": True},
        message=(f"{len(flagged)} suspicious symmetric property(ies)"
                 if flagged else "No wrong symmetric relationships detected"),
    )


# ---------------------------------------------------------------------------
# P29 -- Defining wrong transitive relationships
# ---------------------------------------------------------------------------

def oops_p29_wrong_transitive_v_0_0_1(ttl_file):
    """
    OOPS! P29 -- Defining wrong transitive relationships.

    Identify properties declared ``owl:TransitiveProperty`` that cannot
    sensibly chain, or that break OWL 2 DL's restrictions on transitive
    properties.

    Definitions
    -----------
    - Non-chaining transitive property: a transitive property whose declared
      range is not told-subsumed by its declared domain.  Transitivity
      composes ``p(x, y)`` and ``p(y, z)``, which requires ``y`` to be in
      both the range and the domain; when they differ the axiom either never
      fires or forces unintended types.

    - Non-simple misuse: a transitive property that is also functional or
      inverse-functional, or that is used in a cardinality restriction --
      both disallowed for non-simple properties in OWL 2 DL.

    - Invalid transitive property: a datatype property declared transitive.

    Source
    ------
    OOPS! P29 (critical) -- https://oops.linkeddata.es/catalogue.jsp;
    OWL 2 Structural Specification, section 11.2 (global restrictions on
    non-simple properties).

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of flagged transitive properties; ``passed``
        is ``True`` when there are none.

    Output Information
    ------------------
    - Each flagged property with its reasons

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p29_wrong_transitive_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP29WrongTransitive"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    supers = _told_superclasses(g)
    dat = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    trans = {p for p in g.subjects(RDF.type, OWL.TransitiveProperty)
             if isinstance(p, URIRef)}
    card_preds = (OWL.minCardinality, OWL.maxCardinality, OWL.cardinality,
                  OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality,
                  OWL.qualifiedCardinality)
    in_cardinality = {g.value(r, OWL.onProperty)
                      for r in g.subjects(RDF.type, OWL.Restriction)
                      if any(g.value(r, cp) is not None for cp in card_preds)}

    flagged = []
    for p in sorted(trans, key=str):
        reasons = []
        if p in dat:
            reasons.append("datatype property declared transitive")
        types = set(g.objects(p, RDF.type))
        if types & {OWL.FunctionalProperty, OWL.InverseFunctionalProperty}:
            reasons.append("transitive and (inverse-)functional")
        if p in in_cardinality:
            reasons.append("used in a cardinality restriction")
        dom, rng = _values(g, p, RDFS.domain), _values(g, p, RDFS.range)
        if dom and rng and not all(any(_subsumed(supers, r, d) for d in dom)
                                   for r in rng):
            reasons.append("range not subsumed by domain")
        if reasons:
            flagged.append({"property": str(p), "reasons": reasons})

    logger.info("--- OOPS! P29: wrong transitive relationships ---")
    logger.info(f"Transitive properties: {len(trans)}; flagged: {len(flagged)}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=[f["property"] for f in flagged],
        total_examined=len(trans),
        detail={"flagged": flagged, "heuristic": True},
        message=(f"{len(flagged)} suspicious transitive property(ies)"
                 if flagged else "No wrong transitive relationships detected"),
    )


# ---------------------------------------------------------------------------
# P31 -- Defining wrong equivalent classes
# ---------------------------------------------------------------------------

def oops_p31_wrong_equivalent_classes_v_0_0_1(ttl_file):
    """
    OOPS! P31 -- Defining wrong equivalent classes.

    Identify ``owl:equivalentClass`` axioms that contradict the rest of the
    ontology or collapse classes that were meant to be distinct.

    Definitions
    -----------
    - Disjoint equivalents: two named classes stated equivalent while they,
      or any of their told superclasses, are stated disjoint.  Both classes
      are then unsatisfiable -- a definite error.

    - Unsatisfiable participant (reasoner): a class the reasoner finds
      unsatisfiable and that takes part in, or inherits from a class taking
      part in, an ``owl:equivalentClass`` axiom.

    - Collapsed classes (reasoner): a set of two or more named classes the
      reasoner infers to be equivalent although no equivalence between them
      is asserted.  Distinct identifiers usually mean distinct concepts, so
      an inferred collapse points to an equivalence axiom that is too
      strong.

    Source
    ------
    OOPS! P31 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of classes implicated; ``passed`` is
        ``True`` when there are none.  ``detail["reasoner"]`` records whether
        HermiT ran, and ``detail["consistent"]`` its verdict.

    Output Information
    ------------------
    - Disjoint equivalent pairs, unsatisfiable participants, collapsed sets

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - When no reasoner is available only the first signal is evaluated.

    Notes
    -----
    Requires ``owlready2`` and a Java runtime for the reasoner signals.
    Classification of large ontologies can take several seconds.

    Examples
    --------
    >>> r = oops_p31_wrong_equivalent_classes_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "oopsP31WrongEquivClass"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    supers = _told_superclasses(g)
    disjoint = _disjoint_pairs(g)
    named = [(s, o) for s, o in g.subject_objects(OWL.equivalentClass)
             if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o]

    contradictions = []
    for a, b in named:
        for x in supers(a):
            hit = next((y for y in supers(b)
                        if frozenset((x, y)) in disjoint), None)
            if hit is not None:
                contradictions.append({"pair": [str(a), str(b)],
                                       "disjoint": [str(x), str(hit)]})
                break

    reasoned = _run_reasoner(str(ttl_file))
    unsat_part, collapsed = [], []
    consistent = None
    if reasoned is not None:
        consistent = reasoned["consistent"]
        in_equiv = {s for s, o in g.subject_objects(OWL.equivalentClass)
                    if isinstance(s, URIRef)}
        in_equiv |= {o for s, o in named}
        for iri in reasoned["unsatisfiable"]:
            c = URIRef(iri)
            if supers(c) & in_equiv:
                unsat_part.append(iri)
        asserted = {frozenset((a, b)) for a, b in named}
        for group in reasoned["equivalent_sets"]:
            members = [URIRef(x) for x in group if not _is_foundational(x)]
            if len(members) < 2:
                continue
            new = [frozenset((a, b)) for i, a in enumerate(members)
                   for b in members[i + 1:]
                   if frozenset((a, b)) not in asserted
                   and not (b in supers(a) and a in supers(b))]
            if new:
                collapsed.append(sorted(str(m) for m in members))

    affected = sorted({x for c in contradictions for x in c["pair"]}
                      | set(unsat_part)
                      | {x for grp in collapsed for x in grp})
    if consistent is False:
        affected = affected or ["<ontology is inconsistent>"]

    logger.info("--- OOPS! P31: wrong equivalent classes ---")
    logger.info(f"Named equivalences: {len(named)}; disjoint-equivalent: "
                f"{len(contradictions)}; reasoner: "
                f"{'HermiT' if reasoned is not None else 'unavailable'}")
    if reasoned is not None:
        logger.info(f"Consistent: {consistent}; unsatisfiable participants: "
                    f"{len(unsat_part)}; collapsed sets: {len(collapsed)}")

    return MetricResult(
        metric_id=mid,
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=sum(1 for _ in g.subject_objects(OWL.equivalentClass)),
        detail={"disjoint_equivalents": contradictions,
                "unsatisfiable_participants": unsat_part,
                "collapsed_sets": collapsed,
                "reasoner": reasoned is not None,
                "consistent": consistent,
                "relaxed_datatypes": (reasoned or {}).get("relaxed_datatypes", []),
                "declared_untyped_classes": (reasoned or {}).get(
                    "declared_untyped_classes", []),
                "heuristic": True},
        message=(f"{len(affected)} class(es) implicated in wrong "
                 f"equivalences" if affected
                 else "No wrong equivalent classes detected"
                 + ("" if reasoned is not None else " (no reasoner)")),
    )


# ---------------------------------------------------------------------------
# P37 -- Ontology not available on the Web
# ---------------------------------------------------------------------------

_RDF_ACCEPT = ("text/turtle, application/rdf+xml;q=0.9, "
               "application/ld+json;q=0.8, application/n-triples;q=0.7")


def oops_p37_not_available_on_web_v_0_0_1(ttl_file, timeout=15):
    """
    OOPS! P37 -- Ontology not available on the Web.

    Dereference the ontology URI and check that both its code (an RDF
    serialisation) and its documentation (HTML) are served.

    Definitions
    -----------
    - Ontology URI: the ``owl:Ontology`` IRI, or the own namespace when no
      declaration exists.

    - Code available: a request with an RDF ``Accept`` header returns a
      successful response that parses as RDF.

    - Documentation available: a request with ``Accept: text/html`` returns a
      successful ``text/html`` response.

    - Pitfall: either representation is missing ("code and/or
      documentation", Poveda-Villalon et al. 2014).

    Source
    ------
    OOPS! P37 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    timeout : int or float, optional
        Per-request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when both representations are
        served.  ``detail`` records the HTTP outcome of each request.

    Output Information
    ------------------
    - Status code, final URL and media type for the RDF and HTML requests

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - Network errors are recorded in ``detail`` and count as unavailable.

    Notes
    -----
    Registered with ``requires_network=True``.  FOOPS! CN1, DOC1, RDF1 and
    URI1 decompose the same question into separate tests.

    Examples
    --------
    >>> r = oops_p37_not_available_on_web_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "oopsP37NotOnWeb"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    iri = _ontology_iri(g)
    if iri is None:
        ns = _own_namespace(g)
        iri = ns[0] if isinstance(ns, tuple) else ns
    if iri is None:
        return MetricResult(metric_id=mid, score=False, passed=False,
                            affected=["<no ontology URI>"], total_examined=1,
                            message="No ontology URI to dereference")
    iri = str(iri)

    rdf = _http_get(iri, _RDF_ACCEPT, timeout)
    rdf_ok = _parse_rdf_response(rdf) is not None
    html = _http_get(iri, "text/html", timeout)
    html_ok = bool(html["status"] and html["status"] < 400
                   and html["content_type"] == "text/html")
    ok = rdf_ok and html_ok

    logger.info("--- OOPS! P37: ontology available on the Web ---")
    logger.info(f"URI: {iri}; RDF: {rdf_ok} ({rdf['status']} "
                f"{rdf['content_type']}); HTML: {html_ok} ({html['status']})")

    strip = lambda r: {k: v for k, v in r.items() if k != "text"}  # noqa: E731
    missing = [x for x, good in (("code (RDF)", rdf_ok),
                                 ("documentation (HTML)", html_ok)) if not good]
    return MetricResult(
        metric_id=mid,
        score=ok,
        passed=ok,
        affected=[] if ok else [iri],
        total_examined=1,
        detail={"uri": iri, "rdf_available": rdf_ok, "html_available": html_ok,
                "rdf_response": strip(rdf), "html_response": strip(html)},
        message=("Ontology code and documentation are served at its URI"
                 if ok else f"Not served at {iri}: {', '.join(missing)}"),
    )


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

def _d(metric_id, name, function, category, source_id, severity, scale,
       description, **flags):
    """
    Build an OOPS! metric descriptor with the shared fields filled in.

    Parameters
    ----------
    metric_id, name : str
        Registry identifier and human-readable name.
    function : callable
        Implementation.
    category : Category
        Functional grouping.
    source_id : str
        OOPS! pitfall code.
    severity : Severity
        OOPS! importance level.
    scale : Scale
        Interpretation of the score.
    description : str
        One-line summary.
    **flags
        ``requires_network``, ``requires_abox`` or ``requires_questions``.

    Returns
    -------
    MetricDescriptor
        The descriptor.
    """
    return MetricDescriptor(
        metric_id=metric_id, name=name, function=function, category=category,
        source_framework=SourceFramework.OOPS, source_id=source_id,
        source_url=_CATALOGUE, severity=severity, scale=scale,
        higher_is_better=(scale == Scale.BOOLEAN), description=description,
        **flags,
    )


_AXIOM_DESCRIPTORS = [
    _d("oopsP05WrongInverse", "Wrong inverse relationships",
       oops_p05_wrong_inverse_v_0_0_1, Category.STRUCTURAL, "P05",
       Severity.CRITICAL, Scale.COUNT,
       "owl:inverseOf pairs whose domains and ranges do not mirror."),
    _d("oopsP09MissingDomainInfo", "Missing domain information",
       oops_p09_missing_domain_information_v_0_0_1, Category.TASK_BASED, "P09",
       Severity.MINOR, Scale.COUNT,
       "Terms required by the competency questions but not defined.",
       requires_questions=True),
    _d("oopsP14MisusedAllValuesFrom", "Misused owl:allValuesFrom",
       oops_p14_misused_allvaluesfrom_v_0_0_1, Category.STRUCTURAL, "P14",
       Severity.CRITICAL, Scale.COUNT,
       "Universal restrictions without an existential counterpart."),
    _d("oopsP15SomeNot", "'Some not' instead of 'not some'",
       oops_p15_some_not_v_0_0_1, Category.STRUCTURAL, "P15",
       Severity.CRITICAL, Scale.COUNT,
       "Existential restrictions over a complement class."),
    _d("oopsP16PrimitiveNotDefined", "Primitive instead of defined class",
       oops_p16_primitive_instead_of_defined_v_0_0_1, Category.STRUCTURAL,
       "P16", Severity.CRITICAL, Scale.COUNT,
       "Primitive classes whose conditions other classes already meet."),
    _d("oopsP17OverspecializedHierarchy", "Overspecialized hierarchy",
       oops_p17_overspecialized_hierarchy_v_0_0_1, Category.STRUCTURAL, "P17",
       Severity.IMPORTANT, Scale.COUNT,
       "Leaf classes with no instances in the data.", requires_abox=True),
    _d("oopsP18OverspecializedDomainRange", "Overspecialized domain or range",
       oops_p18_overspecialized_domain_range_v_0_0_1, Category.STRUCTURAL,
       "P18", Severity.IMPORTANT, Scale.COUNT,
       "Properties used outside their declared domain or range."),
    _d("oopsP27WrongEquivProperty", "Wrong equivalent properties",
       oops_p27_wrong_equivalent_properties_v_0_0_1, Category.STRUCTURAL,
       "P27", Severity.CRITICAL, Scale.COUNT,
       "owl:equivalentProperty between incompatible properties."),
    _d("oopsP28WrongSymmetric", "Wrong symmetric relationships",
       oops_p28_wrong_symmetric_v_0_0_1, Category.STRUCTURAL, "P28",
       Severity.CRITICAL, Scale.COUNT,
       "Symmetric properties whose domain differs from their range."),
    _d("oopsP29WrongTransitive", "Wrong transitive relationships",
       oops_p29_wrong_transitive_v_0_0_1, Category.STRUCTURAL, "P29",
       Severity.CRITICAL, Scale.COUNT,
       "Transitive properties that cannot chain or break OWL 2 DL rules."),
    _d("oopsP31WrongEquivClass", "Wrong equivalent classes",
       oops_p31_wrong_equivalent_classes_v_0_0_1, Category.STRUCTURAL, "P31",
       Severity.CRITICAL, Scale.COUNT,
       "Equivalences that contradict disjointness or collapse classes."),
    _d("oopsP37NotOnWeb", "Ontology not available on the Web",
       oops_p37_not_available_on_web_v_0_0_1, Category.ACCESSIBILITY, "P37",
       Severity.CRITICAL, Scale.BOOLEAN,
       "Ontology URI serves both RDF code and HTML documentation.",
       requires_network=True),
]

for _descriptor in _AXIOM_DESCRIPTORS:
    register_metric(_descriptor)