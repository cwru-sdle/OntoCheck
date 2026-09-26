"""
OOPS!-derived lexical, annotation and naming pitfall checks.

Implements the OOPS! pitfalls that are decided from identifiers, labels and
annotations rather than from logical axioms.  Several use WordNet (through
NLTK) to recognise synonyms and lexicalised phrases; when WordNet is not
available they fall back to exact lexical matching and say so in
``detail["wordnet"]``.

Pitfalls implemented here
-------------------------
======  ==========================================  ==========
Code    Pitfall                                     Importance
======  ==========================================  ==========
P01     Creating polysemous elements                critical
P02     Creating synonyms as classes                minor
P03     Creating the relationship "is" instead of
        OWL primitives                              critical
P04     Creating unconnected ontology elements      minor
P07     Merging different concepts in the same
        class                                       minor
P08     Missing annotations                         minor
P11     Missing domain or range in properties       important
P12     Equivalent properties not explicitly
        declared                                    important
P20     Misusing ontology annotations               minor
P22     Using different naming conventions          minor
P23     Duplicating a datatype already provided by
        the implementation language                 important
P30     Equivalent classes not explicitly declared  important
P32     Several classes with the same label         minor
P41     No license declared                         important
======  ==========================================  ==========

Scope
-----
Unless stated otherwise a check examines the terms minted in the ontology's
own namespace(s) (see ``_own_namespace``).  Imported upper-ontology terms
that are only re-declared as stubs (CCO, BFO) are not the assessed
ontology's responsibility and are excluded; including them would penalise
every module that imports CCO for gaps in CCO.

Heuristic checks
----------------
P01, P02, P07, P12, P20, P22 and P30 are heuristic in OOPS! as well: they
identify *candidates* that a modeller should review.  Each such result sets
``detail["heuristic"] = True``.

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
from collections import Counter, defaultdict

from rdflib import BNode, Literal, OWL, RDF, RDFS, SKOS, URIRef

from .helpers.oops_helpers import (
    _is_foundational,
    _load_graph,
    _local_name,
    _named_classes,
    _ontology_iri,
    _own_namespace,
    _split_identifier,
)
from .helpers.semantic_helpers import (
    DEFINITION_PREDICATES,
    _are_synonyms,
    _declared_kind,
    _individuals,
    _is_opaque_identifier,
    _labels,
    _lexical_forms,
    _normalise,
    _object_and_datatype_properties,
    _synonym_variant,
    _synsets,
    _told_superclasses,
    _wordnet,
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


def _load_error(metric_id):
    """
    Build the result returned when an ontology cannot be loaded.

    Parameters
    ----------
    metric_id : str
        Registry identifier of the calling metric.

    Returns
    -------
    MetricResult
        Result with an ``"Error:"`` status.
    """
    return MetricResult(metric_id=metric_id,
                        status="Error: could not load ontology")


def _is_own(term, own_ns):
    """
    Test whether a term is minted in the ontology's own namespace(s).

    Parameters
    ----------
    term : rdflib.term.Node
        Term to test.
    own_ns : str, tuple of str or None
        Result of ``_own_namespace``.  ``None`` accepts every non-foundational
        URI.

    Returns
    -------
    bool
        ``True`` for a URI in the own namespace.
    """
    if not isinstance(term, URIRef) or _is_foundational(term):
        return False
    return True if own_ns is None else str(term).startswith(own_ns)


def _own_classes(g, own_ns):
    """
    Return the named classes minted in the own namespace(s).

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    own_ns : str, tuple of str or None
        Result of ``_own_namespace``.

    Returns
    -------
    set of rdflib.URIRef
        Own named classes.
    """
    return {c for c in _named_classes(g) if _is_own(c, own_ns)}


def _own_properties(g, own_ns):
    """
    Return the object and datatype properties minted in the own namespace(s).

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    own_ns : str, tuple of str or None
        Result of ``_own_namespace``.

    Returns
    -------
    set of rdflib.URIRef
        Own object and datatype properties.
    """
    return {p for p in _object_and_datatype_properties(g) if _is_own(p, own_ns)}


# ---------------------------------------------------------------------------
# P01 -- Creating polysemous elements
# ---------------------------------------------------------------------------

def oops_p01_polysemous_elements_v_0_0_1(ttl_file):
    """
    OOPS! P01 -- Creating polysemous elements.

    Identify ontology elements whose identifier is used for more than one
    conceptual idea.

    Definitions
    -----------
    - Punned identifier: one IRI declared as more than one kind of element
      (class, object property, datatype property, individual).  The same
      identifier then names different things, which is the formal signature
      of polysemy.

    - Divergent definitions: an element with two or more textual definitions
      carried by the same predicate and language whose stemmed content words overlap by less than
      30 % (overlap coefficient, ``|A ∩ B| / min(|A|, |B|)``, so that a short
      and a long definition of the same sense are not flagged).  Two
      unrelated definitions indicate that the element has been used for two
      senses, typically after a merge.  Definitions under different
      predicates are not compared, because ``rdfs:comment`` commonly holds
      editorial notes beside a ``skos:definition``.

    - Divergent labels: an element with two or more ``rdfs:label`` values in
      the same language whose normalised forms differ and are not WordNet
      synonyms of each other.

    Source
    ------
    OOPS! P01 (critical) -- https://oops.linkeddata.es/catalogue.jsp.
    OOPS! does not detect P01 automatically; the three signals above are
    OntoCheck's operationalisation.

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of candidate polysemous elements;
        ``passed`` is ``True`` when none are found.  ``detail`` breaks the
        candidates down by signal.

    Output Information
    ------------------
    - Punned identifiers with their declared kinds
    - Elements with divergent definitions or labels

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    Heuristic.  Every flagged element needs review by a domain expert.

    Examples
    --------
    >>> r = oops_p01_polysemous_elements_v_0_0_1("onto.ttl")  # doctest: +SKIP
    >>> r.detail["punned"]                                    # doctest: +SKIP
    []
    """
    mid = "oopsP01Polysemy"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    terms = {s for s in g.subjects() if _is_own(s, own_ns)}

    punned, div_defs, div_labels = [], [], []
    stop = {"a", "an", "the", "of", "in", "to", "and", "or", "is", "that",
            "which", "for", "by", "with", "as", "on", "at", "from", "be"}

    try:
        from nltk.stem import PorterStemmer
        stem = PorterStemmer().stem
    except ImportError:
        stem = lambda w: w  # noqa: E731

    def words(text):
        """Return the stemmed content words of a definition."""
        return {stem(w) for w in re.findall(r"[a-z]{3,}", text.lower())
                if w not in stop}

    for t in sorted(terms, key=str):
        kinds = _declared_kind(g, t) - {"annotation"}
        if len(kinds) > 1:
            punned.append({"term": str(t), "kinds": sorted(kinds)})

        by_lang = defaultdict(list)
        for p in DEFINITION_PREDICATES:
            for o in g.objects(t, p):
                if isinstance(o, Literal) and str(o).strip():
                    by_lang[(p, o.language)].append(str(o))
        for lang, texts in by_lang.items():
            texts = list(dict.fromkeys(texts))
            for i, a in enumerate(texts):
                for b in texts[i + 1:]:
                    wa, wb = words(a), words(b)
                    if wa and wb and len(wa & wb) / min(len(wa), len(wb)) < 0.3:
                        div_defs.append({"term": str(t), "definitions": [a, b]})

        labels_by_lang = defaultdict(set)
        for o in g.objects(t, RDFS.label):
            if isinstance(o, Literal) and str(o).strip():
                labels_by_lang[o.language].add(_normalise(o))
        for lang, labels in labels_by_lang.items():
            labels = sorted(labels)
            for i, a in enumerate(labels):
                for b in labels[i + 1:]:
                    ta, tb = a.split(), b.split()
                    related = (set(ta) & set(tb)) or _synonym_variant(ta, tb) \
                        or _are_synonyms(a.replace(" ", "_"), b.replace(" ", "_"))
                    if not related:
                        div_labels.append({"term": str(t), "labels": [a, b]})

    affected = sorted({d["term"] for d in punned + div_defs + div_labels})
    logger.info("--- OOPS! P01: polysemous elements ---")
    logger.info(f"Punned identifiers: {len(punned)}; divergent definitions: "
                f"{len(div_defs)}; divergent labels: {len(div_labels)}")
    for a in affected:
        logger.info(f"  {a}")

    return MetricResult(
        metric_id=mid,
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=len(terms),
        detail={"punned": punned, "divergent_definitions": div_defs,
                "divergent_labels": div_labels, "heuristic": True,
                "wordnet": _wordnet() is not None},
        message=(f"{len(affected)} candidate polysemous element(s)"
                 if affected else "No polysemy signals found"),
    )


# ---------------------------------------------------------------------------
# P02 -- Creating synonyms as classes
# ---------------------------------------------------------------------------

def oops_p02_synonyms_as_classes_v_0_0_1(ttl_file):
    """
    OOPS! P02 -- Creating synonyms as classes.

    Identify distinct classes that represent the same concept under
    synonymous names.

    Definitions
    -----------
    - Equivalent same-namespace classes: two named classes in the same
      namespace related by ``owl:equivalentClass``.  This is the pattern the
      OOPS! catalogue describes: the synonym has been minted as a separate
      class and then stated equivalent, instead of being recorded as an
      alternative label.

    - Synonymous identifiers: two own classes whose tokenised names have the
      same length and differ in exactly one token, where the differing
      tokens share a WordNet noun synset (e.g. ``SampleHolder`` and
      ``SpecimenHolder``).

    - Label/altLabel collision: the ``rdfs:label`` or ``skos:prefLabel`` of
      one class equals the ``skos:altLabel`` of another, so the synonym is
      recorded on one class and minted as another.

    Source
    ------
    OOPS! P02 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of candidate synonym pairs; ``passed`` is
        ``True`` when there are none.  ``detail`` lists the pairs by signal.

    Output Information
    ------------------
    - Pairs of classes with the evidence that relates them

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    Without WordNet only the first and third signals are evaluated.

    Examples
    --------
    >>> r = oops_p02_synonyms_as_classes_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP02SynonymClasses"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    classes = _own_classes(g, own_ns)

    from .helpers.oops_helpers import _namespace_of

    equiv_pairs = []
    for s, o in g.subject_objects(OWL.equivalentClass):
        if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o \
                and _namespace_of(s) == _namespace_of(o) and _is_own(s, own_ns):
            equiv_pairs.append(tuple(sorted((str(s), str(o)))))

    tokens = {c: _split_identifier(_local_name(c)) for c in classes
              if not _is_opaque_identifier(_local_name(c))}
    by_len = defaultdict(list)
    for c, t in tokens.items():
        by_len[len(t)].append(c)
    syn_pairs = []
    for group in by_len.values():
        group = sorted(group, key=str)
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                v = _synonym_variant(tokens[a], tokens[b])
                if v:
                    syn_pairs.append({"pair": [str(a), str(b)],
                                      "synonyms": list(v)})

    primary = defaultdict(set)
    for c in classes:
        for p in (RDFS.label, SKOS.prefLabel):
            for o in g.objects(c, p):
                if str(o).strip():
                    primary[_normalise(o)].add(c)
    alt_pairs = []
    for c in classes:
        for o in g.objects(c, SKOS.altLabel):
            for other in primary.get(_normalise(o), ()):
                if other != c:
                    alt_pairs.append({"pair": sorted([str(c), str(other)]),
                                      "altLabel": str(o)})

    pairs = {tuple(p) for p in equiv_pairs}
    pairs |= {tuple(sorted(d["pair"])) for d in syn_pairs + alt_pairs}
    affected = sorted({x for p in pairs for x in p})

    logger.info("--- OOPS! P02: synonyms as classes ---")
    logger.info(f"Equivalent same-namespace pairs: {len(equiv_pairs)}; "
                f"synonymous identifiers: {len(syn_pairs)}; "
                f"label/altLabel collisions: {len(alt_pairs)}")

    return MetricResult(
        metric_id=mid,
        score=len(pairs),
        passed=not pairs,
        affected=affected,
        total_examined=len(classes),
        detail={"equivalent_same_namespace": equiv_pairs,
                "synonymous_identifiers": syn_pairs,
                "label_altlabel_collisions": alt_pairs,
                "heuristic": True, "wordnet": _wordnet() is not None},
        message=(f"{len(pairs)} candidate synonym class pair(s)"
                 if pairs else "No synonym classes detected"),
    )


# ---------------------------------------------------------------------------
# P03 -- Creating the relationship "is"
# ---------------------------------------------------------------------------

_IS_PATTERNS = {
    ("is",), ("isa",), ("is", "a"), ("is", "an"), ("is", "kind", "of"),
    ("is", "type", "of"), ("is", "instance", "of"), ("instance", "of"),
    ("kind", "of"), ("type", "of"), ("is", "same", "as"), ("same", "as"),
    ("is", "subclass", "of"), ("subclass", "of"), ("is", "a", "kind", "of"),
}


def oops_p03_is_relationship_v_0_0_1(ttl_file):
    """
    OOPS! P03 -- Creating the relationship "is" instead of using
    ``rdfs:subClassOf``, ``rdf:type`` or ``owl:sameAs``.

    Identify properties whose name or label is a form of "is", which almost
    always re-implements an OWL/RDFS primitive as a domain relation.

    Definitions
    -----------
    - "is" property: an object, datatype or untyped property whose tokenised
      local name or label is one of ``is``, ``isA``, ``is_a``, ``isKindOf``,
      ``isTypeOf``, ``instanceOf``, ``typeOf``, ``sameAs``, ``subclassOf``
      and their variants.  Longer names beginning with "is" (``isPartOf``,
      ``isComponentOf``) are ordinary relations and are not flagged.

    Source
    ------
    OOPS! P03 (critical) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of such properties; ``passed`` is ``True``
        when there are none.

    Output Information
    ------------------
    - Flagged properties with the matched form

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p03_is_relationship_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP03IsRelationship"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)

    candidates = set(_object_and_datatype_properties(g))
    candidates |= {p for p in g.subjects(RDF.type, RDF.Property)}
    candidates |= {p for _, p, _ in g if isinstance(p, URIRef)}
    candidates = {p for p in candidates if _is_own(p, own_ns)}

    flagged = []
    for p in sorted(candidates, key=str):
        forms = [tuple(_split_identifier(_local_name(p)))]
        forms += [tuple(_normalise(l).split()) for l in g.objects(p, RDFS.label)]
        hit = next((f for f in forms if f in _IS_PATTERNS), None)
        if hit:
            flagged.append({"property": str(p), "form": " ".join(hit)})

    logger.info("--- OOPS! P03: 'is' relationships ---")
    for f in flagged:
        logger.info(f"  {f['property']} ({f['form']})")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=[f["property"] for f in flagged],
        total_examined=len(candidates),
        detail={"flagged": flagged},
        message=(f"{len(flagged)} property(ies) re-implement 'is'"
                 if flagged else "No 'is' relationships found"),
    )


# ---------------------------------------------------------------------------
# P04 -- Creating unconnected ontology elements
# ---------------------------------------------------------------------------

_STRUCTURAL_CLASS_PREDICATES = (
    RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith,
    OWL.complementOf,
)


def oops_p04_unconnected_elements_v_0_0_1(ttl_file):
    """
    OOPS! P04 -- Creating unconnected ontology elements.

    Identify own classes and properties that take part in no logical
    relation with any other element.

    Definitions
    -----------
    - Connected class: a class that appears in a subsumption, equivalence,
      disjointness or complement axiom (as subject or object), in the
      domain or range of a property, in a restriction or Boolean class
      expression, or as the type of an individual.

    - Connected property: a property with a domain, a range, a
      sub-/super-/inverse-/equivalent-property axiom, a use in a restriction
      or property chain, or a use as a predicate in an instance assertion.

    - Annotations (labels, definitions) and the ``rdf:type`` declaration
      itself do not connect an element.

    Source
    ------
    OOPS! P04 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of unconnected own elements; ``passed`` is
        ``True`` when there are none.  ``detail`` separates classes and
        properties.

    Output Information
    ------------------
    - Unconnected classes and unconnected properties

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    OntoCheck's ``isolatedElements`` metric treats a property as isolated
    unless it takes part in a property-to-property axiom.  P04 follows the
    OOPS! reading, in which a domain or range already connects a property.

    Examples
    --------
    >>> r = oops_p04_unconnected_elements_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP04Unconnected"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    classes = _own_classes(g, own_ns)
    props = _own_properties(g, own_ns)

    connected = set()
    for p in _STRUCTURAL_CLASS_PREDICATES:
        for s, o in g.subject_objects(p):
            if not (s == o):
                connected.add(s)
                connected.add(o)
    for p in (RDFS.domain, RDFS.range):
        for s, o in g.subject_objects(p):
            connected.add(o)
            connected.add(s)
    for p in (OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass,
              OWL.onProperty, OWL.hasValue):
        for o in g.objects(None, p):
            connected.add(o)
    for p in (OWL.unionOf, OWL.intersectionOf, OWL.oneOf,
              OWL.propertyChainAxiom, OWL.members):
        from .helpers.oops_helpers import _parse_rdf_list
        for s, lst in g.subject_objects(p):
            connected.update(_parse_rdf_list(g, lst))
    for p in (RDFS.subPropertyOf, OWL.inverseOf, OWL.equivalentProperty,
              OWL.propertyDisjointWith):
        for s, o in g.subject_objects(p):
            connected.add(s)
            connected.add(o)
    connected |= {t for types in _individuals(g).values() for t in types}
    used_predicates = {p for s, p, o in g
                       if not isinstance(s, BNode) and p in props
                       and (s, RDF.type, OWL.Class) not in g}
    connected |= used_predicates

    lonely_classes = sorted(str(c) for c in classes if c not in connected)
    lonely_props = sorted(str(p) for p in props if p not in connected)
    affected = lonely_classes + lonely_props

    logger.info("--- OOPS! P04: unconnected elements ---")
    logger.info(f"Unconnected classes: {len(lonely_classes)} of {len(classes)}")
    logger.info(f"Unconnected properties: {len(lonely_props)} of {len(props)}")

    return MetricResult(
        metric_id=mid,
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=len(classes) + len(props),
        detail={"classes": lonely_classes, "properties": lonely_props},
        message=(f"{len(lonely_classes)} class(es) and {len(lonely_props)} "
                 f"property(ies) unconnected" if affected
                 else "All own elements are connected"),
    )


# ---------------------------------------------------------------------------
# P07 -- Merging different concepts in the same class
# ---------------------------------------------------------------------------

_CONJUNCTIONS = {"and", "or", "nor"}


def oops_p07_merged_concepts_v_0_0_1(ttl_file):
    """
    OOPS! P07 -- Merging different concepts in the same class.

    Identify classes whose name joins two concepts with a conjunction.

    Definitions
    -----------
    - Merged class name: an own class whose tokenised local name or label
      contains "and", "or" or "nor", or the symbol "&".

    - Lexicalised compound: a conjunction phrase that is itself a WordNet
      entry (e.g. ``research_and_development``, ``rock_and_roll``) names a
      single concept and is not flagged.

    Source
    ------
    OOPS! P07 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of candidate merged classes; ``passed`` is
        ``True`` when there are none.

    Output Information
    ------------------
    - Flagged classes with the conjunction found

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p07_merged_concepts_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP07MergedConcepts"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    classes = _own_classes(g, own_ns)

    flagged = []
    for c in sorted(classes, key=str):
        forms = [_split_identifier(_local_name(c))]
        forms += [_normalise(l).split() for l in g.objects(c, RDFS.label)]
        raw = " ".join(str(l) for l in g.objects(c, RDFS.label))
        for toks in forms:
            conj = [t for t in toks if t in _CONJUNCTIONS]
            if conj or "&" in raw:
                i = toks.index(conj[0]) if conj else None
                phrase = "_".join(toks[max(0, i - 1): i + 2]) if conj else ""
                if phrase and _synsets(phrase):
                    continue
                flagged.append({"class": str(c),
                                "conjunction": conj[0] if conj else "&"})
                break

    logger.info("--- OOPS! P07: merged concepts ---")
    for f in flagged:
        logger.info(f"  {f['class']} ({f['conjunction']})")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=[f["class"] for f in flagged],
        total_examined=len(classes),
        detail={"flagged": flagged, "heuristic": True,
                "wordnet": _wordnet() is not None},
        message=(f"{len(flagged)} class name(s) join two concepts"
                 if flagged else "No merged-concept class names found"),
    )


# ---------------------------------------------------------------------------
# P08 -- Missing annotations
# ---------------------------------------------------------------------------

def oops_p08_missing_annotations_v_0_0_1(ttl_file):
    """
    OOPS! P08 -- Missing annotations.

    Identify own classes, object properties and datatype properties that
    lack a human-readable label or a definition.

    Definitions
    -----------
    - Label: ``rdfs:label``, ``skos:prefLabel``, ``skos:altLabel`` or
      ``ontolex:writtenRep`` (the lemon lexical entry named by OOPS!).

    - Definition: ``rdfs:comment`` or ``dc:description`` as named by OOPS!,
      extended with ``skos:definition``, ``dcterms:description`` and
      ``obo:IAO_0000115``, which are the definition conventions of MDS-Onto
      and the OBO Foundry.

    Source
    ------
    OOPS! P08 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of own elements lacking a label, a
        definition or both; ``passed`` is ``True`` when there are none.

    Output Information
    ------------------
    - Elements without a label and elements without a definition

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    OntoCheck's ``checkLabel`` and ``definitionCheck`` examine classes only
    and every class in the file.  P08 covers properties too and restricts to
    the own namespace, matching the OOPS! element scope.

    Examples
    --------
    >>> r = oops_p08_missing_annotations_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP08MissingAnnotations"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    elements = _own_classes(g, own_ns) | _own_properties(g, own_ns)

    no_label = sorted(str(e) for e in elements if not _labels(g, e))
    no_def = sorted(str(e) for e in elements
                    if not _labels(g, e, DEFINITION_PREDICATES))
    affected = sorted(set(no_label) | set(no_def))

    logger.info("--- OOPS! P08: missing annotations ---")
    logger.info(f"Without label: {len(no_label)}; without definition: "
                f"{len(no_def)} (of {len(elements)})")

    return MetricResult(
        metric_id=mid,
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=len(elements),
        detail={"missing_label": no_label, "missing_definition": no_def},
        message=(f"{len(no_label)} element(s) without label, {len(no_def)} "
                 f"without definition" if affected
                 else "Every own element is labelled and defined"),
    )


# ---------------------------------------------------------------------------
# P11 -- Missing domain or range in properties
# ---------------------------------------------------------------------------

def oops_p11_missing_domain_range_v_0_0_1(ttl_file):
    """
    OOPS! P11 -- Missing domain or range in properties.

    Identify own object and datatype properties without a domain or range.

    Definitions
    -----------
    - Effective domain: a declared ``rdfs:domain``, or the ``rdfs:range`` of
      a declared ``owl:inverseOf`` partner.  OOPS! does not flag a property
      whose inverse supplies the missing information, since a reasoner
      derives it.

    - Effective range: symmetrically, a declared ``rdfs:range`` or the
      ``rdfs:domain`` of an inverse partner.

    Source
    ------
    OOPS! P11 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of own properties missing a domain, a range
        or both; ``passed`` is ``True`` when there are none.

    Output Information
    ------------------
    - Properties missing a domain and properties missing a range

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    OntoCheck's ``missingDomainRange`` counts every declared property,
    including stubs of imported properties, and ignores inverses.

    Examples
    --------
    >>> r = oops_p11_missing_domain_range_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP11MissingDomainRange"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    props = _own_properties(g, own_ns)

    def inverses(p):
        """Return the named properties declared inverse to ``p``."""
        out = set(g.objects(p, OWL.inverseOf)) | set(g.subjects(OWL.inverseOf, p))
        return {q for q in out if isinstance(q, URIRef)}

    no_dom, no_rng = [], []
    for p in sorted(props, key=str):
        inv = inverses(p)
        has_dom = g.value(p, RDFS.domain) is not None or any(
            g.value(q, RDFS.range) is not None for q in inv)
        has_rng = g.value(p, RDFS.range) is not None or any(
            g.value(q, RDFS.domain) is not None for q in inv)
        if not has_dom:
            no_dom.append(str(p))
        if not has_rng:
            no_rng.append(str(p))
    affected = sorted(set(no_dom) | set(no_rng))

    logger.info("--- OOPS! P11: missing domain or range ---")
    logger.info(f"Missing domain: {len(no_dom)}; missing range: {len(no_rng)} "
                f"(of {len(props)})")

    return MetricResult(
        metric_id=mid,
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=len(props),
        detail={"missing_domain": no_dom, "missing_range": no_rng},
        message=(f"{len(affected)} property(ies) lack a domain or range"
                 if affected else "Every own property has domain and range"),
    )


# ---------------------------------------------------------------------------
# P12 -- Equivalent properties not explicitly declared
# ---------------------------------------------------------------------------

def _linked(g, a, b, predicates):
    """
    Test whether two terms are related by any of the given predicates.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    a, b : rdflib.URIRef
        Terms.
    predicates : iterable of rdflib.URIRef
        Predicates tested in both directions.

    Returns
    -------
    bool
        ``True`` if any ``(a, p, b)`` or ``(b, p, a)`` triple exists.
    """
    return any((a, p, b) in g or (b, p, a) in g for p in predicates)


def _duplicate_pairs(g, terms, own_ns, pos):
    """
    Find pairs of terms that name the same concept.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    terms : set of rdflib.URIRef
        Candidate terms of one kind (all classes, or all properties).
    own_ns : str, tuple of str or None
        Result of ``_own_namespace``; at least one member of a pair must be
        own.
    pos : str
        WordNet part of speech for the synonym test.

    Returns
    -------
    list of dict
        One dict per pair with ``pair`` (two IRIs) and ``evidence``
        (``"same name or label"`` or ``"synonyms: x/y"``).
    """
    forms = {t: _lexical_forms(g, t) for t in terms}
    index = defaultdict(set)
    for t, fs in forms.items():
        for f in fs:
            index[f].add(t)
    pairs = {}
    for f, members in index.items():
        members = sorted(members, key=str)
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if _is_own(a, own_ns) or _is_own(b, own_ns):
                    pairs[(a, b)] = "same name or label"

    by_len = defaultdict(list)
    for t, fs in forms.items():
        for f in fs:
            by_len[len(f.split())].append((f.split(), t))
    for group in by_len.values():
        for i, (ta, a) in enumerate(group):
            for tb, b in group[i + 1:]:
                if a == b or (a, b) in pairs or (b, a) in pairs:
                    continue
                if not (_is_own(a, own_ns) or _is_own(b, own_ns)):
                    continue
                v = _synonym_variant(ta, tb, pos)
                if v:
                    key = tuple(sorted((a, b), key=str))
                    pairs[key] = f"synonyms: {v[0]}/{v[1]}"
    return [{"pair": [str(a), str(b)], "evidence": e}
            for (a, b), e in sorted(pairs.items(), key=lambda kv: str(kv[0]))]


def oops_p12_undeclared_equivalent_properties_v_0_0_1(ttl_file):
    """
    OOPS! P12 -- Equivalent properties not explicitly declared.

    Identify properties that duplicate one another without an
    ``owl:equivalentProperty`` axiom.

    Definitions
    -----------
    - Duplicate properties: two object properties, or two datatype
      properties, at least one in the own namespace, whose normalised local
      names or labels are equal, or differ by one WordNet-synonymous token.

    - Declared relation: the pair is not flagged when related by
      ``owl:equivalentProperty``, ``rdfs:subPropertyOf``, ``owl:inverseOf``
      or ``owl:sameAs``.

    Source
    ------
    OOPS! P12 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of undeclared duplicate pairs; ``passed`` is
        ``True`` when there are none.

    Output Information
    ------------------
    - Property pairs with the evidence that relates them

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    Most relevant for merged ontologies, where two modules mint the same
    relation independently.

    Examples
    --------
    >>> r = oops_p12_undeclared_equivalent_properties_v_0_0_1("m.ttl")  # doctest: +SKIP
    """
    mid = "oopsP12UndeclaredEquivProperty"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    rel = (OWL.equivalentProperty, RDFS.subPropertyOf, OWL.inverseOf,
           OWL.sameAs)

    found = []
    for kind in (OWL.ObjectProperty, OWL.DatatypeProperty):
        terms = {s for s in g.subjects(RDF.type, kind)
                 if isinstance(s, URIRef) and not _is_foundational(s)}
        for d in _duplicate_pairs(g, terms, own_ns, pos="v"):
            a, b = URIRef(d["pair"][0]), URIRef(d["pair"][1])
            if not _linked(g, a, b, rel):
                found.append(d)
    affected = sorted({x for d in found for x in d["pair"]})

    logger.info("--- OOPS! P12: equivalent properties not declared ---")
    for d in found:
        logger.info(f"  {d['pair'][0]} ~ {d['pair'][1]} ({d['evidence']})")

    return MetricResult(
        metric_id=mid,
        score=len(found),
        passed=not found,
        affected=affected,
        total_examined=len(_object_and_datatype_properties(g)),
        detail={"pairs": found, "heuristic": True,
                "wordnet": _wordnet() is not None},
        message=(f"{len(found)} duplicate property pair(s) without "
                 f"owl:equivalentProperty" if found
                 else "No undeclared equivalent properties"),
    )


# ---------------------------------------------------------------------------
# P20 -- Misusing ontology annotations
# ---------------------------------------------------------------------------

_DATE_PREDICATES = (
    URIRef("http://purl.org/dc/terms/created"),
    URIRef("http://purl.org/dc/terms/modified"),
    URIRef("http://purl.org/dc/terms/issued"),
    URIRef("http://purl.org/dc/terms/date"),
    URIRef("http://purl.org/dc/elements/1.1/date"),
)


def oops_p20_misused_annotations_v_0_0_1(ttl_file):
    """
    OOPS! P20 -- Misusing ontology annotations.

    Identify annotation values whose content does not fit the annotation
    property that carries them.

    Definitions
    -----------
    - Definition in a label: an ``rdfs:label``/``skos:prefLabel`` of more than
      ten words, or one containing sentence punctuation (". ", ";") -- the
      content of ``rdfs:comment`` swapped into the label slot.

    - Label in a definition: a definition (``rdfs:comment``,
      ``skos:definition``, ...) that is identical to the element's label or
      has at most two words -- the label swapped into the definition slot.

    - Malformed version information: an ``owl:versionInfo`` value containing
      no digit, or an ``owl:versionIRI`` given as a literal.

    - Malformed date: a ``dcterms:created``/``modified``/``issued``/``date``
      value that does not contain an ISO-8601 date (``YYYY-MM-DD`` or
      ``YYYY``).

    Source
    ------
    OOPS! P20 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of flagged annotation assertions; ``passed``
        is ``True`` when there are none.

    Output Information
    ------------------
    - Each flagged assertion with the reason

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p20_misused_annotations_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP20MisusedAnnotations"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    subjects = {s for s in g.subjects() if _is_own(s, own_ns)}
    onto = _ontology_iri(g)
    if onto is not None:
        subjects.add(onto)

    flagged = []
    for s in sorted(subjects, key=str):
        labels = [str(o).strip() for p in (RDFS.label, SKOS.prefLabel)
                  for o in g.objects(s, p) if str(o).strip()]
        for lab in labels:
            if len(lab.split()) > 10 or re.search(r"\.\s|;", lab):
                flagged.append({"term": str(s), "predicate": "label",
                                "value": lab,
                                "reason": "definition text in a label"})
        norm_labels = {_normalise(l) for l in labels}
        for p in DEFINITION_PREDICATES:
            for o in g.objects(s, p):
                text = str(o).strip()
                if not text:
                    continue
                if _normalise(text) in norm_labels or len(text.split()) <= 2:
                    flagged.append({"term": str(s), "predicate": str(p),
                                    "value": text,
                                    "reason": "label text in a definition"})
        for o in g.objects(s, OWL.versionInfo):
            if not re.search(r"\d", str(o)):
                flagged.append({"term": str(s), "predicate": "owl:versionInfo",
                                "value": str(o),
                                "reason": "version information without a "
                                          "version number"})
        for o in g.objects(s, OWL.versionIRI):
            if isinstance(o, Literal):
                flagged.append({"term": str(s), "predicate": "owl:versionIRI",
                                "value": str(o),
                                "reason": "version IRI given as a literal"})
        for p in _DATE_PREDICATES:
            for o in g.objects(s, p):
                if not re.search(r"\b\d{4}(-\d{2}-\d{2})?\b", str(o)):
                    flagged.append({"term": str(s), "predicate": str(p),
                                    "value": str(o),
                                    "reason": "date annotation without a "
                                              "date"})

    affected = sorted({f["term"] for f in flagged})
    logger.info("--- OOPS! P20: misused annotations ---")
    for reason, n in Counter(f["reason"] for f in flagged).items():
        logger.info(f"  {reason}: {n}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=affected,
        total_examined=len(subjects),
        detail={"flagged": flagged, "heuristic": True,
                "by_reason": dict(Counter(f["reason"] for f in flagged))},
        message=(f"{len(flagged)} misused annotation value(s)"
                 if flagged else "No misused annotations detected"),
    )


# ---------------------------------------------------------------------------
# P22 -- Using different naming conventions
# ---------------------------------------------------------------------------

def _naming_style(name):
    """
    Classify the naming convention of a local name.

    Parameters
    ----------
    name : str
        Local name.

    Returns
    -------
    str
        One of ``"opaque"``, ``"UpperCamel"``, ``"lowerCamel"``,
        ``"snake_case"``, ``"Upper_Snake"``, ``"kebab-case"``, ``"UPPER"``,
        ``"lower"``, ``"mixed-delimiters"`` or ``"other"``.

    Examples
    --------
    >>> _naming_style("XrayDetector"), _naming_style("transforms_into")
    ('UpperCamel', 'snake_case')
    """
    if _is_opaque_identifier(name):
        return "opaque"
    has_us, has_dash = "_" in name, "-" in name
    if has_us and has_dash:
        return "mixed-delimiters"
    if has_dash:
        return "kebab-case"
    if has_us:
        parts = [p for p in name.split("_") if p]
        if all(p.islower() or p.isdigit() for p in parts):
            return "snake_case"
        if all(p[:1].isupper() for p in parts):
            return "Upper_Snake"
        return "mixed-delimiters"
    if name.isupper():
        return "UPPER"
    if name.islower():
        return "lower"
    if name[:1].isupper():
        return "UpperCamel"
    if name[:1].islower():
        return "lowerCamel"
    return "other"


def oops_p22_naming_conventions_v_0_0_1(ttl_file):
    """
    OOPS! P22 -- Using different naming conventions in the ontology.

    Identify own classes and properties whose naming convention differs from
    the convention used by most elements of the same kind.

    Definitions
    -----------
    - Naming style: the convention of a local name -- UpperCamel,
      lowerCamel, snake_case, Upper_Snake, kebab-case, all-upper,
      all-lower, mixed delimiters, or an opaque numeric identifier.

    - Compatible styles: a single-word name has no visible convention, so
      ``lower`` is compatible with lowerCamel and snake_case, and
      ``UPPER`` (an acronym such as ``APS``) with UpperCamel.  Opaque
      identifiers (``ont00000908``) are a deliberate policy and are
      compared only with each other.

    - Deviant element: an element whose style is incompatible with the
      majority style of its kind (classes; object and datatype properties).

    Source
    ------
    OOPS! P22 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of deviant elements; ``passed`` is ``True``
        when every element follows the majority convention of its kind.

    Output Information
    ------------------
    - Majority style per kind and style distribution
    - Deviant elements with their style

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    OntoCheck's ``classCapitalCheck`` and ``classSpaceCheck`` cover
    capitalisation and whitespace of class names only.

    Examples
    --------
    >>> r = oops_p22_naming_conventions_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP22NamingConventions"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    compatible = {
        "UpperCamel": {"UpperCamel", "UPPER"},
        "lowerCamel": {"lowerCamel", "lower"},
        "snake_case": {"snake_case", "lower"},
        "Upper_Snake": {"Upper_Snake", "UpperCamel", "UPPER"},
        "kebab-case": {"kebab-case", "lower"},
    }

    kinds = {"classes": _own_classes(g, own_ns),
             "properties": _own_properties(g, own_ns)}
    deviants, dist, majority = [], {}, {}
    for kind, terms in kinds.items():
        styles = {t: _naming_style(_local_name(t)) for t in terms}
        counts = Counter(s for s in styles.values() if s != "opaque")
        dist[kind] = dict(counts)
        if not counts:
            continue
        major = counts.most_common(1)[0][0]
        majority[kind] = major
        ok = compatible.get(major, {major})
        for t, s in sorted(styles.items(), key=lambda kv: str(kv[0])):
            if s != "opaque" and s not in ok:
                deviants.append({"term": str(t), "kind": kind, "style": s,
                                 "majority": major})

    logger.info("--- OOPS! P22: naming conventions ---")
    for kind in kinds:
        logger.info(f"{kind}: majority {majority.get(kind)}; {dist.get(kind)}")
    logger.info(f"Deviant elements: {len(deviants)}")

    return MetricResult(
        metric_id=mid,
        score=len(deviants),
        passed=not deviants,
        affected=[d["term"] for d in deviants],
        total_examined=sum(len(v) for v in kinds.values()),
        detail={"deviants": deviants, "majority_style": majority,
                "style_distribution": dist, "heuristic": True},
        message=(f"{len(deviants)} element(s) break the majority naming "
                 f"convention" if deviants else "Naming conventions consistent"),
    )


# ---------------------------------------------------------------------------
# P23 -- Duplicating a datatype
# ---------------------------------------------------------------------------

_DATATYPE_NAMES = {
    "string", "boolean", "decimal", "integer", "int", "long", "short", "byte",
    "float", "double", "date", "date time", "datetime", "time", "duration",
    "g year", "gyear", "year month", "any uri", "anyuri", "uri",
    "non negative integer", "positive integer", "negative integer",
    "unsigned int", "hex binary", "base64 binary", "literal", "language",
    "normalized string", "token", "date time stamp",
}


def oops_p23_duplicated_datatype_v_0_0_1(ttl_file):
    """
    OOPS! P23 -- Duplicating a datatype already provided by the
    implementation language.

    Identify own classes that re-create an XML Schema or RDF datatype.

    Definitions
    -----------
    - Datatype class: an own class whose normalised local name or label is
      the name of an XSD/RDF datatype (``String``, ``Integer``, ``Boolean``,
      ``DateTime``, ``Float``, ``AnyURI`` and the rest of the XSD 1.1
      built-ins).

    - Boolean enumeration: an own class whose individuals (or
      ``owl:oneOf`` members) are exactly ``true``/``false`` or
      ``yes``/``no`` -- a re-implementation of ``xsd:boolean``.

    Source
    ------
    OOPS! P23 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of flagged classes; ``passed`` is ``True``
        when there are none.

    Output Information
    ------------------
    - Flagged classes with the datatype they duplicate

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = oops_p23_duplicated_datatype_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP23DuplicatedDatatype"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    classes = _own_classes(g, own_ns)
    from .helpers.oops_helpers import _parse_rdf_list

    members = defaultdict(set)
    for ind, types in _individuals(g).items():
        for t in types:
            members[t].add(_normalise(_local_name(ind)))
    for c in classes:
        for lst in g.objects(c, OWL.oneOf):
            members[c] |= {_normalise(_local_name(m))
                           for m in _parse_rdf_list(g, lst)}
        for eq in g.objects(c, OWL.equivalentClass):
            lst = g.value(eq, OWL.oneOf)
            if lst is not None:
                members[c] |= {_normalise(_local_name(m))
                               for m in _parse_rdf_list(g, lst)}

    flagged = []
    for c in sorted(classes, key=str):
        hit = next((f for f in _lexical_forms(g, c) if f in _DATATYPE_NAMES), None)
        if hit:
            flagged.append({"class": str(c), "duplicates": f"xsd:{hit}"})
        elif members.get(c) in ({"true", "false"}, {"yes", "no"}):
            flagged.append({"class": str(c), "duplicates": "xsd:boolean"})

    logger.info("--- OOPS! P23: duplicated datatypes ---")
    for f in flagged:
        logger.info(f"  {f['class']} -> {f['duplicates']}")

    return MetricResult(
        metric_id=mid,
        score=len(flagged),
        passed=not flagged,
        affected=[f["class"] for f in flagged],
        total_examined=len(classes),
        detail={"flagged": flagged},
        message=(f"{len(flagged)} class(es) duplicate a built-in datatype"
                 if flagged else "No duplicated datatypes"),
    )


# ---------------------------------------------------------------------------
# P30 -- Equivalent classes not explicitly declared
# ---------------------------------------------------------------------------

def oops_p30_undeclared_equivalent_classes_v_0_0_1(ttl_file):
    """
    OOPS! P30 -- Equivalent classes not explicitly declared.

    Identify classes that duplicate one another without an
    ``owl:equivalentClass`` axiom.

    Definitions
    -----------
    - Duplicate classes: two named classes with different IRIs, at least one
      in the own namespace, whose normalised local names or labels are equal,
      or differ by one WordNet-synonymous noun.

    - Declared relation: the pair is not flagged when related by
      ``owl:equivalentClass``, ``owl:sameAs``, or told subsumption in either
      direction.

    - SKOS-only mapping: a pair linked only by ``skos:exactMatch`` or
      ``skos:closeMatch`` is declared, but invisible to OWL reasoning.  It is
      not counted and is listed in ``detail["skos_only"]``.

    Source
    ------
    OOPS! P30 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of undeclared duplicate pairs; ``passed`` is
        ``True`` when there are none.  ``detail["cross_namespace"]`` counts
        pairs whose members live in different namespaces -- the case the
        OOPS! catalogue singles out for reused vocabularies.

    Output Information
    ------------------
    - Class pairs with the evidence that relates them

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    P32 (same label) overlaps with the "same label" evidence here, as in
    OOPS!; P30 additionally uses names and synonyms and ignores pairs that
    are already related.

    Examples
    --------
    >>> r = oops_p30_undeclared_equivalent_classes_v_0_0_1("m.ttl")  # doctest: +SKIP
    """
    mid = "oopsP30UndeclaredEquivClass"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    from .helpers.oops_helpers import _namespace_of
    classes = {c for c in _named_classes(g) if not _is_foundational(c)}
    supers = _told_superclasses(g)

    found, skos_only = [], []
    for d in _duplicate_pairs(g, classes, own_ns, pos="n"):
        a, b = URIRef(d["pair"][0]), URIRef(d["pair"][1])
        if _linked(g, a, b, (OWL.equivalentClass, OWL.sameAs)):
            continue
        if b in supers(a) or a in supers(b):
            continue
        if _linked(g, a, b, (SKOS.exactMatch, SKOS.closeMatch)):
            skos_only.append(d)
            continue
        d["cross_namespace"] = _namespace_of(a) != _namespace_of(b)
        found.append(d)
    affected = sorted({x for d in found for x in d["pair"]})

    logger.info("--- OOPS! P30: equivalent classes not declared ---")
    logger.info(f"Undeclared duplicate pairs: {len(found)}")

    return MetricResult(
        metric_id=mid,
        score=len(found),
        passed=not found,
        affected=affected,
        total_examined=len(classes),
        detail={"pairs": found, "skos_only": skos_only,
                "cross_namespace": sum(1 for d in found if d["cross_namespace"]),
                "heuristic": True, "wordnet": _wordnet() is not None},
        message=(f"{len(found)} duplicate class pair(s) without "
                 f"owl:equivalentClass" if found
                 else "No undeclared equivalent classes"),
    )


# ---------------------------------------------------------------------------
# P32 -- Several classes with the same label
# ---------------------------------------------------------------------------

def oops_p32_same_label_v_0_0_1(ttl_file):
    """
    OOPS! P32 -- Several classes with the same label.

    Identify groups of classes that share a label.

    Definitions
    -----------
    - Shared label: an ``rdfs:label`` or ``skos:prefLabel`` value that,
      compared case- and whitespace-insensitively within one language tag,
      is carried by two or more distinct named classes.

    Source
    ------
    OOPS! P32 (minor) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of classes that share a label with another
        class; ``passed`` is ``True`` when there are none.
        ``detail["groups"]`` maps each shared label to its classes.

    Output Information
    ------------------
    - Each shared label and the classes carrying it

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    OntoCheck's ``duplicateLabels`` also compares properties and counts
    duplicate label values rather than affected classes.

    Examples
    --------
    >>> r = oops_p32_same_label_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP32SameLabel"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    classes = {c for c in _named_classes(g) if not _is_foundational(c)}

    groups = defaultdict(set)
    for c in classes:
        for p in (RDFS.label, SKOS.prefLabel):
            for o in g.objects(c, p):
                if isinstance(o, Literal) and str(o).strip():
                    key = (" ".join(str(o).lower().split()), o.language or "")
                    groups[key].add(c)
    shared = {f"{k[0]}@{k[1]}" if k[1] else k[0]: sorted(str(c) for c in v)
              for k, v in groups.items() if len(v) > 1}
    affected = sorted({c for v in shared.values() for c in v})

    logger.info("--- OOPS! P32: classes with the same label ---")
    for lab, cs in shared.items():
        logger.info(f"  '{lab}': {len(cs)} classes")

    return MetricResult(
        metric_id=mid,
        score=len(affected),
        passed=not affected,
        affected=affected,
        total_examined=len(classes),
        detail={"groups": shared},
        message=(f"{len(shared)} label(s) shared by {len(affected)} classes"
                 if shared else "No two classes share a label"),
    )


# ---------------------------------------------------------------------------
# P41 -- No license declared
# ---------------------------------------------------------------------------

LICENSE_PREDICATES = (
    URIRef("http://purl.org/dc/terms/license"),
    URIRef("http://purl.org/dc/terms/rights"),
    URIRef("http://purl.org/dc/terms/accessRights"),
    URIRef("http://purl.org/dc/elements/1.1/rights"),
    URIRef("http://creativecommons.org/ns#license"),
    URIRef("http://schema.org/license"),
    URIRef("https://schema.org/license"),
    URIRef("http://usefulinc.com/ns/doap#license"),
    URIRef("http://www.w3.org/1999/xhtml/vocab#license"),
)


def oops_p41_no_license_v_0_0_1(ttl_file):
    """
    OOPS! P41 -- No license declared.

    Check that the ontology metadata declares a license.

    Definitions
    -----------
    - License declaration: a value for ``dcterms:license``,
      ``dcterms:rights``, ``dcterms:accessRights``, ``dc:rights``,
      ``cc:license``, ``schema:license``, ``doap:license`` or
      ``xhv:license`` on the ``owl:Ontology`` resource.  This is the union of
      the properties accepted by OOPS! P41 and FOOPS! OM4.1.

    Source
    ------
    OOPS! P41 (important) -- https://oops.linkeddata.es/catalogue.jsp

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when a license is declared.
        ``detail["license"]`` gives the declared values.

    Output Information
    ------------------
    - Declared license values, or the reason none was found

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    OntoCheck's ``humanLicense`` searches all literals and the raw file text
    for license keywords.  P41 requires a machine-readable statement on the
    ontology resource, which is what OOPS! and FOOPS! test.

    Examples
    --------
    >>> r = oops_p41_no_license_v_0_0_1("onto.ttl")  # doctest: +SKIP
    """
    mid = "oopsP41NoLicense"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    onto = _ontology_iri(g)
    subjects = [onto] if onto is not None else list(
        g.subjects(RDF.type, OWL.Ontology))
    values = sorted({str(o) for s in subjects for p in LICENSE_PREDICATES
                     for o in g.objects(s, p) if str(o).strip()})
    ok = bool(values)

    logger.info("--- OOPS! P41: license ---")
    logger.info(f"License: {values or 'none declared'}")

    return MetricResult(
        metric_id=mid,
        score=ok,
        passed=ok,
        affected=[] if ok else ["<no license on owl:Ontology>"],
        total_examined=1,
        detail={"license": values, "ontology": str(onto) if onto else None},
        message=(f"License declared: {values[0]}" if ok
                 else ("No owl:Ontology declaration to carry a license"
                       if not subjects else "No license declared")),
    )


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

def _d(metric_id, name, function, category, source_id, severity, scale,
       description):
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
    )


_LEXICAL_DESCRIPTORS = [
    _d("oopsP01Polysemy", "Polysemous elements",
       oops_p01_polysemous_elements_v_0_0_1, Category.NAMING, "P01",
       Severity.CRITICAL, Scale.COUNT,
       "Punned IRIs and elements with divergent definitions or labels."),
    _d("oopsP02SynonymClasses", "Synonyms as classes",
       oops_p02_synonyms_as_classes_v_0_0_1, Category.NAMING, "P02",
       Severity.MINOR, Scale.COUNT,
       "Distinct classes that are synonyms of each other."),
    _d("oopsP03IsRelationship", "'is' relationship",
       oops_p03_is_relationship_v_0_0_1, Category.STRUCTURAL, "P03",
       Severity.CRITICAL, Scale.COUNT,
       "Properties named 'is' that re-implement OWL/RDFS primitives."),
    _d("oopsP04Unconnected", "Unconnected elements",
       oops_p04_unconnected_elements_v_0_0_1, Category.STRUCTURAL, "P04",
       Severity.MINOR, Scale.COUNT,
       "Own classes and properties in no logical relation."),
    _d("oopsP07MergedConcepts", "Merged concepts in one class",
       oops_p07_merged_concepts_v_0_0_1, Category.NAMING, "P07",
       Severity.MINOR, Scale.COUNT,
       "Class names that join two concepts with 'and'/'or'."),
    _d("oopsP08MissingAnnotations", "Missing annotations",
       oops_p08_missing_annotations_v_0_0_1, Category.LABELING, "P08",
       Severity.MINOR, Scale.COUNT,
       "Own classes and properties without a label or a definition."),
    _d("oopsP11MissingDomainRange", "Missing domain or range",
       oops_p11_missing_domain_range_v_0_0_1, Category.STRUCTURAL, "P11",
       Severity.IMPORTANT, Scale.COUNT,
       "Own properties without domain or range (inverse-aware)."),
    _d("oopsP12UndeclaredEquivProperty", "Equivalent properties not declared",
       oops_p12_undeclared_equivalent_properties_v_0_0_1, Category.STRUCTURAL,
       "P12", Severity.IMPORTANT, Scale.COUNT,
       "Duplicate properties lacking owl:equivalentProperty."),
    _d("oopsP20MisusedAnnotations", "Misused annotations",
       oops_p20_misused_annotations_v_0_0_1, Category.LABELING, "P20",
       Severity.MINOR, Scale.COUNT,
       "Swapped labels/definitions and malformed version or date values."),
    _d("oopsP22NamingConventions", "Different naming conventions",
       oops_p22_naming_conventions_v_0_0_1, Category.NAMING, "P22",
       Severity.MINOR, Scale.COUNT,
       "Elements breaking the majority naming convention of their kind."),
    _d("oopsP23DuplicatedDatatype", "Duplicated datatype",
       oops_p23_duplicated_datatype_v_0_0_1, Category.STRUCTURAL, "P23",
       Severity.IMPORTANT, Scale.COUNT,
       "Classes that re-create an XSD/RDF datatype."),
    _d("oopsP30UndeclaredEquivClass", "Equivalent classes not declared",
       oops_p30_undeclared_equivalent_classes_v_0_0_1, Category.STRUCTURAL,
       "P30", Severity.IMPORTANT, Scale.COUNT,
       "Duplicate classes lacking owl:equivalentClass."),
    _d("oopsP32SameLabel", "Classes with the same label",
       oops_p32_same_label_v_0_0_1, Category.LABELING, "P32",
       Severity.MINOR, Scale.COUNT,
       "Classes sharing an rdfs:label within one language."),
    _d("oopsP41NoLicense", "No license declared",
       oops_p41_no_license_v_0_0_1, Category.METADATA, "P41",
       Severity.IMPORTANT, Scale.BOOLEAN,
       "The owl:Ontology resource declares a license."),
]

for _descriptor in _LEXICAL_DESCRIPTORS:
    register_metric(_descriptor)
