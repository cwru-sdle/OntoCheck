"""
OOPS!-derived structural pitfall checks (Tier 1).

Implements the fifteen OOPS! pitfalls that are computable from the ontology
graph alone -- no network access, no instance data and no DL reasoner.  Each
function returns a :class:`~ontocheck.metric_registry.MetricResult`.

Pitfalls implemented here
-------------------------
======  ==========================================  ==========
Code    Pitfall                                     Importance
======  ==========================================  ==========
P06     Including cycles in a class hierarchy       critical
P10     Missing disjointness                        important
P13     Inverse relationships not explicitly
        declared                                    minor
P19     Defining multiple domains or ranges in
        properties                                  critical
P21     Using a miscellaneous class                 minor
P24     Using recursive definitions                 important
P25     Defining a relationship as inverse to
        itself                                      important
P26     Defining inverse relationships for a
        symmetric property                          important
P33     Creating a property chain with just one
        property                                    minor
P34     Untyped class                               important
P35     Untyped property                            important
P36     URI contains file extension                 minor
P38     No OWL ontology declaration                 important
P39     Ambiguous namespace                         critical
P40     Namespace hijacking                         critical
======  ==========================================  ==========

Pitfalls implemented elsewhere
------------------------------
The remaining 26 pitfalls are in :mod:`ontocheck.oops_lexical_checks`
(P01, P02, P03, P04, P07, P08, P11, P12, P20, P22, P23, P30, P32, P41) and
:mod:`ontocheck.oops_axiom_checks` (P05, P09, P14, P15, P16, P17, P18, P27,
P28, P29, P31, P37), so that all 41 OOPS! pitfalls are covered.

Source
------
OOPS! Pitfall Catalogue -- https://oops.linkeddata.es/catalogue.jsp

Poveda-Villalon, M., Gomez-Perez, A., & Suarez-Figueroa, M. C. (2014).
OOPS! (OntOlogy Pitfall Scanner!): An on-line tool for ontology evaluation.
*International Journal on Semantic Web and Information Systems*, 10(2), 7-34.

Version: 0.0.1

.. note::

   Claude AI (Opus 5) was employed chiefly to support documentation efforts.
"""

import logging
import re

import networkx as nx
from rdflib import BNode, Graph, OWL, RDF, RDFS, URIRef

from .helpers.oops_helpers import (
    _direct_parents,
    _definitions_of,
    _disjoint_pairs,
    _is_foundational,
    _load_graph,
    _local_name,
    _named_classes,
    _named_properties,
    _namespace_of,
    _ontology_iri,
    _own_namespace,
    _parse_rdf_list,
    _split_identifier,
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

_CATALOGUE = "https://oops.linkeddata.es/catalogue.jsp"


# ---------------------------------------------------------------------------
# P06 -- Including cycles in a class hierarchy
# ---------------------------------------------------------------------------

def oops_p06_cycle_check_v_0_0_1(ttl_file):
    """
    OOPS! P06 -- Including cycles in a class hierarchy.

    Detect cycles in the ``rdfs:subClassOf`` graph, in which a class is
    reachable from itself through a chain of subsumption assertions.

    Definitions
    -----------
    - Subsumption graph: the directed graph whose nodes are named classes and
      whose edges run from a class to each of its named direct superclasses.

    - Cycle: a directed path from a class back to itself.  A cycle makes every
      class on it equivalent under standard OWL semantics, which is almost
      never the modeller's intention.

    - Self-loop: the degenerate one-node cycle ``C rdfs:subClassOf C``,
      reported alongside longer cycles.

    Source
    ------
    OOPS! P06 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of distinct classes lying on at least one
        cycle; ``passed`` is ``True`` when that count is zero.  ``affected``
        lists those classes and ``detail["cycles"]`` gives each cycle as an
        ordered list of URIs.

    Output Information
    ------------------
    - Number of cycles found and the classes participating in each
    - Total number of named classes examined

    Error Handling
    --------------
    - FileNotFoundError and Turtle parse errors are logged, and a
      ``MetricResult`` with ``status`` beginning ``"Error:"`` is returned.

    Notes
    -----
    Only named superclasses are followed.  Anonymous superclasses
    (restrictions, Boolean class expressions) cannot close a cycle on their
    own and are skipped.

    Examples
    --------
    >>> result = oops_p06_cycle_check_v_0_0_1("ontology.ttl")   # doctest: +SKIP
    >>> result.passed                                           # doctest: +SKIP
    True
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP06Cycles",
            status="Error: could not load ontology",
        )

    classes = _named_classes(g)
    parents = _direct_parents(g)

    graph = nx.DiGraph()
    graph.add_nodes_from(str(c) for c in classes)
    for child, parent_set in parents.items():
        for parent in parent_set:
            graph.add_edge(str(child), str(parent))

    cycles = [c for c in nx.simple_cycles(graph)]
    on_cycle = sorted({node for cycle in cycles for node in cycle})

    logger.info(f"--- OOPS! P06: cycles in class hierarchy ---")
    logger.info(f"Named classes examined: {len(classes)}")
    if cycles:
        logger.info(f"Cycles detected: {len(cycles)}")
        for cycle in cycles:
            logger.info("  " + " -> ".join(cycle + [cycle[0]]))
    else:
        logger.info("No subsumption cycles detected.")

    return MetricResult(
        metric_id="oopsP06Cycles",
        score=len(on_cycle),
        passed=not on_cycle,
        affected=on_cycle,
        total_examined=len(classes),
        detail={"cycles": cycles, "cycle_count": len(cycles)},
        message=(
            f"{len(cycles)} subsumption cycle(s) involving "
            f"{len(on_cycle)} class(es)"
            if cycles else "No subsumption cycles detected"
        ),
    )


# ---------------------------------------------------------------------------
# P10 -- Missing disjointness
# ---------------------------------------------------------------------------

def oops_p10_disjointness_check_v_0_0_1(ttl_file):
    """
    OOPS! P10 -- Missing disjointness.

    Identify sibling classes that are not asserted to be pairwise disjoint.
    Without such assertions a reasoner may infer unintended common instances.

    Definitions
    -----------
    - Siblings: two or more named classes sharing at least one named direct
      superclass.

    - Asserted disjointness: a pair appearing either in an ``owl:disjointWith``
      statement or together in the member list of an
      ``owl:AllDisjointClasses`` axiom.

    - Sibling group: the set of children of a single parent.  A group is
      reported when at least one of its pairs lacks a disjointness assertion.

    Source
    ------
    OOPS! P10 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of sibling pairs lacking a disjointness
        assertion.  ``detail["coverage"]`` gives the proportion of sibling
        pairs that are covered, and ``detail["worst_parents"]`` lists the ten
        parents with the most uncovered pairs.

    Notes
    -----
    Disjointness is not always appropriate -- siblings may legitimately
    overlap -- so this check reports coverage rather than asserting a defect.
    OOPS! takes the same position, classifying P10 as important rather than
    critical.

    Both the binary and n-ary forms are recognised.  Ontologies that express
    disjointness exclusively through ``owl:AllDisjointClasses`` would
    otherwise appear to have none at all.

    Examples
    --------
    >>> result = oops_p10_disjointness_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    >>> result.detail["coverage"]                                     # doctest: +SKIP
    0.43
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP10Disjointness",
            status="Error: could not load ontology",
        )

    parents = _direct_parents(g)
    asserted = _disjoint_pairs(g)

    children_of = {}
    for child, parent_set in parents.items():
        for parent in parent_set:
            children_of.setdefault(parent, set()).add(child)

    total_pairs = 0
    uncovered = []
    per_parent = {}

    for parent, children in children_of.items():
        kids = sorted(children, key=str)
        if len(kids) < 2:
            continue
        missing_here = 0
        for i, a in enumerate(kids):
            for b in kids[i + 1:]:
                total_pairs += 1
                if frozenset((a, b)) not in asserted:
                    uncovered.append(f"{a} | {b}")
                    missing_here += 1
        if missing_here:
            per_parent[str(parent)] = missing_here

    covered = total_pairs - len(uncovered)
    coverage = (covered / total_pairs) if total_pairs else 1.0
    worst = sorted(per_parent.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

    logger.info("--- OOPS! P10: missing disjointness ---")
    logger.info(f"Sibling pairs examined: {total_pairs}")
    logger.info(f"Pairs with asserted disjointness: {covered}")
    logger.info(f"Disjointness coverage: {coverage:.2%}")
    if worst:
        logger.info("Parents with the most uncovered sibling pairs:")
        for parent, count in worst:
            logger.info(f"  {parent}: {count}")

    return MetricResult(
        metric_id="oopsP10Disjointness",
        score=len(uncovered),
        passed=not uncovered,
        affected=uncovered,
        total_examined=total_pairs,
        detail={
            "coverage": round(coverage, 4),
            "covered_pairs": covered,
            "worst_parents": worst,
        },
        message=(
            f"{len(uncovered)} of {total_pairs} sibling pairs lack a "
            f"disjointness assertion ({coverage:.1%} covered)"
        ),
    )


# ---------------------------------------------------------------------------
# P13 -- Inverse relationships not explicitly declared
# ---------------------------------------------------------------------------

def oops_p13_undeclared_inverse_check_v_0_0_1(ttl_file):
    """
    OOPS! P13 -- Inverse relationships not explicitly declared.

    Identify pairs of object properties whose domain and range are mirror
    images of one another but between which no ``owl:inverseOf`` assertion
    exists.  Such pairs are candidate undeclared inverses.

    Definitions
    -----------
    - Mirrored pair: object properties *p* and *q*, distinct, where
      ``domain(p) == range(q)`` and ``range(p) == domain(q)``, with all four
      declarations present and non-empty.

    - Declared inverse: an ``owl:inverseOf`` assertion between the pair in
      either direction.

    Source
    ------
    OOPS! P13 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of candidate pairs; ``affected`` lists them as
        ``"p | q"`` strings.

    Notes
    -----
    This is a heuristic, and deliberately so: mirrored domain and range do not
    entail inversehood.  Two properties may legitimately share that shape
    without being inverses -- ``precedes`` and ``inhibits`` over the same
    process class, for instance.  Results are candidates for review, not
    defects.  OOPS! classifies P13 as minor for the same reason.

    Properties whose domain or range is an anonymous class expression are
    skipped, since structural equality of blank nodes is not meaningful here.

    Examples
    --------
    >>> result = oops_p13_undeclared_inverse_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP13UndeclaredInverse",
            status="Error: could not load ontology",
        )

    object_properties = {
        s for s in g.subjects(RDF.type, OWL.ObjectProperty)
        if isinstance(s, URIRef)
    }

    declared = set()
    for s, o in g.subject_objects(OWL.inverseOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            declared.add(frozenset((s, o)))

    signature = {}
    for p in object_properties:
        domains = {d for d in g.objects(p, RDFS.domain) if isinstance(d, URIRef)}
        ranges = {r for r in g.objects(p, RDFS.range) if isinstance(r, URIRef)}
        if domains and ranges:
            signature[p] = (frozenset(domains), frozenset(ranges))

    props = sorted(signature, key=str)
    candidates = []
    for i, p in enumerate(props):
        dom_p, ran_p = signature[p]
        for q in props[i + 1:]:
            dom_q, ran_q = signature[q]
            if dom_p == ran_q and ran_p == dom_q:
                if frozenset((p, q)) not in declared:
                    candidates.append(f"{p} | {q}")

    logger.info("--- OOPS! P13: inverse relationships not declared ---")
    logger.info(f"Object properties with declared domain and range: {len(signature)}")
    logger.info(f"Declared owl:inverseOf pairs: {len(declared)}")
    logger.info(f"Candidate undeclared inverse pairs: {len(candidates)}")
    for pair in candidates:
        logger.info(f"  {pair}")

    return MetricResult(
        metric_id="oopsP13UndeclaredInverse",
        score=len(candidates),
        passed=not candidates,
        affected=candidates,
        total_examined=len(signature),
        detail={"declared_inverse_pairs": len(declared)},
        message=(
            f"{len(candidates)} candidate undeclared inverse pair(s) "
            f"among {len(signature)} typed object properties"
        ),
    )


# ---------------------------------------------------------------------------
# P19 -- Defining multiple domains or ranges in properties
# ---------------------------------------------------------------------------

def oops_p19_multiple_domain_range_check_v_0_0_1(ttl_file):
    """
    OOPS! P19 -- Defining multiple domains or ranges in properties.

    Identify properties carrying more than one ``rdfs:domain`` or more than one
    ``rdfs:range`` statement.

    Definitions
    -----------
    - Multiple domain: two or more distinct ``rdfs:domain`` objects on a single
      property.  In OWL this is read as the *intersection* of those classes,
      not the union, so an instance must belong to all of them.  Modellers
      almost always intend the union, which must be written explicitly as an
      ``owl:unionOf`` class expression.

    - Multiple range: the same situation for ``rdfs:range``.

    Source
    ------
    OOPS! P19 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of properties with a multiple domain or a
        multiple range.  ``detail`` separates the two counts.

    Notes
    -----
    A single ``rdfs:domain`` whose object is an anonymous ``owl:unionOf``
    expression is the correct pattern and is not flagged.

    Examples
    --------
    >>> result = oops_p19_multiple_domain_range_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP19MultipleDomainRange",
            status="Error: could not load ontology",
        )

    properties = _named_properties(g)
    multi_domain, multi_range = [], []

    for p in sorted(properties, key=str):
        domains = list(g.objects(p, RDFS.domain))
        ranges = list(g.objects(p, RDFS.range))
        if len(set(domains)) > 1:
            multi_domain.append(str(p))
        if len(set(ranges)) > 1:
            multi_range.append(str(p))

    affected = sorted(set(multi_domain) | set(multi_range))

    logger.info("--- OOPS! P19: multiple domains or ranges ---")
    logger.info(f"Named properties examined: {len(properties)}")
    logger.info(f"Properties with multiple rdfs:domain: {len(multi_domain)}")
    logger.info(f"Properties with multiple rdfs:range: {len(multi_range)}")
    for p in affected:
        logger.info(f"  {p}")

    return MetricResult(
        metric_id="oopsP19MultipleDomainRange",
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=len(properties),
        detail={
            "multiple_domain": multi_domain,
            "multiple_range": multi_range,
        },
        message=(
            f"{len(affected)} propert(ies) declare multiple domains or ranges"
        ),
    )


# ---------------------------------------------------------------------------
# P21 -- Using a miscellaneous class
# ---------------------------------------------------------------------------

_MISC_PATTERNS = (
    r"^other$", r"^others$", r"^misc$", r"^miscellaneous$",
    r"^unclassified$", r"^unknown$", r"^undefined$", r"^unspecified$",
    r"^various$", r"^not[_ ]?applicable$", r"^n/?a$", r"^none$",
    r"^rest$", r"^remainder$", r"^etc$",
)


def oops_p21_miscellaneous_class_check_v_0_0_1(ttl_file):
    """
    OOPS! P21 -- Using a miscellaneous class.

    Identify classes that appear to be catch-alls for instances the modeller
    did not classify, such as ``Other``, ``Miscellaneous`` or ``Unknown``.

    Definitions
    -----------
    - Miscellaneous class: a class whose local name or ``rdfs:label``, after
      normalisation, matches one of a set of catch-all patterns.

    - Normalisation: CamelCase and snake_case identifiers are split into
      words, lowercased and rejoined with single spaces before matching.

    Source
    ------
    OOPS! P21 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of classes matching a catch-all pattern.

    Notes
    -----
    Purely lexical, so it will not detect a catch-all with a domain-specific
    name, and it may flag a legitimate class that happens to be named
    ``Other``.  The patterns are deliberately anchored to the whole
    normalised name to keep false positives low -- ``OtherwiseQualified``
    does not match, ``Other`` does.

    Examples
    --------
    >>> result = oops_p21_miscellaneous_class_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP21MiscellaneousClass",
            status="Error: could not load ontology",
        )

    compiled = [re.compile(p, re.IGNORECASE) for p in _MISC_PATTERNS]
    classes = _named_classes(g)
    flagged = []

    for c in sorted(classes, key=str):
        names = [" ".join(_split_identifier(_local_name(c)))]
        names.extend(str(lbl).strip().lower() for lbl in g.objects(c, RDFS.label))
        if any(rx.match(n) for n in names if n for rx in compiled):
            flagged.append(str(c))

    logger.info("--- OOPS! P21: miscellaneous class ---")
    logger.info(f"Named classes examined: {len(classes)}")
    logger.info(f"Catch-all classes detected: {len(flagged)}")
    for c in flagged:
        logger.info(f"  {c}")

    return MetricResult(
        metric_id="oopsP21MiscellaneousClass",
        score=len(flagged),
        passed=not flagged,
        affected=flagged,
        total_examined=len(classes),
        message=f"{len(flagged)} catch-all class(es) detected",
    )


# ---------------------------------------------------------------------------
# P24 -- Using recursive definitions
# ---------------------------------------------------------------------------

def oops_p24_recursive_definition_check_v_0_0_1(ttl_file, min_word_length=4):
    """
    OOPS! P24 -- Using recursive definitions.

    Identify terms whose own name appears inside their textual definition,
    which leaves the definition circular and uninformative.

    Definitions
    -----------
    - Recursive definition: the term's identifier, split into words, occurs as
      a contiguous word sequence within one of its definition strings.

    - Definition: the object of ``skos:definition``, ``rdfs:comment``,
      ``obo:IAO_0000115`` or a Dublin Core ``description``.

    - Significant word: a word of at least *min_word_length* characters.
      Terms whose entire identifier consists of shorter words are skipped, as
      matching on them produces noise.

    Source
    ------
    OOPS! P24 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    min_word_length : int, optional
        Minimum length for a word to be considered significant.  Default 4.

    Returns
    -------
    MetricResult
        ``score`` is the number of terms with a recursive definition;
        ``detail["examples"]`` holds up to ten term/definition pairs.

    Notes
    -----
    Scientific vocabularies produce a measurable false-positive rate here,
    because a genus-differentia definition legitimately repeats the genus:
    "Lattice Parameter -- the lattice parameter of a unit cell" is circular,
    but "Alpha Lath Width -- the in-plane width of individual alpha-phase
    laths" repeats "width" without being circular.  Matching the full
    identifier as a contiguous phrase, rather than any single shared word,
    keeps that rate low.

    Examples
    --------
    >>> result = oops_p24_recursive_definition_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP24RecursiveDefinition",
            status="Error: could not load ontology",
        )

    terms = _named_classes(g) | _named_properties(g)
    flagged, examples, examined = [], [], 0

    for term in sorted(terms, key=str):
        definitions = _definitions_of(g, term)
        if not definitions:
            continue
        examined += 1

        words = _split_identifier(_local_name(term))
        if not any(len(w) >= min_word_length for w in words):
            continue
        phrase = r"\s+".join(re.escape(w) for w in words)
        pattern = re.compile(rf"\b{phrase}\b", re.IGNORECASE)

        for definition in definitions:
            if pattern.search(definition):
                flagged.append(str(term))
                if len(examples) < 10:
                    snippet = definition[:160]
                    examples.append({"term": str(term), "definition": snippet})
                break

    logger.info("--- OOPS! P24: recursive definitions ---")
    logger.info(f"Terms carrying a definition: {examined}")
    logger.info(f"Recursive definitions detected: {len(flagged)}")
    for ex in examples:
        logger.info(f"  {ex['term']}: {ex['definition']}")

    return MetricResult(
        metric_id="oopsP24RecursiveDefinition",
        score=len(flagged),
        passed=not flagged,
        affected=flagged,
        total_examined=examined,
        detail={"examples": examples, "min_word_length": min_word_length},
        message=(
            f"{len(flagged)} of {examined} defined term(s) restate their own "
            f"name in their definition"
        ),
    )


# ---------------------------------------------------------------------------
# P25 -- Defining a relationship as inverse to itself
# ---------------------------------------------------------------------------

def oops_p25_self_inverse_check_v_0_0_1(ttl_file):
    """
    OOPS! P25 -- Defining a relationship as inverse to itself.

    Identify properties asserted to be their own inverse via
    ``?p owl:inverseOf ?p``.

    Definitions
    -----------
    - Self-inverse assertion: an ``owl:inverseOf`` triple whose subject and
      object are the same resource.  The modeller almost always intends
      ``owl:SymmetricProperty``, which is what a self-inverse assertion
      entails but states far less clearly.

    Source
    ------
    OOPS! P25 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of self-inverse properties.
        ``detail["already_symmetric"]`` lists those that are additionally
        typed ``owl:SymmetricProperty``, where the assertion is redundant
        rather than merely unclear.

    Examples
    --------
    >>> result = oops_p25_self_inverse_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP25SelfInverse",
            status="Error: could not load ontology",
        )

    symmetric = {
        s for s in g.subjects(RDF.type, OWL.SymmetricProperty)
        if isinstance(s, URIRef)
    }

    flagged, already_symmetric = [], []
    total_inverse = 0
    for s, o in g.subject_objects(OWL.inverseOf):
        total_inverse += 1
        if isinstance(s, URIRef) and s == o:
            flagged.append(str(s))
            if s in symmetric:
                already_symmetric.append(str(s))

    flagged = sorted(set(flagged))

    logger.info("--- OOPS! P25: relationship inverse to itself ---")
    logger.info(f"owl:inverseOf assertions examined: {total_inverse}")
    logger.info(f"Self-inverse properties detected: {len(flagged)}")
    for p in flagged:
        logger.info(f"  {p}")

    return MetricResult(
        metric_id="oopsP25SelfInverse",
        score=len(flagged),
        passed=not flagged,
        affected=flagged,
        total_examined=total_inverse,
        detail={"already_symmetric": sorted(set(already_symmetric))},
        message=f"{len(flagged)} propert(ies) declared inverse to themselves",
    )


# ---------------------------------------------------------------------------
# P26 -- Defining inverse relationships for a symmetric property
# ---------------------------------------------------------------------------

def oops_p26_symmetric_with_inverse_check_v_0_0_1(ttl_file):
    """
    OOPS! P26 -- Defining inverse relationships for a symmetric property.

    Identify properties typed ``owl:SymmetricProperty`` that also carry an
    ``owl:inverseOf`` assertion to a different property.

    Definitions
    -----------
    - Symmetric property: a property declared ``owl:SymmetricProperty``, which
      already entails that it is its own inverse.

    - Conflicting inverse: an ``owl:inverseOf`` assertion between a symmetric
      property and a *different* property, which forces the two to be
      equivalent.  This is usually a modelling error: either the property is
      not truly symmetric, or the inverse declaration is spurious.

    Source
    ------
    OOPS! P26 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of symmetric properties carrying a conflicting
        inverse; ``affected`` lists them as ``"p inverseOf q"`` strings.

    Notes
    -----
    Self-inverse assertions on a symmetric property are redundant but not
    contradictory, and are reported by P25 rather than here.

    Examples
    --------
    >>> result = oops_p26_symmetric_with_inverse_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP26SymmetricWithInverse",
            status="Error: could not load ontology",
        )

    symmetric = {
        s for s in g.subjects(RDF.type, OWL.SymmetricProperty)
        if isinstance(s, URIRef)
    }

    flagged = []
    for p in sorted(symmetric, key=str):
        for o in g.objects(p, OWL.inverseOf):
            if isinstance(o, URIRef) and o != p:
                flagged.append(f"{p} inverseOf {o}")
        for s in g.subjects(OWL.inverseOf, p):
            if isinstance(s, URIRef) and s != p:
                flagged.append(f"{s} inverseOf {p}")

    flagged = sorted(set(flagged))

    logger.info("--- OOPS! P26: inverse declared for symmetric property ---")
    logger.info(f"Symmetric properties examined: {len(symmetric)}")
    logger.info(f"Conflicting inverse declarations: {len(flagged)}")
    for entry in flagged:
        logger.info(f"  {entry}")

    return MetricResult(
        metric_id="oopsP26SymmetricWithInverse",
        score=len(flagged),
        passed=not flagged,
        affected=flagged,
        total_examined=len(symmetric),
        message=(
            f"{len(flagged)} inverse declaration(s) on symmetric properties"
        ),
    )


# ---------------------------------------------------------------------------
# P33 -- Creating a property chain with just one property
# ---------------------------------------------------------------------------

def oops_p33_single_property_chain_check_v_0_0_1(ttl_file):
    """
    OOPS! P33 -- Creating a property chain with just one property.

    Identify ``owl:propertyChainAxiom`` declarations whose RDF collection
    contains fewer than two members.

    Definitions
    -----------
    - Property chain: an ``owl:propertyChainAxiom`` whose object is an RDF
      collection of properties whose composition implies the subject property.

    - Degenerate chain: a chain of length one, which states only that the
      subject is a super-property of the single member.  That is expressed
      correctly with ``rdfs:subPropertyOf``.  A chain of length zero is
      malformed.

    Source
    ------
    OOPS! P33 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of degenerate chains; ``detail["lengths"]``
        maps each affected property to its chain length.

    Examples
    --------
    >>> result = oops_p33_single_property_chain_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP33SinglePropertyChain",
            status="Error: could not load ontology",
        )

    flagged, lengths, total = [], {}, 0
    for s, o in g.subject_objects(OWL.propertyChainAxiom):
        total += 1
        members = _parse_rdf_list(g, o)
        if len(members) < 2:
            flagged.append(str(s))
            lengths[str(s)] = len(members)

    flagged = sorted(set(flagged))

    logger.info("--- OOPS! P33: property chain with one property ---")
    logger.info(f"Property chain axioms examined: {total}")
    logger.info(f"Degenerate chains detected: {len(flagged)}")
    for p in flagged:
        logger.info(f"  {p} (chain length {lengths[p]})")

    return MetricResult(
        metric_id="oopsP33SinglePropertyChain",
        score=len(flagged),
        passed=not flagged,
        affected=flagged,
        total_examined=total,
        detail={"lengths": lengths},
        message=f"{len(flagged)} degenerate property chain(s)",
    )


# ---------------------------------------------------------------------------
# P34 -- Untyped class
# ---------------------------------------------------------------------------

def oops_p34_untyped_class_check_v_0_0_1(ttl_file):
    """
    OOPS! P34 -- Untyped class.

    Identify resources used in a class position that are never declared
    ``owl:Class`` or ``rdfs:Class``.

    Definitions
    -----------
    - Class position: object of ``rdf:type``, either side of
      ``rdfs:subClassOf``, object of ``rdfs:domain`` or ``rdfs:range``, object
      of ``owl:someValuesFrom``, ``owl:allValuesFrom``, ``owl:onClass`` or
      ``owl:equivalentClass``, or a member of an ``owl:AllDisjointClasses``
      axiom.

    - Untyped: used in a class position but carrying no
      ``rdf:type owl:Class`` or ``rdf:type rdfs:Class`` assertion anywhere in
      the graph.

    - Local versus imported: an untyped class in the ontology's own namespace
      is a defect the maintainer can fix.  One in an external namespace is
      usually a term referenced from an ontology that is not being loaded, so
      the two are counted separately.

    Source
    ------
    OOPS! P34 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of untyped classes in the ontology's own
        namespace.  ``detail["external_untyped"]`` lists those in other
        namespaces, and ``detail["own_namespace"]`` records the namespace
        used to draw the distinction.

    Notes
    -----
    Scoring only the local namespace keeps the metric actionable.  Merged
    cross-domain assessments reference large numbers of CCO and BFO terms
    without importing their definitions, and counting those as defects would
    swamp the genuine findings.

    This check also catches malformed identifiers.  A superclass written as
    ``obo:0000023`` rather than ``obo:BFO_0000023`` resolves to a URI that is
    never declared anywhere, so it surfaces here as an untyped class.

    Examples
    --------
    >>> result = oops_p34_untyped_class_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP34UntypedClass",
            status="Error: could not load ontology",
        )

    declared = {
        s for t in (OWL.Class, RDFS.Class)
        for s in g.subjects(RDF.type, t)
        if isinstance(s, URIRef)
    }

    used = set()
    for o in g.objects(None, RDF.type):
        if isinstance(o, URIRef) and o not in (
            OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
            OWL.AnnotationProperty, OWL.Ontology, OWL.Restriction,
            OWL.AllDisjointClasses, OWL.NamedIndividual, RDF.Property,
            OWL.SymmetricProperty, OWL.TransitiveProperty,
            OWL.FunctionalProperty, OWL.InverseFunctionalProperty,
            RDFS.Datatype,
        ):
            used.add(o)

    for pred in (RDFS.subClassOf, RDFS.domain, RDFS.range,
                 OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass,
                 OWL.equivalentClass, OWL.disjointWith):
        for s, o in g.subject_objects(pred):
            if pred == RDFS.subClassOf and isinstance(s, URIRef):
                used.add(s)
            if isinstance(o, URIRef):
                used.add(o)

    for axiom in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members_node = g.value(axiom, OWL.members)
        if members_node is not None:
            for m in _parse_rdf_list(g, members_node):
                if isinstance(m, URIRef):
                    used.add(m)

    untyped = {
        u for u in used
        if u not in declared and not _is_foundational(u)
    }

    own_ns = _own_namespace(g)
    local_untyped, external_untyped = [], []
    for u in sorted(untyped, key=str):
        if own_ns and str(u).startswith(own_ns):
            local_untyped.append(str(u))
        else:
            external_untyped.append(str(u))

    logger.info("--- OOPS! P34: untyped class ---")
    logger.info(f"Own namespace: {own_ns}")
    logger.info(f"Declared classes: {len(declared)}")
    logger.info(f"Resources used in a class position: {len(used)}")
    logger.info(f"Untyped in own namespace: {len(local_untyped)}")
    for u in local_untyped:
        logger.info(f"  {u}")
    logger.info(f"Untyped in external namespaces: {len(external_untyped)}")

    return MetricResult(
        metric_id="oopsP34UntypedClass",
        score=len(local_untyped),
        passed=not local_untyped,
        affected=local_untyped,
        total_examined=len(used),
        detail={
            "external_untyped": external_untyped,
            "external_untyped_count": len(external_untyped),
            "own_namespace": own_ns,
            "declared_classes": len(declared),
        },
        message=(
            f"{len(local_untyped)} untyped class(es) in the ontology's own "
            f"namespace, {len(external_untyped)} in external namespaces"
        ),
    )


# ---------------------------------------------------------------------------
# P35 -- Untyped property
# ---------------------------------------------------------------------------

def oops_p35_untyped_property_check_v_0_0_1(ttl_file):
    """
    OOPS! P35 -- Untyped property.

    Identify resources used in a property position that are never declared
    ``owl:ObjectProperty``, ``owl:DatatypeProperty``,
    ``owl:AnnotationProperty`` or ``rdf:Property``.

    Definitions
    -----------
    - Property position: appearing as the predicate of a triple, or as the
      object of ``owl:onProperty``, ``rdfs:subPropertyOf``,
      ``owl:inverseOf``, ``owl:equivalentProperty`` or
      ``owl:propertyDisjointWith``.

    - Untyped: used in a property position with no type assertion of any of
      the four property kinds.

    - Local versus imported: as for P34, untyped properties in the ontology's
      own namespace are scored, and those in external namespaces are reported
      separately.

    Source
    ------
    OOPS! P35 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of untyped properties in the ontology's own
        namespace; ``detail["external_untyped"]`` lists the remainder.

    Notes
    -----
    Predicates belonging to foundational vocabularies (RDF, RDFS, OWL, SKOS,
    Dublin Core, QUDT, PROV) are excluded, since a domain ontology is not
    expected to re-declare them.

    Examples
    --------
    >>> result = oops_p35_untyped_property_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP35UntypedProperty",
            status="Error: could not load ontology",
        )

    declared = _named_properties(g)

    used = set()
    for _, p, _ in g:
        if isinstance(p, URIRef):
            used.add(p)
    for pred in (OWL.onProperty, RDFS.subPropertyOf, OWL.inverseOf,
                 OWL.equivalentProperty, OWL.propertyDisjointWith):
        for s, o in g.subject_objects(pred):
            if isinstance(o, URIRef):
                used.add(o)
            if pred != OWL.onProperty and isinstance(s, URIRef):
                used.add(s)

    untyped = {
        u for u in used
        if u not in declared and not _is_foundational(u)
    }

    own_ns = _own_namespace(g)
    local_untyped, external_untyped = [], []
    for u in sorted(untyped, key=str):
        if own_ns and str(u).startswith(own_ns):
            local_untyped.append(str(u))
        else:
            external_untyped.append(str(u))

    logger.info("--- OOPS! P35: untyped property ---")
    logger.info(f"Declared properties: {len(declared)}")
    logger.info(f"Resources used in a property position: {len(used)}")
    logger.info(f"Untyped in own namespace: {len(local_untyped)}")
    for u in local_untyped:
        logger.info(f"  {u}")
    logger.info(f"Untyped in external namespaces: {len(external_untyped)}")

    return MetricResult(
        metric_id="oopsP35UntypedProperty",
        score=len(local_untyped),
        passed=not local_untyped,
        affected=local_untyped,
        total_examined=len(used),
        detail={
            "external_untyped": external_untyped,
            "external_untyped_count": len(external_untyped),
            "own_namespace": own_ns,
            "declared_properties": len(declared),
        },
        message=(
            f"{len(local_untyped)} untyped propert(ies) in the ontology's own "
            f"namespace, {len(external_untyped)} in external namespaces"
        ),
    )


# ---------------------------------------------------------------------------
# P36 -- URI contains file extension
# ---------------------------------------------------------------------------

_FILE_EXTENSIONS = (
    ".owl", ".rdf", ".ttl", ".n3", ".nt", ".xml", ".jsonld", ".json",
    ".rdfs", ".trig", ".nq",
)


def oops_p36_uri_file_extension_check_v_0_0_1(ttl_file):
    """
    OOPS! P36 -- URI contains file extension.

    Identify term URIs that embed a serialisation file extension, which binds
    an identifier to one particular representation of the ontology.

    Definitions
    -----------
    - File extension: one of ``.owl``, ``.rdf``, ``.ttl``, ``.n3``, ``.nt``,
      ``.xml``, ``.jsonld``, ``.json``, ``.rdfs``, ``.trig`` or ``.nq``.

    - Term URI: the URI of any named class, property or individual, and the
      ontology IRI itself.

    Source
    ------
    OOPS! P36 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of term URIs containing a file extension;
        ``detail["ontology_iri_affected"]`` records whether the ontology IRI
        itself is among them.

    Notes
    -----
    Matching is on the URI up to any fragment delimiter, so a fragment that
    happens to contain a dotted string is not flagged.

    Examples
    --------
    >>> result = oops_p36_uri_file_extension_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP36UriFileExtension",
            status="Error: could not load ontology",
        )

    terms = _named_classes(g) | _named_properties(g)
    ontology_iri = _ontology_iri(g)
    if ontology_iri is not None:
        terms = terms | {ontology_iri}

    flagged = []
    for t in sorted(terms, key=str):
        head = str(t).split("#", 1)[0].lower()
        if any(ext in head for ext in _FILE_EXTENSIONS):
            flagged.append(str(t))

    iri_affected = (
        ontology_iri is not None and str(ontology_iri) in flagged
    )

    logger.info("--- OOPS! P36: URI contains file extension ---")
    logger.info(f"Term URIs examined: {len(terms)}")
    logger.info(f"URIs containing a file extension: {len(flagged)}")
    if iri_affected:
        logger.info(f"  The ontology IRI itself is affected: {ontology_iri}")

    return MetricResult(
        metric_id="oopsP36UriFileExtension",
        score=len(flagged),
        passed=not flagged,
        affected=flagged,
        total_examined=len(terms),
        detail={
            "ontology_iri_affected": iri_affected,
            "ontology_iri": str(ontology_iri) if ontology_iri else None,
        },
        message=(
            f"{len(flagged)} term URI(s) embed a serialisation file extension"
        ),
    )


# ---------------------------------------------------------------------------
# P38 -- No OWL ontology declaration
# ---------------------------------------------------------------------------

def oops_p38_ontology_declaration_check_v_0_0_1(ttl_file):
    """
    OOPS! P38 -- No OWL ontology declaration.

    Verify that the file declares an ``owl:Ontology``.

    Definitions
    -----------
    - Ontology declaration: a triple ``<iri> rdf:type owl:Ontology``.  Without
      it, tools cannot attach ontology-level metadata -- version, license,
      imports, provenance -- and several FOOPS! FAIR tests have nothing to
      inspect.

    Source
    ------
    OOPS! P38 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is ``True`` when a declaration is present.
        ``detail["declarations"]`` lists every declared ontology IRI, and
        ``detail["anonymous"]`` counts declarations on blank nodes, which
        satisfy the letter of the check but provide no usable identifier.

    Notes
    -----
    This check is a prerequisite for OOPS! P39 and for the FOOPS! metadata,
    license, provenance and version tests, all of which inspect the subject of
    the ontology declaration.

    Examples
    --------
    >>> result = oops_p38_ontology_declaration_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    >>> result.passed                                                         # doctest: +SKIP
    True
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP38OntologyDeclaration",
            status="Error: could not load ontology",
        )

    all_decls = list(g.subjects(RDF.type, OWL.Ontology))
    named = sorted((str(s) for s in all_decls if isinstance(s, URIRef)))
    anonymous = sum(1 for s in all_decls if isinstance(s, BNode))

    present = bool(named)

    logger.info("--- OOPS! P38: OWL ontology declaration ---")
    if present:
        logger.info(f"Ontology declaration(s) found: {len(named)}")
        for iri in named:
            logger.info(f"  {iri}")
    else:
        logger.info("No owl:Ontology declaration found.")
    if anonymous:
        logger.info(f"Anonymous owl:Ontology declarations: {anonymous}")

    return MetricResult(
        metric_id="oopsP38OntologyDeclaration",
        score=present,
        passed=present,
        affected=[] if present else ["<no owl:Ontology declaration>"],
        total_examined=1,
        detail={"declarations": named, "anonymous": anonymous},
        message=(
            f"owl:Ontology declared ({named[0]})" if present
            else "No owl:Ontology declaration present"
        ),
    )


# ---------------------------------------------------------------------------
# P39 -- Ambiguous namespace
# ---------------------------------------------------------------------------

def oops_p39_ambiguous_namespace_check_v_0_0_1(ttl_file):
    """
    OOPS! P39 -- Ambiguous namespace.

    Verify that the ontology establishes an unambiguous base namespace, by
    declaring an ontology IRI or a base URI.

    Definitions
    -----------
    - Ambiguous namespace: neither an ``owl:Ontology`` IRI nor a base URI is
      declared, leaving relative URIs in the file resolvable only against the
      retrieval location.  The same file then mints different identifiers
      depending on where it was fetched from.

    - Base URI: the Turtle ``@base`` directive, corresponding to ``xml:base``
      in RDF/XML.

    Source
    ------
    OOPS! P39 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is ``True`` when the namespace is unambiguous.  ``detail``
        records which of the two mechanisms was found, the empty-prefix
        binding if present, and whether the ontology IRI ends in a URI
        delimiter.

    Notes
    -----
    An ontology IRI that does not end in ``#`` or ``/`` is reported in
    ``detail["iri_lacks_delimiter"]``.  It satisfies P39, but concatenating
    local names onto it produces run-together identifiers, so it is worth
    surfacing.

    Examples
    --------
    >>> result = oops_p39_ambiguous_namespace_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP39AmbiguousNamespace",
            status="Error: could not load ontology",
        )

    ontology_iri = _ontology_iri(g)
    base = getattr(g, "base", None)

    empty_prefix = None
    for prefix, namespace in g.namespaces():
        if prefix == "":
            empty_prefix = str(namespace)
            break

    unambiguous = ontology_iri is not None or base is not None
    iri_lacks_delimiter = (
        ontology_iri is not None and not str(ontology_iri).endswith(("#", "/"))
    )

    logger.info("--- OOPS! P39: ambiguous namespace ---")
    logger.info(f"Ontology IRI: {ontology_iri}")
    logger.info(f"Base URI: {base}")
    logger.info(f"Empty-prefix binding: {empty_prefix}")
    if not unambiguous:
        logger.info("Neither an ontology IRI nor a base URI is declared.")
    if iri_lacks_delimiter:
        logger.info(
            "Ontology IRI does not end in '#' or '/'; concatenated local "
            "names will run together."
        )

    return MetricResult(
        metric_id="oopsP39AmbiguousNamespace",
        score=unambiguous,
        passed=unambiguous,
        affected=[] if unambiguous else ["<no ontology IRI or base URI>"],
        total_examined=1,
        detail={
            "ontology_iri": str(ontology_iri) if ontology_iri else None,
            "base_uri": str(base) if base else None,
            "empty_prefix": empty_prefix,
            "iri_lacks_delimiter": iri_lacks_delimiter,
        },
        message=(
            "Namespace is unambiguous" if unambiguous
            else "Neither an ontology IRI nor a base URI is declared"
        ),
    )


# ---------------------------------------------------------------------------
# P40 -- Namespace hijacking
# ---------------------------------------------------------------------------

_DEFINING_PREDICATES = (
    RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range,
    OWL.equivalentClass, OWL.equivalentProperty, OWL.disjointWith,
    OWL.inverseOf, OWL.propertyChainAxiom,
)


def oops_p40_namespace_hijacking_check_v_0_0_1(ttl_file):
    """
    OOPS! P40 -- Namespace hijacking.

    Identify terms in namespaces the ontology does not own that are given
    defining axioms rather than merely referenced.

    Definitions
    -----------
    - Own namespace: the namespace inferred from the ``owl:Ontology`` IRI, or
      failing that the most frequent namespace among named subjects.

    - Defining axiom: a statement that alters the meaning of a term --
      ``rdfs:subClassOf``, ``rdfs:subPropertyOf``, ``rdfs:domain``,
      ``rdfs:range``, ``owl:equivalentClass``, ``owl:equivalentProperty``,
      ``owl:disjointWith``, ``owl:inverseOf`` or ``owl:propertyChainAxiom``
      asserted *about* a foreign term.

    - Hijacking: asserting such an axiom about a term another party owns.
      Anyone consuming both ontologies inherits the redefinition, which is why
      OOPS! rates this critical.

    - Annotation is not hijacking: adding ``rdfs:label``, ``skos:definition``
      or ``skos:exactMatch`` to a foreign term does not change its logical
      meaning and is not reported.

    Source
    ------
    OOPS! P40 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of foreign terms carrying defining axioms.
        ``detail["by_namespace"]`` breaks the count down per foreign
        namespace, and ``detail["axioms"]`` lists up to fifty offending
        statements.

    Notes
    -----
    Particularly relevant to the cross-domain assessments this package
    supports.  Merging several domain ontologies into one graph makes it easy
    to assert subsumption into an upper-level namespace such as CCO or BFO
    without noticing, and the merged file then silently redefines terms that
    other MDS ontologies also import.

    Terms declared ``owl:Class`` locally but minted in a foreign namespace are
    reported in ``detail["foreign_declarations"]``, which is the stronger form
    of the pitfall.

    Examples
    --------
    >>> result = oops_p40_namespace_hijacking_check_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="oopsP40NamespaceHijacking",
            status="Error: could not load ontology",
        )

    own_ns = _own_namespace(g)
    if own_ns is None:
        return MetricResult(
            metric_id="oopsP40NamespaceHijacking",
            status="Skipped (could not determine the ontology's own namespace)",
            message="Own namespace could not be inferred",
        )

    hijacked, axioms, by_namespace = set(), [], {}

    for pred in _DEFINING_PREDICATES:
        for s, o in g.subject_objects(pred):
            if not isinstance(s, URIRef):
                continue
            if str(s).startswith(own_ns):
                continue
            hijacked.add(str(s))
            ns = _namespace_of(s)
            by_namespace[ns] = by_namespace.get(ns, 0) + 1
            if len(axioms) < 50:
                axioms.append(f"{s} {_local_name(pred)} {o}")

    foreign_declarations = []
    for t in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty):
        for s in g.subjects(RDF.type, t):
            if isinstance(s, URIRef) and not str(s).startswith(own_ns):
                if not _is_foundational(s):
                    foreign_declarations.append(str(s))

    affected = sorted(hijacked)

    logger.info("--- OOPS! P40: namespace hijacking ---")
    logger.info(f"Own namespace: {own_ns}")
    logger.info(f"Foreign terms carrying defining axioms: {len(affected)}")
    for ns, count in sorted(by_namespace.items(), key=lambda kv: -kv[1]):
        logger.info(f"  {ns}: {count} axiom(s)")
    for axiom in axioms[:20]:
        logger.info(f"    {axiom}")

    return MetricResult(
        metric_id="oopsP40NamespaceHijacking",
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=len(set(g.subjects())),
        detail={
            "own_namespace": own_ns,
            "by_namespace": by_namespace,
            "axioms": axioms,
            "foreign_declarations": sorted(set(foreign_declarations)),
            "foreign_declaration_count": len(set(foreign_declarations)),
        },
        message=(
            f"{len(affected)} foreign term(s) carry defining axioms across "
            f"{len(by_namespace)} external namespace(s)"
        ),
    )


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

_OOPS_DESCRIPTORS = [
    MetricDescriptor(
        metric_id="oopsP06Cycles",
        name="Cycles in class hierarchy",
        function=oops_p06_cycle_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P06",
        source_url=_CATALOGUE,
        severity=Severity.CRITICAL,
        scale=Scale.COUNT,
        description="Classes reachable from themselves via rdfs:subClassOf.",
    ),
    MetricDescriptor(
        metric_id="oopsP10Disjointness",
        name="Missing disjointness",
        function=oops_p10_disjointness_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P10",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.COUNT,
        description="Sibling class pairs lacking a disjointness assertion.",
    ),
    MetricDescriptor(
        metric_id="oopsP13UndeclaredInverse",
        name="Inverse relationships not declared",
        function=oops_p13_undeclared_inverse_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P13",
        source_url=_CATALOGUE,
        severity=Severity.MINOR,
        scale=Scale.COUNT,
        description="Object property pairs with mirrored domain and range "
                    "but no owl:inverseOf.",
    ),
    MetricDescriptor(
        metric_id="oopsP19MultipleDomainRange",
        name="Multiple domains or ranges",
        function=oops_p19_multiple_domain_range_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P19",
        source_url=_CATALOGUE,
        severity=Severity.CRITICAL,
        scale=Scale.COUNT,
        description="Properties with more than one rdfs:domain or rdfs:range.",
    ),
    MetricDescriptor(
        metric_id="oopsP21MiscellaneousClass",
        name="Miscellaneous class",
        function=oops_p21_miscellaneous_class_check_v_0_0_1,
        category=Category.NAMING,
        source_framework=SourceFramework.OOPS,
        source_id="P21",
        source_url=_CATALOGUE,
        severity=Severity.MINOR,
        scale=Scale.COUNT,
        description="Catch-all classes such as Other, Misc or Unknown.",
    ),
    MetricDescriptor(
        metric_id="oopsP24RecursiveDefinition",
        name="Recursive definitions",
        function=oops_p24_recursive_definition_check_v_0_0_1,
        category=Category.LABELING,
        source_framework=SourceFramework.OOPS,
        source_id="P24",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.COUNT,
        description="Terms whose definition restates the term's own name.",
    ),
    MetricDescriptor(
        metric_id="oopsP25SelfInverse",
        name="Relationship inverse to itself",
        function=oops_p25_self_inverse_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P25",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.COUNT,
        description="Properties asserted as their own owl:inverseOf.",
    ),
    MetricDescriptor(
        metric_id="oopsP26SymmetricWithInverse",
        name="Inverse declared for symmetric property",
        function=oops_p26_symmetric_with_inverse_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P26",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.COUNT,
        description="Symmetric properties carrying a conflicting inverse.",
    ),
    MetricDescriptor(
        metric_id="oopsP33SinglePropertyChain",
        name="Property chain with one property",
        function=oops_p33_single_property_chain_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P33",
        source_url=_CATALOGUE,
        severity=Severity.MINOR,
        scale=Scale.COUNT,
        description="owl:propertyChainAxiom with fewer than two members.",
    ),
    MetricDescriptor(
        metric_id="oopsP34UntypedClass",
        name="Untyped class",
        function=oops_p34_untyped_class_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P34",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.COUNT,
        description="Resources used as classes but never declared as such.",
    ),
    MetricDescriptor(
        metric_id="oopsP35UntypedProperty",
        name="Untyped property",
        function=oops_p35_untyped_property_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P35",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.COUNT,
        description="Resources used as properties but never declared as such.",
    ),
    MetricDescriptor(
        metric_id="oopsP36UriFileExtension",
        name="URI contains file extension",
        function=oops_p36_uri_file_extension_check_v_0_0_1,
        category=Category.NAMING,
        source_framework=SourceFramework.OOPS,
        source_id="P36",
        source_url=_CATALOGUE,
        severity=Severity.MINOR,
        scale=Scale.COUNT,
        description="Term URIs embedding .owl, .rdf, .ttl and similar.",
    ),
    MetricDescriptor(
        metric_id="oopsP38OntologyDeclaration",
        name="OWL ontology declaration",
        function=oops_p38_ontology_declaration_check_v_0_0_1,
        category=Category.METADATA,
        source_framework=SourceFramework.OOPS,
        source_id="P38",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.BOOLEAN,
        higher_is_better=True,
        description="Presence of an owl:Ontology declaration.",
    ),
    MetricDescriptor(
        metric_id="oopsP39AmbiguousNamespace",
        name="Ambiguous namespace",
        function=oops_p39_ambiguous_namespace_check_v_0_0_1,
        category=Category.METADATA,
        source_framework=SourceFramework.OOPS,
        source_id="P39",
        source_url=_CATALOGUE,
        severity=Severity.CRITICAL,
        scale=Scale.BOOLEAN,
        higher_is_better=True,
        description="Presence of an ontology IRI or base URI.",
    ),
    MetricDescriptor(
        metric_id="oopsP40NamespaceHijacking",
        name="Namespace hijacking",
        function=oops_p40_namespace_hijacking_check_v_0_0_1,
        category=Category.STRUCTURAL,
        source_framework=SourceFramework.OOPS,
        source_id="P40",
        source_url=_CATALOGUE,
        severity=Severity.CRITICAL,
        scale=Scale.COUNT,
        description="Defining axioms asserted about terms in foreign "
                    "namespaces.",
    ),
]

for _descriptor in _OOPS_DESCRIPTORS:
    register_metric(_descriptor)
