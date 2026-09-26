"""
FOOPS!-derived accessibility, findability, licensing and reuse tests.

Completes OntoCheck's coverage of the FOOPS! test catalogue.  Together with
``foops_metadata_checks`` (FIND1, HTTP1, OM1, OM2, OM3, OM5.1, OM5.2, VOC3,
VOC4) and ``foops_version_checks`` (VER1, VER2), all 24 FOOPS! tests are now
implemented.

Tests implemented here
----------------------
===========  ====================================================  =====  =======
Test         Title                                                 FAIR   Network
===========  ====================================================  =====  =======
CN1-T        Content negotiation for RDF and HTML                  A1     yes
DOC1-T       Ontology has HTML documentation                       R1     yes
FIND2-T      Ontology prefix found in prefix.cc or LOV             F4     yes
FIND3-T      Ontology found in a community registry                F4     yes
FIND_3_BIS   Metadata accessible even when the ontology is not     A2     yes
OM4.1-T      Ontology has a license available                      R1.1   no
OM4.2-T      Ontology license is resolvable                        R1.1   yes
PURL1-T      Ontology has a persistent URL                         F1     no
RDF1-T       Ontology is available in RDF                          I1     no
URI1-T       Ontology URI is resolvable                            F1     yes
URI2-T       Consistent ontology IDs are employed                  F1     yes
VOC1-T       Metadata annotations reuse existing vocabularies      I2     no
VOC2-T       Ontology imports or reuses established vocabularies   I2     no
===========  ====================================================  =====  =======

Network tests are registered with ``requires_network=True`` and are skipped,
with that reason, when assessment runs offline.

Source
------
FOOPS! test catalogue -- https://w3id.org/foops/catalog (per-test pages at
``https://w3id.org/foops/test/<ID>``).

Garijo, D., Corcho, O., & Poveda-Villalon, M. (2021).  FOOPS!: An ontology
pitfall scanner for the FAIR principles.  *ISWC 2021 Posters and Demos*,
CEUR-WS 2980.

Version: 0.0.1

.. note::

   Claude AI (Opus 5) was employed chiefly to support documentation efforts.
"""

import logging
import re

from rdflib import Graph, OWL, RDF, RDFS, URIRef

from .helpers.oops_helpers import (
    _load_graph,
    _namespace_of,
    _ontology_iri,
    _own_namespace,
)
from .helpers.semantic_helpers import (
    RDF_MEDIA_TYPES,
    _http_get,
    _object_and_datatype_properties,
    _parse_rdf_response,
)
from .helpers.oops_helpers import _named_classes
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
_TEST_URL = "https://w3id.org/foops/test/{}"

VANN = "http://purl.org/vocab/vann/"
SCHEMA_CATALOG = (URIRef("http://schema.org/includedInDataCatalog"),
                  URIRef("https://schema.org/includedInDataCatalog"))
LOV_LIST_URL = "https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/list"
PREFIXCC_URL = "https://prefix.cc/{}.file.json"

# FOOPS! OM4.1 accepted predicates.
LICENSE_PROPERTIES = (
    URIRef("http://purl.org/dc/terms/license"),
    URIRef("http://schema.org/license"),
    URIRef("https://schema.org/license"),
    URIRef("http://usefulinc.com/ns/doap#license"),
    URIRef("http://creativecommons.org/ns#license"),
)
RIGHTS_PROPERTIES = (
    URIRef("http://purl.org/dc/elements/1.1/rights"),
    URIRef("http://purl.org/dc/terms/rights"),
    URIRef("http://purl.org/dc/terms/accessRights"),
)

# FOOPS! PURL1 accepted persistent-identifier schemes.
PERSISTENT_HOSTS = (
    r"w3id\.org", r"doi\.org", r"purl\.org", r"purl\.[a-z0-9\-]+\.org",
    r"linked\.data\.gov\.au", r"dbpedia\.org", r"www\.w3\.org", r"perma\.cc",
    r"data\.europa\.eu",
)

# FOOPS! VOC1 accepted metadata vocabularies.
METADATA_VOCABULARIES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "schema": ("http://schema.org/", "https://schema.org/"),
    "vann": "http://purl.org/vocab/vann/",
    "prov": "http://www.w3.org/ns/prov#",
    "bibo": "http://purl.org/ontology/bibo/",
    "pav": "http://purl.org/pav/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "doap": "http://usefulinc.com/ns/doap#",
    "mod": "https://w3id.org/mod#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}

_CORE_NS = (str(RDF), str(RDFS), str(OWL),
            "http://www.w3.org/2001/XMLSchema#",
            "http://www.w3.org/XML/1998/namespace")

_RDF_ACCEPT = ("text/turtle, application/rdf+xml;q=0.9, "
               "application/ld+json;q=0.8, application/n-triples;q=0.7")


def _load_error(metric_id):
    """
    Build the result returned when an ontology cannot be loaded.

    Parameters
    ----------
    metric_id : str
        Registry identifier of the calling test.

    Returns
    -------
    MetricResult
        Result with an ``"Error:"`` status.
    """
    return MetricResult(metric_id=metric_id,
                        status="Error: could not load ontology")


def _ontology_uri(g):
    """
    Return the URI FOOPS! would assess.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    str or None
        The ``owl:Ontology`` IRI, or ``None`` when the ontology declares none
        (FOOPS! then has nothing to dereference).
    """
    iri = _ontology_iri(g)
    return str(iri) if iri is not None else None


def _no_uri(metric_id):
    """
    Build the failing result for a test that needs an ontology URI.

    Parameters
    ----------
    metric_id : str
        Registry identifier of the calling test.

    Returns
    -------
    MetricResult
        Failing result explaining that no ``owl:Ontology`` IRI is declared.
    """
    return MetricResult(metric_id=metric_id, score=False, passed=False,
                        affected=["<no owl:Ontology IRI>"], total_examined=1,
                        message="No ontology URI declared; nothing to "
                                "dereference")


def _strip(response):
    """
    Drop the body from an HTTP response record before storing it.

    Parameters
    ----------
    response : dict
        Result of ``_http_get``.

    Returns
    -------
    dict
        The same record without the ``text`` key.
    """
    return {k: v for k, v in response.items() if k != "text"}


# ---------------------------------------------------------------------------
# CN1 -- Content negotiation
# ---------------------------------------------------------------------------

def foops_cn1_content_negotiation_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! CN1-T -- The ontology has content negotiation for RDF and HTML.

    Request the ontology URI once per media type and check that HTML and at
    least one RDF serialisation are served.

    Definitions
    -----------
    - RDF serialisations: RDF/XML (``application/rdf+xml``), Turtle
      (``text/turtle``), N-Triples (``application/n-triples``, also
      ``text/n3``) and JSON-LD (``application/ld+json``).

    - Served: the request succeeds (status < 400), the response
      ``Content-Type`` matches the requested type, and, for RDF, the body
      parses.

    - Pass: HTML and at least one RDF serialisation are served.

    Source
    ------
    FOOPS! CN1-T, FAIR principle A1 -- https://w3id.org/foops/test/CN1

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file whose URI is tested.
    timeout : int or float, optional
        Per-request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` on success.
        ``detail["served"]`` maps each media type to ``True``/``False``.

    Output Information
    ------------------
    - Media types served and their HTTP outcome

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - An ontology without an IRI fails with an explanatory message.

    Examples
    --------
    >>> r = foops_cn1_content_negotiation_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsCN1ContentNegotiation"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    uri = _ontology_uri(g)
    if uri is None:
        return _no_uri(mid)

    served, responses = {}, {}
    for media in list(RDF_MEDIA_TYPES) + ["text/html"]:
        r = _http_get(uri, media, timeout)
        responses[media] = _strip(r)
        if media == "text/html":
            served[media] = bool(r["status"] and r["status"] < 400
                                 and r["content_type"] == "text/html")
        else:
            served[media] = (r["content_type"] in RDF_MEDIA_TYPES
                             and _parse_rdf_response(r) is not None)
    rdf_ok = any(v for k, v in served.items() if k != "text/html")
    ok = rdf_ok and served["text/html"]

    logger.info("--- FOOPS! CN1-T: content negotiation ---")
    for k, v in served.items():
        logger.info(f"  {k}: {v}")

    return MetricResult(
        metric_id=mid, score=ok, passed=ok,
        affected=[] if ok else [uri], total_examined=len(served),
        detail={"uri": uri, "served": served, "responses": responses},
        message=("HTML and RDF are served by content negotiation" if ok
                 else "Missing: " + ", ".join(
                     x for x, good in (("HTML", served["text/html"]),
                                       ("RDF", rdf_ok)) if not good)),
    )


# ---------------------------------------------------------------------------
# DOC1 -- HTML documentation
# ---------------------------------------------------------------------------

def foops_doc1_html_documentation_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! DOC1-T -- The ontology has HTML documentation.

    Request the ontology URI with ``Accept: text/html``.

    Definitions
    -----------
    - HTML documentation: a successful (status < 400) response whose
      ``Content-Type`` is ``text/html``.

    Source
    ------
    FOOPS! DOC1-T, FAIR principle R1 -- https://w3id.org/foops/test/DOC1

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file whose URI is tested.
    timeout : int or float, optional
        Request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when HTML is served.

    Output Information
    ------------------
    - Status code, final URL and media type of the response

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - An ontology without an IRI fails with an explanatory message.

    Examples
    --------
    >>> r = foops_doc1_html_documentation_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsDOC1HtmlDocumentation"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    uri = _ontology_uri(g)
    if uri is None:
        return _no_uri(mid)
    r = _http_get(uri, "text/html", timeout)
    ok = bool(r["status"] and r["status"] < 400
              and r["content_type"] == "text/html")
    logger.info("--- FOOPS! DOC1-T: HTML documentation ---")
    logger.info(f"{uri}: {r['status']} {r['content_type']} {r['error'] or ''}")
    return MetricResult(
        metric_id=mid, score=ok, passed=ok, affected=[] if ok else [uri],
        total_examined=1, detail={"uri": uri, "response": _strip(r)},
        message=("HTML documentation is served" if ok
                 else f"No HTML documentation at {uri} "
                      f"({r['error'] or r['status']})"),
    )


# ---------------------------------------------------------------------------
# FIND2 -- Prefix registered in prefix.cc or LOV
# ---------------------------------------------------------------------------

def _declared_prefix(g):
    """
    Return the prefix and namespace URI the ontology declares for itself.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    tuple
        ``(prefix, namespace_uri)``; either may be ``None``.  The prefix is
        read from ``vann:preferredNamespacePrefix``; FOOPS! FIND1 requires
        that property, so FIND2 does too.
    """
    onto = _ontology_iri(g)
    if onto is None:
        return None, None
    prefix = g.value(onto, URIRef(VANN + "preferredNamespacePrefix"))
    ns = g.value(onto, URIRef(VANN + "preferredNamespaceUri"))
    return (str(prefix).strip() if prefix else None,
            str(ns).strip() if ns else None)


def _lov_vocabularies(timeout):
    """
    Download the Linked Open Vocabularies catalogue.

    Parameters
    ----------
    timeout : int or float
        Request timeout in seconds.

    Returns
    -------
    tuple
        ``(vocabularies, error)`` where ``vocabularies`` is a list of dicts
        with ``uri``, ``nsp`` and ``prefix`` keys (``None`` on failure).
    """
    import json
    r = _http_get(LOV_LIST_URL, "application/json", timeout)
    if r["error"] or not r["text"]:
        return None, r["error"] or f"HTTP {r['status']}"
    try:
        return json.loads(r["text"]), None
    except ValueError as e:
        return None, f"invalid JSON from LOV: {e}"


def _same_uri(a, b):
    """
    Compare two namespace or ontology URIs, ignoring trailing delimiters.

    Parameters
    ----------
    a, b : str or None
        URIs.

    Returns
    -------
    bool
        ``True`` when both are given and equal after stripping ``#`` and
        ``/`` from the end and normalising ``https`` to ``http``.
    """
    if not a or not b:
        return False
    norm = lambda u: re.sub(r"^https://", "http://", u).rstrip("#/")  # noqa: E731
    return norm(a) == norm(b)


def foops_find2_prefix_registered_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! FIND2-T -- The ontology prefix is found in prefix.cc or LOV.

    Look up the ontology's declared prefix in the two public prefix
    registries and check that the registered namespace is the ontology's.

    Definitions
    -----------
    - Declared prefix: ``vann:preferredNamespacePrefix`` on the ontology.

    - Registered: prefix.cc (``https://prefix.cc/<prefix>.file.json``) or
      the LOV vocabulary list maps the prefix to a namespace.

    - Pass: a prefix is declared, it is registered, and the registered
      namespace equals the ontology URI or its declared namespace URI.

    Source
    ------
    FOOPS! FIND2-T, FAIR principle F4 -- https://w3id.org/foops/test/FIND2

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
        ``score`` and ``passed`` are ``True`` on success.  ``detail``
        records the registry answers.

    Output Information
    ------------------
    - Declared prefix, registry matches and namespace comparison

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - Registry errors are recorded in ``detail`` and count as "not found".

    Examples
    --------
    >>> r = foops_find2_prefix_registered_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    import json
    mid = "foopsFIND2PrefixRegistered"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    prefix, ns = _declared_prefix(g)
    uri = _ontology_uri(g)
    if not prefix:
        return MetricResult(metric_id=mid, score=False, passed=False,
                            affected=["<no vann:preferredNamespacePrefix>"],
                            total_examined=1,
                            detail={"prefix": None},
                            message="No prefix declared (see FIND1-T), so "
                                    "no registry lookup was possible")

    registered = {}
    r = _http_get(PREFIXCC_URL.format(prefix), "application/json", timeout)
    if r["text"]:
        try:
            registered["prefix.cc"] = json.loads(r["text"]).get(prefix)
        except ValueError:
            registered["prefix.cc"] = None
    errors = {"prefix.cc": r["error"]}
    lov, lov_err = _lov_vocabularies(timeout)
    errors["lov"] = lov_err
    if lov:
        hit = next((v for v in lov if v.get("prefix") == prefix), None)
        registered["lov"] = hit.get("nsp") if hit else None

    matches = {k: v for k, v in registered.items()
               if v and (_same_uri(v, uri) or _same_uri(v, ns))}
    ok = bool(matches)

    logger.info("--- FOOPS! FIND2-T: prefix registered ---")
    logger.info(f"Prefix '{prefix}': {registered}; errors: {errors}")

    return MetricResult(
        metric_id=mid, score=ok, passed=ok,
        affected=[] if ok else [prefix], total_examined=1,
        detail={"prefix": prefix, "registered": registered,
                "matches": matches, "errors": errors},
        message=(f"Prefix '{prefix}' is registered for this ontology in "
                 f"{', '.join(matches)}" if ok
                 else f"Prefix '{prefix}' not registered for this ontology"),
    )


# ---------------------------------------------------------------------------
# FIND3 and FIND_3_BIS -- Community registry
# ---------------------------------------------------------------------------

def _registry_check(ttl_file, metric_id, timeout):
    """
    Shared implementation of FIND3-T and FIND_3_BIS-T.

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    metric_id : str
        Registry identifier of the calling test.
    timeout : int or float
        Request timeout in seconds.

    Returns
    -------
    MetricResult
        Passing when ``schema:includedInDataCatalog`` is declared or the
        ontology URI is listed in LOV.
    """
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(metric_id)
    uri = _ontology_uri(g)
    onto = _ontology_iri(g)
    catalogs = sorted({str(o) for p in SCHEMA_CATALOG
                       for o in g.objects(onto, p)}) if onto is not None else []
    in_lov, lov_err = False, None
    if not catalogs and uri:
        lov, lov_err = _lov_vocabularies(timeout)
        if lov:
            in_lov = any(_same_uri(v.get("uri"), uri)
                         or _same_uri(v.get("nsp"), uri) for v in lov)
    ok = bool(catalogs) or in_lov
    return MetricResult(
        metric_id=metric_id, score=ok, passed=ok,
        affected=[] if ok else [uri or "<no owl:Ontology IRI>"],
        total_examined=1,
        detail={"uri": uri, "includedInDataCatalog": catalogs,
                "in_lov": in_lov, "lov_error": lov_err},
        message=("Registered: " + (f"schema:includedInDataCatalog "
                                   f"{catalogs[0]}" if catalogs else "LOV")
                 if ok else "Not found in LOV and no "
                            "schema:includedInDataCatalog declared"),
    )


def foops_find3_community_registry_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! FIND3-T -- The ontology is found in a community registry.

    Definitions
    -----------
    - Registered: the ontology URI appears in the Linked Open Vocabularies
      catalogue, or the ontology declares ``schema:includedInDataCatalog``.

    Source
    ------
    FOOPS! FIND3-T, FAIR principle F4 -- https://w3id.org/foops/test/FIND3

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    timeout : int or float, optional
        Request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when registered.

    Output Information
    ------------------
    - Declared catalogues and the LOV lookup outcome

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - A failed LOV request is recorded in ``detail["lov_error"]``.

    Notes
    -----
    LOV is only queried when no ``schema:includedInDataCatalog`` is
    declared.

    Examples
    --------
    >>> r = foops_find3_community_registry_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    logger.info("--- FOOPS! FIND3-T: community registry ---")
    return _registry_check(ttl_file, "foopsFIND3CommunityRegistry", timeout)


def foops_find3bis_metadata_persistence_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! FIND_3_BIS-T -- Ontology metadata are accessible even when the
    ontology is not.

    Definitions
    -----------
    - Persistent metadata: the ontology is listed in LOV or declares
      ``schema:includedInDataCatalog``, so a registry keeps its metadata
      reachable if the ontology itself disappears.  The means of
      verification is the same as FIND3-T; the FAIR principle is A2.

    Source
    ------
    FOOPS! FIND_3_BIS-T, FAIR principle A2 --
    https://w3id.org/foops/test/FIND_3_BIS

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    timeout : int or float, optional
        Request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when the metadata are held by
        a registry.

    Output Information
    ------------------
    - Declared catalogues and the LOV lookup outcome

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = foops_find3bis_metadata_persistence_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    logger.info("--- FOOPS! FIND_3_BIS-T: metadata persistence ---")
    return _registry_check(ttl_file, "foopsFIND3BISMetadataPersistence",
                           timeout)


# ---------------------------------------------------------------------------
# OM4.1 and OM4.2 -- License
# ---------------------------------------------------------------------------

def foops_om41_license_declared_v_0_0_1(ttl_file):
    """
    FOOPS! OM4.1-T -- The ontology has a license available.

    Definitions
    -----------
    - License: a value of ``dcterms:license``, ``schema:license``,
      ``doap:license`` or ``cc:license`` on the ontology resource.

    - Rights (accepted alternative): a value of ``dc:rights``,
      ``dcterms:rights`` or ``dcterms:accessRights``.

    Source
    ------
    FOOPS! OM4.1-T, FAIR principle R1.1 -- https://w3id.org/foops/test/OM4.1

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when a license or rights
        statement is declared.  ``detail["via"]`` says which.

    Output Information
    ------------------
    - Declared license and rights values

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = foops_om41_license_declared_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsOM41LicenseDeclared"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    onto = _ontology_iri(g)
    licenses = sorted({str(o) for p in LICENSE_PROPERTIES
                       for o in g.objects(onto, p)}) if onto else []
    rights = sorted({str(o) for p in RIGHTS_PROPERTIES
                     for o in g.objects(onto, p)}) if onto else []
    ok = bool(licenses or rights)
    via = "license" if licenses else ("rights" if rights else None)
    logger.info("--- FOOPS! OM4.1-T: license declared ---")
    logger.info(f"License: {licenses}; rights: {rights}")
    return MetricResult(
        metric_id=mid, score=ok, passed=ok,
        affected=[] if ok else ["<no license or rights>"], total_examined=1,
        detail={"license": licenses, "rights": rights, "via": via},
        message=(f"License declared ({via})" if ok
                 else "No license or rights statement on the ontology"),
    )


def foops_om42_license_resolvable_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! OM4.2-T -- The ontology license is resolvable.

    Definitions
    -----------
    - Resolvable license: a declared license (OM4.1 properties) that is an
      HTTP(S) URI and dereferences with a status below 400.

    Source
    ------
    FOOPS! OM4.2-T, FAIR principle R1.1 -- https://w3id.org/foops/test/OM4.2

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    timeout : int or float, optional
        Request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when at least one declared
        license URI resolves.

    Output Information
    ------------------
    - HTTP outcome per declared license

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - A license given as a literal rather than a URI fails, per FOOPS!.

    Examples
    --------
    >>> r = foops_om42_license_resolvable_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsOM42LicenseResolvable"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    onto = _ontology_iri(g)
    licenses = sorted({o for p in LICENSE_PROPERTIES
                       for o in g.objects(onto, p)}, key=str) if onto else []
    if not licenses:
        return MetricResult(metric_id=mid, score=False, passed=False,
                            affected=["<no license>"], total_examined=1,
                            message="No license declared (see OM4.1-T)")
    outcomes = {}
    for lic in licenses:
        s = str(lic).strip()
        if not re.match(r"https?://", s):
            outcomes[s] = {"error": "license is not a URI"}
            continue
        outcomes[s] = _strip(_http_get(s, "text/html, */*;q=0.5", timeout))
    ok = any(o.get("status") and o["status"] < 400 for o in outcomes.values())
    logger.info("--- FOOPS! OM4.2-T: license resolvable ---")
    for k, v in outcomes.items():
        logger.info(f"  {k}: {v.get('status')} {v.get('error') or ''}")
    return MetricResult(
        metric_id=mid, score=ok, passed=ok,
        affected=[] if ok else list(outcomes), total_examined=len(outcomes),
        detail={"outcomes": outcomes},
        message=("License resolves" if ok else "No declared license resolves"),
    )


# ---------------------------------------------------------------------------
# PURL1 -- Persistent URL
# ---------------------------------------------------------------------------

def foops_purl1_persistent_url_v_0_0_1(ttl_file):
    """
    FOOPS! PURL1-T -- The ontology has a persistent URL.

    Definitions
    -----------
    - Persistent URL: an ontology URI whose host is one of the FOOPS!
      persistent-identifier services: ``w3id.org``, ``doi.org``,
      ``purl.org`` (or ``purl.<name>.org``), ``linked.data.gov.au``,
      ``dbpedia.org``, ``www.w3.org``, ``perma.cc`` or ``data.europa.eu``.

    Source
    ------
    FOOPS! PURL1-T, FAIR principle F1 -- https://w3id.org/foops/test/PURL1

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when the URI is persistent.

    Output Information
    ------------------
    - The ontology URI and its host

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    Relevant to the MDS modules, whose URIs live on
    ``cwrusdle.bitbucket.io`` -- a hosting location, not a persistent
    identifier -- so moving the site breaks every term IRI.

    Examples
    --------
    >>> r = foops_purl1_persistent_url_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsPURL1PersistentUrl"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    uri = _ontology_uri(g)
    if uri is None:
        return _no_uri(mid)
    m = re.match(r"https?://([^/#]+)", uri)
    host = m.group(1).lower() if m else None
    ok = bool(host) and any(re.fullmatch(h, host) for h in PERSISTENT_HOSTS)
    logger.info("--- FOOPS! PURL1-T: persistent URL ---")
    logger.info(f"{uri} (host {host}): {ok}")
    return MetricResult(
        metric_id=mid, score=ok, passed=ok, affected=[] if ok else [uri],
        total_examined=1, detail={"uri": uri, "host": host},
        message=(f"Persistent URL ({host})" if ok
                 else f"Host {host} is not a persistent-identifier service"),
    )


# ---------------------------------------------------------------------------
# RDF1 -- RDF availability
# ---------------------------------------------------------------------------

def foops_rdf1_rdf_available_v_0_0_1(ttl_file):
    """
    FOOPS! RDF1-T -- The ontology is available in RDF.

    Definitions
    -----------
    - Available in RDF: the ontology document loads as RDF (Turtle, N3,
      RDF/XML or JSON-LD) without syntax errors and yields at least one
      triple.  OntoCheck assesses a local file, so the file is the document
      tested; FOOPS! additionally dereferences the URI (see CN1-T, URI1-T).

    Source
    ------
    FOOPS! RDF1-T, FAIR principle I1 -- https://w3id.org/foops/test/RDF1

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology file.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when the file parses.
        ``detail["format"]`` is the serialisation that parsed.

    Output Information
    ------------------
    - Triple count and the parser error, if any

    Error Handling
    --------------
    - Parse failures are the failing outcome of this test, not an error.

    Examples
    --------
    >>> r = foops_rdf1_rdf_available_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsRDF1RdfAvailable"
    errors = {}
    for fmt in ("turtle", "xml", "json-ld", "n3"):
        g = Graph()
        try:
            g.parse(str(ttl_file), format=fmt)
            if len(g):
                logger.info(f"--- FOOPS! RDF1-T: parsed as {fmt}, "
                            f"{len(g)} triples ---")
                return MetricResult(
                    metric_id=mid, score=True, passed=True, total_examined=1,
                    detail={"format": fmt, "triples": len(g)},
                    message=f"Valid RDF ({fmt}, {len(g)} triples)")
        except Exception as e:
            errors[fmt] = f"{type(e).__name__}: {str(e)[:200]}"
    logger.info("--- FOOPS! RDF1-T: no RDF serialisation could be parsed ---")
    return MetricResult(
        metric_id=mid, score=False, passed=False, affected=[str(ttl_file)],
        total_examined=1, detail={"errors": errors},
        message="The file does not parse as RDF",
    )


# ---------------------------------------------------------------------------
# URI1 and URI2 -- URI resolution and consistency
# ---------------------------------------------------------------------------

def foops_uri1_uri_resolvable_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! URI1-T -- The ontology URI is resolvable.

    Definitions
    -----------
    - Resolvable: dereferencing the ``owl:Ontology`` IRI found in the
      document with an RDF ``Accept`` header returns RDF/XML, Turtle,
      N-Triples or JSON-LD that parses.

    Source
    ------
    FOOPS! URI1-T, FAIR principle F1 -- https://w3id.org/foops/test/URI1

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    timeout : int or float, optional
        Request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when RDF is returned.

    Output Information
    ------------------
    - HTTP outcome of the request

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - An ontology without an IRI fails with an explanatory message.

    Examples
    --------
    >>> r = foops_uri1_uri_resolvable_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsURI1UriResolvable"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    uri = _ontology_uri(g)
    if uri is None:
        return _no_uri(mid)
    r = _http_get(uri, _RDF_ACCEPT, timeout)
    ok = _parse_rdf_response(r) is not None
    logger.info("--- FOOPS! URI1-T: URI resolvable ---")
    logger.info(f"{uri}: {r['status']} {r['content_type']} {r['error'] or ''}")
    return MetricResult(
        metric_id=mid, score=ok, passed=ok, affected=[] if ok else [uri],
        total_examined=1, detail={"uri": uri, "response": _strip(r)},
        message=("Ontology URI resolves to RDF" if ok
                 else f"Ontology URI does not resolve to RDF "
                      f"({r['error'] or r['status']})"),
    )


def foops_uri2_consistent_ids_v_0_0_1(ttl_file, timeout=15):
    """
    FOOPS! URI2-T -- Consistent ontology IDs are employed.

    Definitions
    -----------
    - Consistent ID: the ontology document retrieved by dereferencing the
      ontology URI declares, as its ``owl:Ontology`` IRI, the same URI that
      was used to load it.  FOOPS! compares the loading URI with the ID in
      the document; here the loading URI is the IRI declared in the local
      file, so the test also confirms that the published copy and the local
      copy agree on their identity.

    Source
    ------
    FOOPS! URI2-T, FAIR principle F1 -- https://w3id.org/foops/test/URI2

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    timeout : int or float, optional
        Request timeout in seconds.  Default 15.

    Returns
    -------
    MetricResult
        ``score`` and ``passed`` are ``True`` when the published document's
        ontology IRI equals the loading URI.

    Output Information
    ------------------
    - The loading URI and the IRI found in the retrieved document

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.
    - When the URI cannot be dereferenced the test fails and the HTTP
      outcome is recorded.

    Examples
    --------
    >>> r = foops_uri2_consistent_ids_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsURI2ConsistentIds"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    uri = _ontology_uri(g)
    if uri is None:
        return _no_uri(mid)
    r = _http_get(uri, _RDF_ACCEPT, timeout)
    remote = _parse_rdf_response(r)
    remote_ids = sorted(str(s) for s in remote.subjects(RDF.type, OWL.Ontology)
                        if isinstance(s, URIRef)) if remote is not None else []
    ok = uri in remote_ids
    logger.info("--- FOOPS! URI2-T: consistent ontology IDs ---")
    logger.info(f"Loading URI {uri}; IDs in retrieved document: {remote_ids}")
    return MetricResult(
        metric_id=mid, score=ok, passed=ok, affected=[] if ok else [uri],
        total_examined=1,
        detail={"uri": uri, "retrieved_ids": remote_ids,
                "response": _strip(r)},
        message=("Ontology ID matches the URI it is served from" if ok
                 else ("Retrieved document declares a different ontology ID"
                       if remote_ids else
                       "No ontology document could be retrieved from the URI")),
    )


# ---------------------------------------------------------------------------
# VOC1 and VOC2 -- Vocabulary reuse
# ---------------------------------------------------------------------------

def foops_voc1_metadata_vocabulary_reuse_v_0_0_1(ttl_file):
    """
    FOOPS! VOC1-T -- The ontology reuses existing vocabularies for metadata
    annotations.

    Definitions
    -----------
    - Metadata annotation: a statement whose subject is the ``owl:Ontology``
      resource, excluding ``rdf:type``.

    - Accepted vocabularies: Dublin Core (``dc``, ``dcterms``), schema.org,
      VANN, PROV, BIBO, PAV, FOAF, DOAP, MOD, OWL and RDFS.

    - Pass: at least one metadata annotation uses a property from an
      accepted vocabulary.

    Source
    ------
    FOOPS! VOC1-T, FAIR principle I2 -- https://w3id.org/foops/test/VOC1

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the share of metadata annotations drawn from accepted
        vocabularies; ``passed`` is ``True`` when at least one is.
        ``detail["by_vocabulary"]`` counts them.

    Output Information
    ------------------
    - Accepted and non-standard metadata properties used

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Notes
    -----
    Metadata properties outside the accepted vocabularies are listed in
    ``detail["non_standard"]``.

    Examples
    --------
    >>> r = foops_voc1_metadata_vocabulary_reuse_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsVOC1MetadataVocabReuse"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    onto = _ontology_iri(g)
    if onto is None:
        onto = next(iter(g.subjects(RDF.type, OWL.Ontology)), None)
    if onto is None:
        return MetricResult(metric_id=mid, score=0.0, passed=False,
                            affected=["<no owl:Ontology>"], total_examined=0,
                            message="No owl:Ontology resource to annotate")
    preds = [p for p in g.predicates(onto, None) if p != RDF.type]
    by_vocab, non_std = {}, []
    for p in preds:
        vocab = next((k for k, ns in METADATA_VOCABULARIES.items()
                      if str(p).startswith(ns)), None)
        if vocab:
            by_vocab[vocab] = by_vocab.get(vocab, 0) + 1
        else:
            non_std.append(str(p))
    score = round(sum(by_vocab.values()) / len(preds), 4) if preds else 0.0
    ok = bool(by_vocab)
    logger.info("--- FOOPS! VOC1-T: metadata vocabulary reuse ---")
    logger.info(f"Accepted: {by_vocab}; non-standard: {sorted(set(non_std))}")
    return MetricResult(
        metric_id=mid, score=score, passed=ok,
        affected=sorted(set(non_std)), total_examined=len(preds),
        detail={"by_vocabulary": by_vocab,
                "non_standard": sorted(set(non_std))},
        message=(f"{sum(by_vocab.values())} of {len(preds)} metadata "
                 f"annotation(s) use standard vocabularies" if preds
                 else "No metadata annotations on the ontology"),
    )


def foops_voc2_vocabulary_reuse_v_0_0_1(ttl_file):
    """
    FOOPS! VOC2-T -- The ontology imports or reuses well-established
    vocabularies.

    Definitions
    -----------
    - Import: an ``owl:imports`` statement.

    - Reused term: a class or object/datatype property outside the
      ontology's own namespace(s) and outside RDF, RDFS, OWL and XSD, used
      in the ontology.

    - Pass: at least one import or reused term.

    Source
    ------
    FOOPS! VOC2-T, FAIR principle I2 -- https://w3id.org/foops/test/VOC2

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is the number of reused external terms; ``passed`` is
        ``True`` when something is imported or reused.
        ``detail["by_namespace"]`` counts reused terms per namespace.

    Output Information
    ------------------
    - Imports and reused namespaces with term counts

    Error Handling
    --------------
    - A file that cannot be loaded yields a result with an ``"Error:"``
      status.

    Examples
    --------
    >>> r = foops_voc2_vocabulary_reuse_v_0_0_1("o.ttl")  # doctest: +SKIP
    """
    mid = "foopsVOC2VocabReuse"
    g = _load_graph(ttl_file)
    if g is None:
        return _load_error(mid)
    own_ns = _own_namespace(g)
    imports = sorted(str(o) for o in g.objects(None, OWL.imports))
    terms = _named_classes(g) | _object_and_datatype_properties(g)
    terms |= {p for _, p, _ in g if isinstance(p, URIRef)}

    def own(t):
        """True when ``t`` is in the ontology's own namespace(s)."""
        return own_ns is not None and str(t).startswith(own_ns)

    reused = sorted({t for t in terms if isinstance(t, URIRef)
                     and not own(t) and not str(t).startswith(_CORE_NS)},
                    key=str)
    by_ns = {}
    for t in reused:
        ns = _namespace_of(t)
        by_ns[ns] = by_ns.get(ns, 0) + 1
    ok = bool(imports or reused)
    logger.info("--- FOOPS! VOC2-T: vocabulary reuse ---")
    logger.info(f"Imports: {imports}; reused namespaces: {by_ns}")
    return MetricResult(
        metric_id=mid, score=len(reused), passed=ok,
        affected=[] if ok else ["<no imports or reused terms>"],
        total_examined=len(terms),
        detail={"imports": imports, "by_namespace": by_ns},
        message=(f"{len(imports)} import(s); {len(reused)} reused term(s) "
                 f"from {len(by_ns)} namespace(s)" if ok
                 else "No imported or reused vocabularies"),
    )


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

def _d(metric_id, name, function, category, test_id, severity, scale, fair,
       description, network=False):
    """
    Build a FOOPS! test descriptor with the shared fields filled in.

    Parameters
    ----------
    metric_id, name : str
        Registry identifier and human-readable name.
    function : callable
        Implementation.
    category : Category
        Functional grouping.
    test_id : str
        FOOPS! test identifier, e.g. ``"CN1"``.
    severity : Severity
        Severity assigned in OntoCheck.
    scale : Scale
        Interpretation of the score.
    fair : str
        FAIR principle addressed.
    description : str
        One-line summary.
    network : bool, optional
        Whether the test performs HTTP requests.

    Returns
    -------
    MetricDescriptor
        The descriptor.
    """
    return MetricDescriptor(
        metric_id=metric_id, name=name, function=function, category=category,
        source_framework=SourceFramework.FOOPS, source_id=f"{test_id}-T",
        source_url=_TEST_URL.format(test_id), severity=severity, scale=scale,
        higher_is_better=True, requires_network=network, fair_principle=fair,
        description=description,
    )


_ACCESS_DESCRIPTORS = [
    _d("foopsCN1ContentNegotiation", "Content negotiation",
       foops_cn1_content_negotiation_v_0_0_1, Category.ACCESSIBILITY, "CN1",
       Severity.IMPORTANT, Scale.BOOLEAN, "A1",
       "Ontology URI serves HTML and an RDF serialisation.", network=True),
    _d("foopsDOC1HtmlDocumentation", "HTML documentation",
       foops_doc1_html_documentation_v_0_0_1, Category.ACCESSIBILITY, "DOC1",
       Severity.IMPORTANT, Scale.BOOLEAN, "R1",
       "Ontology URI serves HTML documentation.", network=True),
    _d("foopsFIND2PrefixRegistered", "Prefix registered",
       foops_find2_prefix_registered_v_0_0_1, Category.METADATA, "FIND2",
       Severity.MINOR, Scale.BOOLEAN, "F4",
       "Declared prefix is registered in prefix.cc or LOV.", network=True),
    _d("foopsFIND3CommunityRegistry", "Found in community registry",
       foops_find3_community_registry_v_0_0_1, Category.METADATA, "FIND3",
       Severity.MINOR, Scale.BOOLEAN, "F4",
       "Ontology listed in LOV or declares schema:includedInDataCatalog.",
       network=True),
    _d("foopsFIND3BISMetadataPersistence", "Metadata persist in a registry",
       foops_find3bis_metadata_persistence_v_0_0_1, Category.METADATA,
       "FIND_3_BIS", Severity.MINOR, Scale.BOOLEAN, "A2",
       "Metadata held by LOV or a declared data catalogue.", network=True),
    _d("foopsOM41LicenseDeclared", "License declared",
       foops_om41_license_declared_v_0_0_1, Category.METADATA, "OM4.1",
       Severity.IMPORTANT, Scale.BOOLEAN, "R1.1",
       "License or rights statement on the ontology."),
    _d("foopsOM42LicenseResolvable", "License resolvable",
       foops_om42_license_resolvable_v_0_0_1, Category.METADATA, "OM4.2",
       Severity.MINOR, Scale.BOOLEAN, "R1.1",
       "Declared license URI dereferences.", network=True),
    _d("foopsPURL1PersistentUrl", "Persistent URL",
       foops_purl1_persistent_url_v_0_0_1, Category.ACCESSIBILITY, "PURL1",
       Severity.IMPORTANT, Scale.BOOLEAN, "F1",
       "Ontology URI uses a persistent-identifier service."),
    _d("foopsRDF1RdfAvailable", "Available in RDF",
       foops_rdf1_rdf_available_v_0_0_1, Category.ACCESSIBILITY, "RDF1",
       Severity.IMPORTANT, Scale.BOOLEAN, "I1",
       "Ontology document parses as RDF."),
    _d("foopsURI1UriResolvable", "URI resolvable",
       foops_uri1_uri_resolvable_v_0_0_1, Category.ACCESSIBILITY, "URI1",
       Severity.IMPORTANT, Scale.BOOLEAN, "F1",
       "Ontology URI dereferences to RDF.", network=True),
    _d("foopsURI2ConsistentIds", "Consistent ontology IDs",
       foops_uri2_consistent_ids_v_0_0_1, Category.ACCESSIBILITY, "URI2",
       Severity.MINOR, Scale.BOOLEAN, "F1",
       "Published document's ontology IRI equals the URI it is served from.",
       network=True),
    _d("foopsVOC1MetadataVocabReuse", "Metadata vocabulary reuse",
       foops_voc1_metadata_vocabulary_reuse_v_0_0_1, Category.METADATA,
       "VOC1", Severity.MINOR, Scale.PROPORTION, "I2",
       "Ontology metadata use standard vocabularies."),
    _d("foopsVOC2VocabReuse", "Vocabulary reuse",
       foops_voc2_vocabulary_reuse_v_0_0_1, Category.STRUCTURAL, "VOC2",
       Severity.MINOR, Scale.COUNT, "I2",
       "Ontology imports or reuses external vocabularies."),
]

for _descriptor in _ACCESS_DESCRIPTORS:
    register_metric(_descriptor)
