"""
FOOPS!-derived metadata, provenance and term-documentation checks.

Implements the FOOPS! tests that are computable from the ontology graph alone,
without contacting an external registry:

=========  =============================================  =====
Test       Description                                    FAIR
=========  =============================================  =====
FIND1-T    Ontology prefix is declared                    F3
HTTP1-T    Ontology uses an open protocol                 A1.1
OM1-T      Ontology minimum metadata is declared          F2
OM2-T      Ontology declares recommended metadata         R1
OM3-T      Ontology declares detailed metadata            R1
OM5.1-T    Ontology declares basic provenance metadata    R1.2
OM5.2-T    Ontology declares detailed provenance
           metadata                                       R1.2
VOC3-T     All terms have labels                          R1
VOC4-T     All terms have definitions                     R1
=========  =============================================  =====

Relationship to the existing OntoCheck metrics
----------------------------------------------
``checkLabel`` (``mainLabelCheck_v_0_0_1``) and ``definitionCheck``
(``mainDefCheck_v_0_0_1``) examine *named classes* only.  FOOPS! VOC3-T and
VOC4-T require coverage across *all* terms, so properties and named
individuals must be included.  The two metrics here widen the population
rather than modifying the existing functions, which keeps their behaviour and
their CSV output unchanged.  Doing so also strengthens coverage of OOPS! P08
(missing annotations), which is likewise term-wide.

A note on operationalisation
----------------------------
The FOOPS! catalogue names each test and its FAIR principle but does not
publish the annotation-property sets or the weights behind the OM1/OM2/OM3
tiers.  The sets below are therefore OntoCheck's explicit operationalisation,
stated here so that scores are reproducible and auditable, and configurable
through the ``required``, ``recommended`` and ``detailed`` parameters.  Any
published comparison against FOOPS! scores should say which set was used.

Source
------
FOOPS! Metric and Test Catalogue -- https://w3id.org/foops/catalog

Garijo, D., Corcho, O., & Poveda-Villalon, M. (2021). FOOPS!: An Ontology
Pitfall Scanner for the FAIR principles. *ISWC 2021 Posters and Demos*.

Version: 0.0.1

.. note::

   Claude AI (Opus 5) was employed chiefly to support documentation efforts.
"""

import logging
from urllib.parse import urlparse

from rdflib import OWL, RDF, RDFS, SKOS, URIRef
from rdflib.namespace import DCTERMS

from .helpers.oops_helpers import (
    _definitions_of,
    _is_foundational,
    _load_graph,
    _named_classes,
    _named_properties,
    _ontology_iri,
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

_CATALOGUE = "https://w3id.org/foops/catalog"

DC = "http://purl.org/dc/elements/1.1/"
VANN = "http://purl.org/vocab/vann/"
PAV = "http://purl.org/pav/"
PROV = "http://www.w3.org/ns/prov#"
FOAF = "http://xmlns.com/foaf/0.1/"
SCHEMA = "http://schema.org/"
DCAT = "http://www.w3.org/ns/dcat#"


def _u(*uris):
    """
    Build a tuple of ``URIRef`` from string URIs.

    Parameters
    ----------
    *uris : str
        URI strings.

    Returns
    -------
    tuple of rdflib.URIRef
    """
    return tuple(URIRef(u) for u in uris)


# Metadata tiers.  Each entry maps a logical metadata slot to the set of
# predicates that may fill it; a slot counts as present when any one of its
# predicates carries a non-empty value on the ontology declaration.
MINIMUM_METADATA = {
    "title": _u(str(DCTERMS.title), DC + "title", str(RDFS.label)),
    "description": _u(str(DCTERMS.description), DC + "description",
                      str(DCTERMS.abstract), str(RDFS.comment)),
    "creator": _u(str(DCTERMS.creator), DC + "creator",
                  str(DCTERMS.contributor), PAV + "createdBy",
                  PAV + "authoredBy"),
}

RECOMMENDED_METADATA = {
    "license": _u(str(DCTERMS.license), DC + "rights", str(DCTERMS.rights),
                  SCHEMA + "license"),
    "version": _u(str(OWL.versionInfo), str(DCTERMS.hasVersion),
                  PAV + "version", SCHEMA + "version"),
    "date": _u(str(DCTERMS.created), str(DCTERMS.issued),
               str(DCTERMS.modified), DC + "date", PAV + "createdOn"),
    "publisher": _u(str(DCTERMS.publisher), DC + "publisher"),
    "namespace_prefix": _u(VANN + "preferredNamespacePrefix"),
    "namespace_uri": _u(VANN + "preferredNamespaceUri"),
}

DETAILED_METADATA = {
    "citation": _u(str(DCTERMS.bibliographicCitation), SCHEMA + "citation"),
    "source": _u(str(DCTERMS.source), DC + "source",
                 URIRef(PROV + "wasDerivedFrom")),
    "see_also": _u(str(RDFS.seeAlso), FOAF + "homepage", DCAT + "landingPage"),
    "abstract": _u(str(DCTERMS.abstract)),
    "status": _u("http://www.w3.org/2003/06/sw-vocab-status/ns#term_status",
                 str(DCTERMS.accrualPeriodicity)),
    "backward_compatibility": _u(str(OWL.backwardCompatibleWith),
                                 str(OWL.priorVersion)),
}

BASIC_PROVENANCE = {
    "creator": MINIMUM_METADATA["creator"],
    "date": RECOMMENDED_METADATA["date"],
}

DETAILED_PROVENANCE = {
    "created_by": _u(PAV + "createdBy", PAV + "authoredBy",
                     URIRef(PROV + "wasAttributedTo")),
    "created_on": _u(PAV + "createdOn", PAV + "authoredOn",
                     str(DCTERMS.created)),
    "last_updated": _u(PAV + "lastUpdateOn", PAV + "modifiedOn",
                       str(DCTERMS.modified)),
    "derived_from": _u(URIRef(PROV + "wasDerivedFrom"), PAV + "derivedFrom",
                       str(DCTERMS.source)),
    "generated_by": _u(URIRef(PROV + "wasGeneratedBy"),
                       URIRef(PROV + "wasInfluencedBy"),
                       str(DCTERMS.provenance)),
    "imports": _u(str(OWL.imports), PAV + "importedFrom"),
}


def _slots_present(g, subject, slots):
    """
    Determine which metadata slots are filled on a subject.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    subject : rdflib.term.Node
        The ontology declaration, normally the ``owl:Ontology`` IRI.
    slots : dict
        Mapping from slot name to a tuple of acceptable predicates.

    Returns
    -------
    tuple
        ``(present, missing, values)`` where *present* and *missing* are
        sorted lists of slot names and *values* maps each present slot to the
        first non-empty value found.
    """
    present, missing, values = [], [], {}
    for slot, predicates in slots.items():
        found = None
        for pred in predicates:
            for o in g.objects(subject, pred):
                text = str(o).strip()
                if text:
                    found = {"predicate": str(pred), "value": text[:200]}
                    break
            if found:
                break
        if found:
            present.append(slot)
            values[slot] = found
        else:
            missing.append(slot)
    return sorted(present), sorted(missing), values


def _metadata_tier_check(ttl_file, metric_id, tier_name, slots, test_id):
    """
    Shared implementation for the OM1/OM2/OM3 and OM5.x tier checks.

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    metric_id : str
        Registry identifier to stamp on the result.
    tier_name : str
        Human-readable tier name used in log output and messages.
    slots : dict
        Metadata slot definition, as in :data:`MINIMUM_METADATA`.
    test_id : str
        FOOPS! test identifier, for log output.

    Returns
    -------
    MetricResult
        ``score`` is the proportion of slots filled, in [0, 1].  ``passed`` is
        ``True`` only when every slot is filled, matching the FOOPS! tests,
        which are pass/fail.  The proportion is retained because a partial
        score is far more actionable than a bare failure.
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(metric_id=metric_id,
                            status="Error: could not load ontology")

    ontology_iri = _ontology_iri(g)
    if ontology_iri is None:
        logger.info(f"--- FOOPS! {test_id}: {tier_name} ---")
        logger.info("No owl:Ontology declaration; no metadata can be carried.")
        return MetricResult(
            metric_id=metric_id,
            score=0.0,
            passed=False,
            affected=sorted(slots),
            total_examined=len(slots),
            detail={"no_ontology_declaration": True,
                    "missing": sorted(slots), "present": []},
            message=(
                f"No owl:Ontology declaration, so no {tier_name.lower()} is "
                f"present (see OOPS! P38)"
            ),
        )

    present, missing, values = _slots_present(g, ontology_iri, slots)
    proportion = len(present) / len(slots) if slots else 1.0

    logger.info(f"--- FOOPS! {test_id}: {tier_name} ---")
    logger.info(f"Ontology IRI: {ontology_iri}")
    logger.info(f"Slots filled: {len(present)}/{len(slots)} ({proportion:.0%})")
    for slot in present:
        logger.info(f"  [x] {slot}: {values[slot]['value']}")
    for slot in missing:
        logger.info(f"  [ ] {slot}")

    return MetricResult(
        metric_id=metric_id,
        score=round(proportion, 4),
        passed=not missing,
        affected=missing,
        total_examined=len(slots),
        detail={"present": present, "missing": missing, "values": values},
        message=(
            f"{len(present)} of {len(slots)} {tier_name.lower()} slot(s) "
            f"filled" + (f"; missing: {', '.join(missing)}" if missing else "")
        ),
    )


# ---------------------------------------------------------------------------
# OM1-T / OM2-T / OM3-T -- metadata tiers
# ---------------------------------------------------------------------------

def foops_om1_minimum_metadata_v_0_0_1(ttl_file):
    """
    FOOPS! OM1-T -- Ontology minimum metadata is declared.

    Verify that the ontology declaration carries the minimum descriptive
    metadata needed for it to be found and understood.

    Definitions
    -----------
    - Minimum metadata: a title, a description and a creator.  A slot is
      filled when any of its acceptable predicates carries a non-empty value
      on the ontology declaration.

    - Acceptable predicates: ``dcterms:title``/``dc:title``/``rdfs:label`` for
      the title; ``dcterms:description``/``dc:description``/
      ``dcterms:abstract``/``rdfs:comment`` for the description; and
      ``dcterms:creator``/``dc:creator``/``dcterms:contributor``/
      ``pav:createdBy``/``pav:authoredBy`` for the creator.

    Source
    ------
    FOOPS! OM1-T, FAIR principle F2 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the proportion of slots filled; ``passed`` requires all
        of them.  ``detail["missing"]`` names the unfilled slots.

    Notes
    -----
    The predicate sets are OntoCheck's operationalisation of a FOOPS! test
    whose exact term list is not published in the catalogue.  See the module
    docstring.

    Examples
    --------
    >>> result = foops_om1_minimum_metadata_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    return _metadata_tier_check(
        ttl_file, "foopsOM1MinimumMetadata", "Minimum metadata",
        MINIMUM_METADATA, "OM1-T",
    )


def foops_om2_recommended_metadata_v_0_0_1(ttl_file):
    """
    FOOPS! OM2-T -- Ontology declares recommended metadata.

    Verify that the ontology carries the metadata recommended for reuse:
    license, version, date, publisher and preferred namespace prefix and URI.

    Definitions
    -----------
    - Recommended metadata: the six slots ``license``, ``version``, ``date``,
      ``publisher``, ``namespace_prefix`` and ``namespace_uri``.

    - Preferred namespace prefix and URI: ``vann:preferredNamespacePrefix``
      and ``vann:preferredNamespaceUri``, which tell a consumer how the
      ontology expects to be abbreviated.  These also underpin FOOPS! FIND1-T.

    Source
    ------
    FOOPS! OM2-T, FAIR principle R1 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the proportion of the six slots that are filled.

    Notes
    -----
    The ``license`` slot overlaps with the existing ``humanLicense`` metric
    and with OOPS! P41.  It is retained here so that the OM2-T score matches
    the FOOPS! tier definition rather than silently omitting a slot.

    Examples
    --------
    >>> result = foops_om2_recommended_metadata_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    return _metadata_tier_check(
        ttl_file, "foopsOM2RecommendedMetadata", "Recommended metadata",
        RECOMMENDED_METADATA, "OM2-T",
    )


def foops_om3_detailed_metadata_v_0_0_1(ttl_file):
    """
    FOOPS! OM3-T -- Ontology declares detailed metadata.

    Verify that the ontology carries the fuller metadata expected of a
    published, citable artefact.

    Definitions
    -----------
    - Detailed metadata: the six slots ``citation``, ``source``, ``see_also``,
      ``abstract``, ``status`` and ``backward_compatibility``.

    - Backward compatibility: ``owl:backwardCompatibleWith`` or
      ``owl:priorVersion``, which relate a release to the one it supersedes.
      Together with ``owl:versionIRI`` (FOOPS! VER1-T) these are the only
      standard predicates that record an ontology's position in its own
      release history.

    Source
    ------
    FOOPS! OM3-T, FAIR principle R1 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the proportion of the six slots that are filled.

    Examples
    --------
    >>> result = foops_om3_detailed_metadata_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    return _metadata_tier_check(
        ttl_file, "foopsOM3DetailedMetadata", "Detailed metadata",
        DETAILED_METADATA, "OM3-T",
    )


# ---------------------------------------------------------------------------
# OM5.1-T / OM5.2-T -- provenance
# ---------------------------------------------------------------------------

def foops_om51_basic_provenance_v_0_0_1(ttl_file):
    """
    FOOPS! OM5.1-T -- Ontology declares basic provenance metadata.

    Verify that the ontology records who produced it and when.

    Definitions
    -----------
    - Basic provenance: a creator slot and a date slot on the ontology
      declaration.

    - Creator: ``dcterms:creator``, ``dc:creator``, ``dcterms:contributor``,
      ``pav:createdBy`` or ``pav:authoredBy``.

    - Date: ``dcterms:created``, ``dcterms:issued``, ``dcterms:modified``,
      ``dc:date`` or ``pav:createdOn``.

    Source
    ------
    FOOPS! OM5.1-T, FAIR principle R1.2 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the proportion of the two slots that are filled.

    Notes
    -----
    This is ontology-level provenance -- provenance *of the schema*.  It is
    distinct from instance-level evidence provenance, which concerns whether
    individual assertions in a populated graph can be traced to the
    measurement, instrument or sample that produced them.  The latter cannot
    be evaluated over a TBox and is out of scope for every check in OQuaRE,
    OOPS! and FOOPS!.

    Examples
    --------
    >>> result = foops_om51_basic_provenance_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    return _metadata_tier_check(
        ttl_file, "foopsOM51BasicProvenance", "Basic provenance metadata",
        BASIC_PROVENANCE, "OM5.1-T",
    )


def foops_om52_detailed_provenance_v_0_0_1(ttl_file):
    """
    FOOPS! OM5.2-T -- Ontology declares detailed provenance metadata.

    Verify that the ontology records the fuller provenance chain: attribution,
    creation and modification dates, derivation, generation and imports.

    Definitions
    -----------
    - Detailed provenance: the six slots ``created_by``, ``created_on``,
      ``last_updated``, ``derived_from``, ``generated_by`` and ``imports``,
      drawn from PAV, PROV-O, Dublin Core Terms and OWL.

    - Derivation: ``prov:wasDerivedFrom``, ``pav:derivedFrom`` or
      ``dcterms:source`` -- the artefacts this ontology was built from.

    - Imports: ``owl:imports`` or ``pav:importedFrom`` -- the ontologies whose
      axioms this one incorporates, which is what makes an assessment
      reproducible against the same dependency set.

    Source
    ------
    FOOPS! OM5.2-T, FAIR principle R1.2 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the proportion of the six slots that are filled.

    Examples
    --------
    >>> result = foops_om52_detailed_provenance_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    return _metadata_tier_check(
        ttl_file, "foopsOM52DetailedProvenance",
        "Detailed provenance metadata", DETAILED_PROVENANCE, "OM5.2-T",
    )


# ---------------------------------------------------------------------------
# FIND1-T -- ontology prefix declared
# ---------------------------------------------------------------------------

def foops_find1_prefix_declared_v_0_0_1(ttl_file):
    """
    FOOPS! FIND1-T -- Ontology prefix is declared.

    Verify that the ontology states the prefix it expects to be abbreviated
    with, via ``vann:preferredNamespacePrefix``.

    Definitions
    -----------
    - Declared prefix: a ``vann:preferredNamespacePrefix`` value on the
      ontology declaration, optionally paired with
      ``vann:preferredNamespaceUri``.

    - Serialisation prefix: a ``@prefix`` binding in the Turtle file.  These
      are a property of the file, not of the ontology, and any consumer may
      rename them, so their presence does not satisfy FIND1-T.  They are
      reported separately as supporting evidence.

    - Consistency: when both ``vann:preferredNamespacePrefix`` and
      ``vann:preferredNamespaceUri`` are present, the declared URI should
      match the ontology's own namespace.  A mismatch is reported.

    Source
    ------
    FOOPS! FIND1-T, FAIR principle F3 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is ``True`` when a preferred namespace prefix is declared.
        ``detail`` records the declared prefix and URI, the serialisation
        prefix bound to the ontology namespace if any, and whether the
        declared URI matches the inferred own namespace.

    Examples
    --------
    >>> result = foops_find1_prefix_declared_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(metric_id="foopsFIND1PrefixDeclared",
                            status="Error: could not load ontology")

    ontology_iri = _ontology_iri(g)
    own_ns = _own_namespace(g)

    declared_prefix, declared_uri = None, None
    if ontology_iri is not None:
        for o in g.objects(ontology_iri,
                           URIRef(VANN + "preferredNamespacePrefix")):
            declared_prefix = str(o).strip()
            break
        for o in g.objects(ontology_iri,
                           URIRef(VANN + "preferredNamespaceUri")):
            declared_uri = str(o).strip()
            break

    serialisation_prefix = None
    if own_ns:
        for prefix, namespace in g.namespaces():
            owned = own_ns if isinstance(own_ns, tuple) else (own_ns,)
            if str(namespace) in owned and prefix:
                serialisation_prefix = prefix
                break

    present = bool(declared_prefix)
    uri_matches = (
        declared_uri is not None and own_ns is not None
        and declared_uri.rstrip("#/") in {
            n.rstrip("#/")
            for n in (own_ns if isinstance(own_ns, tuple) else (own_ns,))
        }
    )

    logger.info("--- FOOPS! FIND1-T: ontology prefix declared ---")
    logger.info(f"vann:preferredNamespacePrefix: {declared_prefix}")
    logger.info(f"vann:preferredNamespaceUri: {declared_uri}")
    logger.info(f"Serialisation prefix for the own namespace: "
                f"{serialisation_prefix}")
    if declared_uri and not uri_matches:
        logger.info(
            f"Declared namespace URI does not match the inferred own "
            f"namespace ({own_ns})."
        )

    return MetricResult(
        metric_id="foopsFIND1PrefixDeclared",
        score=present,
        passed=present,
        affected=[] if present else ["<no vann:preferredNamespacePrefix>"],
        total_examined=1,
        detail={
            "declared_prefix": declared_prefix,
            "declared_uri": declared_uri,
            "serialisation_prefix": serialisation_prefix,
            "own_namespace": own_ns,
            "declared_uri_matches_own_namespace": uri_matches,
        },
        message=(
            f"Preferred namespace prefix declared ('{declared_prefix}')"
            if present else
            (
                f"No vann:preferredNamespacePrefix; the file binds "
                f"'{serialisation_prefix}:' in its serialisation only"
                if serialisation_prefix
                else "No preferred namespace prefix declared"
            )
        ),
    )


# ---------------------------------------------------------------------------
# HTTP1-T -- open protocol
# ---------------------------------------------------------------------------

_OPEN_SCHEMES = ("http", "https")


def foops_http1_open_protocol_v_0_0_1(ttl_file):
    """
    FOOPS! HTTP1-T -- Ontology uses an open protocol.

    Verify that the ontology IRI is retrievable over a free, open and
    universally implementable protocol.

    Definitions
    -----------
    - Open protocol: the URI scheme is ``http`` or ``https``.  A ``file:``,
      ``urn:``, ``ftp:`` or bare-path identifier cannot be dereferenced by an
      arbitrary consumer.

    - Term URIs: the scheme of every named class and property is also
      examined, since an ontology may be published over HTTP while minting
      terms under a non-dereferenceable scheme.

    Source
    ------
    FOOPS! HTTP1-T, FAIR principle A1.1 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is ``True`` when the ontology IRI uses an open protocol.
        ``detail["scheme"]`` gives that scheme, and
        ``detail["non_open_terms"]`` lists any terms that do not.

    Notes
    -----
    This check inspects the scheme only.  Whether the IRI actually resolves is
    FOOPS! URI1-T, and whether it serves RDF under content negotiation is
    CN1-T; both require network access and are registered separately.

    Examples
    --------
    >>> result = foops_http1_open_protocol_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(metric_id="foopsHTTP1OpenProtocol",
                            status="Error: could not load ontology")

    ontology_iri = _ontology_iri(g)
    if ontology_iri is None:
        logger.info("--- FOOPS! HTTP1-T: open protocol ---")
        logger.info("No owl:Ontology declaration; no IRI scheme to inspect.")
        return MetricResult(
            metric_id="foopsHTTP1OpenProtocol",
            score=False,
            passed=False,
            affected=["<no owl:Ontology declaration>"],
            total_examined=0,
            detail={"no_ontology_declaration": True},
            message="No owl:Ontology declaration (see OOPS! P38)",
        )

    scheme = urlparse(str(ontology_iri)).scheme.lower()
    open_protocol = scheme in _OPEN_SCHEMES

    non_open_terms = []
    terms = _named_classes(g) | _named_properties(g)
    for t in sorted(terms, key=str):
        if _is_foundational(t):
            continue
        term_scheme = urlparse(str(t)).scheme.lower()
        if term_scheme not in _OPEN_SCHEMES:
            non_open_terms.append(str(t))

    logger.info("--- FOOPS! HTTP1-T: open protocol ---")
    logger.info(f"Ontology IRI scheme: {scheme or '<none>'}")
    logger.info(f"Terms using a non-open scheme: {len(non_open_terms)}")

    return MetricResult(
        metric_id="foopsHTTP1OpenProtocol",
        score=open_protocol,
        passed=open_protocol and not non_open_terms,
        affected=([] if open_protocol else [str(ontology_iri)])
        + non_open_terms[:50],
        total_examined=len(terms) + 1,
        detail={
            "scheme": scheme,
            "ontology_iri": str(ontology_iri),
            "non_open_terms": non_open_terms,
            "non_open_term_count": len(non_open_terms),
        },
        message=(
            f"Ontology IRI uses '{scheme}'"
            + (f"; {len(non_open_terms)} term(s) do not use an open protocol"
               if non_open_terms else "")
        ),
    )


# ---------------------------------------------------------------------------
# VOC3-T / VOC4-T -- term-wide label and definition coverage
# ---------------------------------------------------------------------------

def _all_terms(g):
    """
    Collect every term the ontology mints: classes, properties, individuals.

    Definitions
    -----------
    - Term: a named class, a named property, or a named individual declared
      ``owl:NamedIndividual``.

    - Own terms: only terms in the ontology's own namespace are counted.
      Terms drawn from imported vocabularies are documented by their own
      publishers, and counting them would make coverage depend on how many
      upper-level terms happen to be referenced.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    tuple
        ``(own_terms, external_terms)``, each a sorted list of ``URIRef``.
    """
    terms = _named_classes(g) | _named_properties(g)
    for s in g.subjects(RDF.type, OWL.NamedIndividual):
        if isinstance(s, URIRef):
            terms.add(s)

    own_ns = _own_namespace(g)
    own, external = [], []
    for t in sorted(terms, key=str):
        if _is_foundational(t):
            continue
        if own_ns and str(t).startswith(own_ns):
            own.append(t)
        else:
            external.append(t)
    return own, external


def foops_voc3_all_terms_labelled_v_0_0_1(ttl_file):
    """
    FOOPS! VOC3-T -- Ontology documentation: all terms have labels.

    Measure ``rdfs:label`` coverage across every term the ontology mints, not
    only its named classes.

    Definitions
    -----------
    - Term: a named class, named property or named individual in the
      ontology's own namespace.

    - Valid label: a non-empty ``rdfs:label``, ``skos:prefLabel`` or
      ``dcterms:title`` value after whitespace trimming.

    - Coverage: the proportion of own terms carrying at least one valid label.

    Relationship to ``checkLabel``
    ------------------------------
    The existing ``mainLabelCheck_v_0_0_1`` examines named classes only, so it
    cannot satisfy VOC3-T, which is term-wide.  This metric widens the
    population to properties and individuals and reports the class-only and
    property-only figures separately in ``detail``, so the two can be
    reconciled.  It also strengthens coverage of OOPS! P08.

    Source
    ------
    FOOPS! VOC3-T, FAIR principle R1 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is label coverage in [0, 1]; ``passed`` requires complete
        coverage.  ``affected`` lists unlabelled terms, and ``detail`` breaks
        coverage down by term kind.

    Output Information
    ------------------
    - Coverage across all own terms, and separately for classes, properties
      and individuals
    - The list of unlabelled terms
    - The count of external terms excluded from the calculation

    Examples
    --------
    >>> result = foops_voc3_all_terms_labelled_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    >>> result.detail["class_coverage"]                                 # doctest: +SKIP
    0.94
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(metric_id="foopsVOC3AllTermsLabelled",
                            status="Error: could not load ontology")

    own, external = _all_terms(g)
    classes = _named_classes(g)
    properties = _named_properties(g)

    label_predicates = (RDFS.label, SKOS.prefLabel, DCTERMS.title)

    def has_label(term):
        for pred in label_predicates:
            for o in g.objects(term, pred):
                if str(o).strip():
                    return True
        return False

    unlabelled, kind_totals, kind_labelled = [], {}, {}
    for term in own:
        if term in classes:
            kind = "class"
        elif term in properties:
            kind = "property"
        else:
            kind = "individual"
        kind_totals[kind] = kind_totals.get(kind, 0) + 1
        if has_label(term):
            kind_labelled[kind] = kind_labelled.get(kind, 0) + 1
        else:
            unlabelled.append(str(term))

    total = len(own)
    labelled = total - len(unlabelled)
    coverage = (labelled / total) if total else 1.0

    def kind_coverage(kind):
        t = kind_totals.get(kind, 0)
        return round(kind_labelled.get(kind, 0) / t, 4) if t else None

    logger.info("--- FOOPS! VOC3-T: all terms have labels ---")
    logger.info(f"Own terms examined: {total} "
                f"({external and len(external) or 0} external terms excluded)")
    logger.info(f"Label coverage: {coverage:.2%}")
    for kind in sorted(kind_totals):
        logger.info(f"  {kind}: {kind_labelled.get(kind, 0)}/"
                    f"{kind_totals[kind]}")
    for term in unlabelled[:50]:
        logger.info(f"  unlabelled: {term}")

    return MetricResult(
        metric_id="foopsVOC3AllTermsLabelled",
        score=round(coverage, 4),
        passed=not unlabelled,
        affected=unlabelled,
        total_examined=total,
        detail={
            "class_coverage": kind_coverage("class"),
            "property_coverage": kind_coverage("property"),
            "individual_coverage": kind_coverage("individual"),
            "counts_by_kind": kind_totals,
            "labelled_by_kind": kind_labelled,
            "external_terms_excluded": len(external),
        },
        message=(
            f"{labelled}/{total} own terms carry a label ({coverage:.1%})"
        ),
    )


def foops_voc4_all_terms_defined_v_0_0_1(ttl_file):
    """
    FOOPS! VOC4-T -- Ontology documentation: all terms have definitions.

    Measure textual-definition coverage across every term the ontology mints,
    not only its named classes.

    Definitions
    -----------
    - Term: a named class, named property or named individual in the
      ontology's own namespace.

    - Valid definition: a non-empty ``skos:definition``, ``rdfs:comment``,
      ``obo:IAO_0000115`` or Dublin Core ``description`` value.

    - Coverage: the proportion of own terms carrying at least one valid
      definition.

    Relationship to ``definitionCheck``
    -----------------------------------
    As with VOC3-T, the existing ``mainDefCheck_v_0_0_1`` examines named
    classes only and therefore cannot satisfy this term-wide test.  Property
    and individual coverage are reported separately in ``detail``.

    Source
    ------
    FOOPS! VOC4-T, FAIR principle R1 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is definition coverage in [0, 1]; ``passed`` requires
        complete coverage.

    Notes
    -----
    Properties are frequently the weakest population here.  A property defined
    with a domain, a range and a label but no prose definition leaves its
    intended reading to be guessed from its name, which is precisely the
    condition that makes competency-question SPARQL fragile.

    Examples
    --------
    >>> result = foops_voc4_all_terms_defined_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(metric_id="foopsVOC4AllTermsDefined",
                            status="Error: could not load ontology")

    own, external = _all_terms(g)
    classes = _named_classes(g)
    properties = _named_properties(g)

    undefined, kind_totals, kind_defined = [], {}, {}
    for term in own:
        if term in classes:
            kind = "class"
        elif term in properties:
            kind = "property"
        else:
            kind = "individual"
        kind_totals[kind] = kind_totals.get(kind, 0) + 1
        if _definitions_of(g, term):
            kind_defined[kind] = kind_defined.get(kind, 0) + 1
        else:
            undefined.append(str(term))

    total = len(own)
    defined = total - len(undefined)
    coverage = (defined / total) if total else 1.0

    def kind_coverage(kind):
        t = kind_totals.get(kind, 0)
        return round(kind_defined.get(kind, 0) / t, 4) if t else None

    logger.info("--- FOOPS! VOC4-T: all terms have definitions ---")
    logger.info(f"Own terms examined: {total}")
    logger.info(f"Definition coverage: {coverage:.2%}")
    for kind in sorted(kind_totals):
        logger.info(f"  {kind}: {kind_defined.get(kind, 0)}/"
                    f"{kind_totals[kind]}")
    for term in undefined[:50]:
        logger.info(f"  undefined: {term}")

    return MetricResult(
        metric_id="foopsVOC4AllTermsDefined",
        score=round(coverage, 4),
        passed=not undefined,
        affected=undefined,
        total_examined=total,
        detail={
            "class_coverage": kind_coverage("class"),
            "property_coverage": kind_coverage("property"),
            "individual_coverage": kind_coverage("individual"),
            "counts_by_kind": kind_totals,
            "defined_by_kind": kind_defined,
            "external_terms_excluded": len(external),
        },
        message=(
            f"{defined}/{total} own terms carry a definition ({coverage:.1%})"
        ),
    )


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

_METADATA_DESCRIPTORS = [
    MetricDescriptor(
        metric_id="foopsFIND1PrefixDeclared",
        name="Ontology prefix declared",
        function=foops_find1_prefix_declared_v_0_0_1,
        category=Category.METADATA,
        source_framework=SourceFramework.FOOPS,
        source_id="FIND1-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.BOOLEAN,
        higher_is_better=True,
        fair_principle="F3",
        description="vann:preferredNamespacePrefix is declared.",
    ),
    MetricDescriptor(
        metric_id="foopsHTTP1OpenProtocol",
        name="Open protocol",
        function=foops_http1_open_protocol_v_0_0_1,
        category=Category.ACCESSIBILITY,
        source_framework=SourceFramework.FOOPS,
        source_id="HTTP1-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.BOOLEAN,
        higher_is_better=True,
        fair_principle="A1.1",
        description="The ontology IRI uses http or https.",
    ),
    MetricDescriptor(
        metric_id="foopsOM1MinimumMetadata",
        name="Minimum metadata",
        function=foops_om1_minimum_metadata_v_0_0_1,
        category=Category.METADATA,
        source_framework=SourceFramework.FOOPS,
        source_id="OM1-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.PROPORTION,
        higher_is_better=True,
        fair_principle="F2",
        description="Title, description and creator are declared.",
    ),
    MetricDescriptor(
        metric_id="foopsOM2RecommendedMetadata",
        name="Recommended metadata",
        function=foops_om2_recommended_metadata_v_0_0_1,
        category=Category.METADATA,
        source_framework=SourceFramework.FOOPS,
        source_id="OM2-T",
        source_url=_CATALOGUE,
        severity=Severity.MINOR,
        scale=Scale.PROPORTION,
        higher_is_better=True,
        fair_principle="R1",
        description="License, version, date, publisher and namespace "
                    "declarations.",
    ),
    MetricDescriptor(
        metric_id="foopsOM3DetailedMetadata",
        name="Detailed metadata",
        function=foops_om3_detailed_metadata_v_0_0_1,
        category=Category.METADATA,
        source_framework=SourceFramework.FOOPS,
        source_id="OM3-T",
        source_url=_CATALOGUE,
        severity=Severity.MINOR,
        scale=Scale.PROPORTION,
        higher_is_better=True,
        fair_principle="R1",
        description="Citation, source, see-also, abstract, status and "
                    "backward compatibility.",
    ),
    MetricDescriptor(
        metric_id="foopsOM51BasicProvenance",
        name="Basic provenance metadata",
        function=foops_om51_basic_provenance_v_0_0_1,
        category=Category.PROVENANCE,
        source_framework=SourceFramework.FOOPS,
        source_id="OM5.1-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.PROPORTION,
        higher_is_better=True,
        fair_principle="R1.2",
        description="Creator and date are declared on the ontology.",
    ),
    MetricDescriptor(
        metric_id="foopsOM52DetailedProvenance",
        name="Detailed provenance metadata",
        function=foops_om52_detailed_provenance_v_0_0_1,
        category=Category.PROVENANCE,
        source_framework=SourceFramework.FOOPS,
        source_id="OM5.2-T",
        source_url=_CATALOGUE,
        severity=Severity.MINOR,
        scale=Scale.PROPORTION,
        higher_is_better=True,
        fair_principle="R1.2",
        description="PAV/PROV attribution, derivation, generation and "
                    "imports.",
    ),
    MetricDescriptor(
        metric_id="foopsVOC3AllTermsLabelled",
        name="All terms have labels",
        function=foops_voc3_all_terms_labelled_v_0_0_1,
        category=Category.LABELING,
        source_framework=SourceFramework.FOOPS,
        source_id="VOC3-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.PROPORTION,
        higher_is_better=True,
        fair_principle="R1",
        description="Label coverage across classes, properties and "
                    "individuals.",
    ),
    MetricDescriptor(
        metric_id="foopsVOC4AllTermsDefined",
        name="All terms have definitions",
        function=foops_voc4_all_terms_defined_v_0_0_1,
        category=Category.LABELING,
        source_framework=SourceFramework.FOOPS,
        source_id="VOC4-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.PROPORTION,
        higher_is_better=True,
        fair_principle="R1",
        description="Definition coverage across classes, properties and "
                    "individuals.",
    ),
]

for _descriptor in _METADATA_DESCRIPTORS:
    register_metric(_descriptor)
