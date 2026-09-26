"""
FOOPS!-derived version IRI checks.

Implements the two FOOPS! tests that concern ontology versioning:

=========  ==========================================  =====
Test       Description                                 FAIR
=========  ==========================================  =====
VER1-T     A version IRI is declared in the ontology
           metadata                                    F1
VER2-T     The ontology version IRI resolves           F1
=========  ==========================================  =====

These are the only items in OQuaRE, OOPS! or FOOPS! that address ontology
evolution.  Every other check in all three frameworks evaluates a single
snapshot.  A declared, resolvable version IRI is the minimum precondition for
comparing an ontology against its own earlier releases, which is what any
assessment of an evolving ontology requires.

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

from rdflib import OWL, RDF, URIRef

from .helpers.oops_helpers import _load_graph, _ontology_iri
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

# Predicates that may carry version information, in order of standards
# preference.  owl:versionIRI is the only one that yields a dereferenceable
# identifier; the others carry a version string only.
_VERSION_IRI_PREDICATE = OWL.versionIRI
_VERSION_INFO_PREDICATES = (
    OWL.versionInfo,
    URIRef("http://purl.org/dc/terms/hasVersion"),
    URIRef("http://purl.org/pav/version"),
    URIRef("http://www.w3.org/ns/dcat#version"),
    URIRef("http://schema.org/version"),
)


def foops_ver1_version_iri_declared_v_0_0_1(ttl_file):
    """
    FOOPS! VER1-T -- A version IRI is declared in the ontology metadata.

    Verify that the ontology declares an ``owl:versionIRI``, and report any
    weaker version information found in its place.

    Definitions
    -----------
    - Version IRI: the object of ``owl:versionIRI`` on the ontology
      declaration.  It identifies one specific release of the ontology, as
      distinct from the ontology IRI, which identifies the ontology across all
      of its releases.

    - Version information: a version *string* carried by ``owl:versionInfo``,
      ``dcterms:hasVersion``, ``pav:version``, ``dcat:version`` or
      ``schema:version``.  Useful to a human reader but not dereferenceable,
      so it does not satisfy VER1-T on its own.

    - Snapshot comparison: without a version IRI there is no identifier for
      the release an assessment was run against, so results cannot be
      attributed to a particular state of the ontology.

    Source
    ------
    FOOPS! VER1-T, FAIR principle F1 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.

    Returns
    -------
    MetricResult
        ``score`` is ``True`` when an ``owl:versionIRI`` is present.
        ``detail["version_iri"]`` holds it, ``detail["version_info"]`` lists
        any version strings found, and
        ``detail["has_version_info_only"]`` flags the common case of a version
        string present without a version IRI.

    Output Information
    ------------------
    - Whether an ``owl:versionIRI`` is declared, and its value
    - Any version strings found under the alternative predicates
    - Whether the version IRI differs from the ontology IRI, as it should

    Error Handling
    --------------
    - Missing or unparseable files are logged and reported through a
      ``MetricResult`` whose ``status`` begins ``"Error:"``.
    - An ontology with no ``owl:Ontology`` declaration cannot carry a version
      IRI; the result is a failure whose message says so, since OOPS! P38
      reports the underlying cause.

    Notes
    -----
    A version IRI equal to the ontology IRI is reported in
    ``detail["iri_collision"]``.  It satisfies the letter of the test while
    defeating its purpose, since the two then cannot be told apart.

    Examples
    --------
    >>> result = foops_ver1_version_iri_declared_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    >>> result.detail["version_iri"]                                      # doctest: +SKIP
    'https://example.org/onto/1.2.0'
    """
    g = _load_graph(ttl_file)
    if g is None:
        return MetricResult(
            metric_id="foopsVER1VersionIriDeclared",
            status="Error: could not load ontology",
        )

    ontology_iri = _ontology_iri(g)
    if ontology_iri is None:
        logger.info("--- FOOPS! VER1-T: version IRI declared ---")
        logger.info(
            "No owl:Ontology declaration, so no version IRI can be carried "
            "(see OOPS! P38)."
        )
        return MetricResult(
            metric_id="foopsVER1VersionIriDeclared",
            score=False,
            passed=False,
            affected=["<no owl:Ontology declaration>"],
            total_examined=1,
            detail={"version_iri": None, "version_info": [],
                    "no_ontology_declaration": True},
            message=(
                "No owl:Ontology declaration, so no version IRI is present "
                "(see OOPS! P38)"
            ),
        )

    version_iris = [
        str(o) for o in g.objects(ontology_iri, _VERSION_IRI_PREDICATE)
    ]

    version_info = []
    for pred in _VERSION_INFO_PREDICATES:
        for o in g.objects(ontology_iri, pred):
            text = str(o).strip()
            if text:
                version_info.append({"predicate": str(pred), "value": text})

    present = bool(version_iris)
    collision = present and version_iris[0] == str(ontology_iri)

    logger.info("--- FOOPS! VER1-T: version IRI declared ---")
    logger.info(f"Ontology IRI: {ontology_iri}")
    if present:
        for v in version_iris:
            logger.info(f"owl:versionIRI: {v}")
        if collision:
            logger.info(
                "The version IRI is identical to the ontology IRI; releases "
                "cannot be distinguished."
            )
    else:
        logger.info("No owl:versionIRI declared.")
    if version_info:
        logger.info("Version information found under other predicates:")
        for entry in version_info:
            logger.info(f"  {entry['predicate']}: {entry['value']}")

    return MetricResult(
        metric_id="foopsVER1VersionIriDeclared",
        score=present,
        passed=present,
        affected=[] if present else [str(ontology_iri)],
        total_examined=1,
        detail={
            "version_iri": version_iris[0] if present else None,
            "all_version_iris": version_iris,
            "version_info": version_info,
            "has_version_info_only": bool(version_info) and not present,
            "iri_collision": collision,
            "ontology_iri": str(ontology_iri),
        },
        message=(
            f"owl:versionIRI declared ({version_iris[0]})" if present
            else (
                "No owl:versionIRI; version strings present under other "
                "predicates" if version_info
                else "No version IRI or version information declared"
            )
        ),
    )


def foops_ver2_version_iri_resolves_v_0_0_1(ttl_file, timeout=10):
    """
    FOOPS! VER2-T -- The ontology version IRI resolves.

    Dereference the declared ``owl:versionIRI`` over HTTP and report whether
    it returns a successful response.

    Definitions
    -----------
    - Resolves: an HTTP request to the version IRI returns a final status code
      below 400, following redirects.  A ``HEAD`` request is attempted first
      and a ``GET`` is used as a fallback, since some servers do not implement
      ``HEAD``.

    - Non-resolvable version IRI: a declared identifier that cannot be
      retrieved.  The release it names cannot be fetched for comparison, which
      leaves version-to-version assessment impossible even though VER1-T
      passes.

    Source
    ------
    FOOPS! VER2-T, FAIR principle F1 -- https://w3id.org/foops/catalog

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to analyse.
    timeout : int or float, optional
        Per-request timeout in seconds.  Default 10.

    Returns
    -------
    MetricResult
        ``score`` is ``True`` when the version IRI resolves.  ``detail``
        records the status code, final URL after redirects, response content
        type and elapsed time.  When no version IRI is declared the result
        carries ``status`` ``"Skipped (no version IRI declared; see VER1-T)"``.

    Output Information
    ------------------
    - The version IRI requested and the HTTP status returned
    - The final URL, when redirects were followed
    - The ``Content-Type`` of the response, which indicates whether content
      negotiation is serving RDF (compare FOOPS! CN1-T)

    Error Handling
    --------------
    - Connection errors, timeouts and DNS failures are caught and reported as
      a failed resolution with the exception text in ``detail["error"]``,
      rather than propagating.
    - A missing ``requests`` dependency is reported through ``status`` rather
      than raising.

    Notes
    -----
    This metric performs network access and is registered with
    ``requires_network=True``, so it is skipped automatically when assessment
    runs offline.

    Examples
    --------
    >>> result = foops_ver2_version_iri_resolves_v_0_0_1("ontology.ttl")  # doctest: +SKIP
    >>> result.detail["status_code"]                                      # doctest: +SKIP
    200
    """
    ver1 = foops_ver1_version_iri_declared_v_0_0_1(ttl_file)
    if ver1.status.startswith("Error"):
        return MetricResult(
            metric_id="foopsVER2VersionIriResolves",
            status=ver1.status,
        )

    version_iri = ver1.detail.get("version_iri")
    if not version_iri:
        logger.info("--- FOOPS! VER2-T: version IRI resolves ---")
        logger.info("No version IRI declared; nothing to resolve.")
        return MetricResult(
            metric_id="foopsVER2VersionIriResolves",
            score=None,
            passed=None,
            total_examined=0,
            detail={"version_iri": None},
            status="Skipped (no version IRI declared; see VER1-T)",
            message="No version IRI declared, so resolution was not attempted",
        )

    try:
        import requests
    except ImportError:
        logger.error("The 'requests' package is required for VER2-T.")
        return MetricResult(
            metric_id="foopsVER2VersionIriResolves",
            detail={"version_iri": version_iri},
            status="Skipped (the 'requests' package is not installed)",
            message="requests is not installed",
        )

    headers = {"Accept": "text/turtle, application/rdf+xml;q=0.9, */*;q=0.5"}
    status_code, final_url, content_type, error, elapsed = (
        None, None, None, None, None
    )

    logger.info("--- FOOPS! VER2-T: version IRI resolves ---")
    logger.info(f"Requesting: {version_iri}")

    for method in ("head", "get"):
        try:
            response = getattr(requests, method)(
                version_iri,
                allow_redirects=True,
                timeout=timeout,
                headers=headers,
            )
            status_code = response.status_code
            final_url = response.url
            content_type = response.headers.get("Content-Type")
            elapsed = response.elapsed.total_seconds()
            error = None
            if status_code < 400:
                break
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            logger.debug(f"{method.upper()} request failed: {error}")

    resolves = status_code is not None and status_code < 400

    logger.info(f"HTTP status: {status_code}")
    if final_url and final_url != version_iri:
        logger.info(f"Redirected to: {final_url}")
    if content_type:
        logger.info(f"Content-Type: {content_type}")
    if error:
        logger.info(f"Request error: {error}")

    return MetricResult(
        metric_id="foopsVER2VersionIriResolves",
        score=resolves,
        passed=resolves,
        affected=[] if resolves else [version_iri],
        total_examined=1,
        detail={
            "version_iri": version_iri,
            "status_code": status_code,
            "final_url": final_url,
            "content_type": content_type,
            "elapsed_seconds": elapsed,
            "error": error,
            "redirected": bool(final_url and final_url != version_iri),
        },
        message=(
            f"Version IRI resolves (HTTP {status_code})" if resolves
            else f"Version IRI does not resolve ({error or status_code})"
        ),
    )


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

_VERSION_DESCRIPTORS = [
    MetricDescriptor(
        metric_id="foopsVER1VersionIriDeclared",
        name="Version IRI declared",
        function=foops_ver1_version_iri_declared_v_0_0_1,
        category=Category.VERSIONING,
        source_framework=SourceFramework.FOOPS,
        source_id="VER1-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.BOOLEAN,
        higher_is_better=True,
        fair_principle="F1",
        description="An owl:versionIRI is declared in the ontology metadata.",
    ),
    MetricDescriptor(
        metric_id="foopsVER2VersionIriResolves",
        name="Version IRI resolves",
        function=foops_ver2_version_iri_resolves_v_0_0_1,
        category=Category.VERSIONING,
        source_framework=SourceFramework.FOOPS,
        source_id="VER2-T",
        source_url=_CATALOGUE,
        severity=Severity.IMPORTANT,
        scale=Scale.BOOLEAN,
        higher_is_better=True,
        requires_network=True,
        fair_principle="F1",
        description="The declared owl:versionIRI dereferences successfully.",
    ),
]

for _descriptor in _VERSION_DESCRIPTORS:
    register_metric(_descriptor)
