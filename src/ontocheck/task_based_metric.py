"""
Task-Based Ontology Assessment Metric

Evaluates an ontology against a set of competency questions (encoded as SPARQL
queries) by computing term-overlap metrics. For each question set, two scores
are produced:

    Recall   = \\|T_a intersection T_o\\| / \\|T_a\\|
    Precision = \\|T_a intersection T_o\\| / \\|T_o\\|

where T_a is the set of domain terms referenced in the SPARQL queries (the
"task vocabulary") and T_o is the set of domain terms defined in the ontology.

Questions can be supplied as:
    - A path to a JSON file where each item contains a ``sparql_query`` key.
    - A path to a Markdown file with SPARQL queries inside ``sparql`` blocks.
    - A plain list of SPARQL query strings.

Changelog (v0.0.2)
------------------
- FIXED: when ``domain_ns_fragments`` was omitted, T_o was built from every
  non-foundational term in the graph, including the stub declarations a domain
  ontology carries for imported CCO and BFO terms. Because Precision divides
  by ``|T_o|``, those stubs inflate the denominator and understate the score.
  Measured on XRD.ttl, ``|T_o|`` was 371 without a fragment filter against 318
  with one, understating Precision by a factor of 1.17; the effect is larger on
  merged cross-domain files, which accumulate more stubs. The CLI invocation
  documented in the README omits the flag, so this was the default behaviour.
  ``domain_ns_fragments`` is now derived automatically from the namespace
  bindings of ``domain_prefixes`` when it is not supplied, and the derivation
  is logged.
- FIXED: ``_extract_terms_from_sparql`` did not match SPARQL local names
  containing ``-`` or ``.``, both of which are legal in a PN_LOCAL, so terms
  such as ``mds:has-part`` were silently dropped from T_a. The pattern now
  accepts them. It also required a non-word character before the prefix, so
  that the prefix ``mds`` no longer matches inside ``xmds:Foo``.
- ADDED: ``task_coverage`` and ``ontology_utilization`` keys alongside
  ``recall`` and ``precision``. See the note on naming below. The original
  keys are unchanged, so existing callers and the README example continue to
  work.

A note on the name "Precision"
------------------------------
``|T_a intersection T_o| / |T_o|`` is not precision in the
information-retrieval sense: it does not measure how many returned items were
relevant, and it penalises a comprehensive ontology for containing terms that
a particular question set happened not to use. An ontology that perfectly
answers every competency question scores *lower* on this quantity the more
domain coverage it has. The project README already describes it as
"utilization density", which is accurate.

Both names are returned so that the terminology can be settled without
breaking callers. Whichever is adopted, the paper should define the quantity
explicitly rather than relying on the reader's IR intuitions, and the three
spellings currently in the codebase -- "Recall/Precision" in the README and in
this module, "Relevance/Accuracy" in ``cli.py`` -- should be reduced to one.
"""

import re
import json
import logging
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Foundational namespace filter
# ---------------------------------------------------------------------------

_FOUNDATIONAL_NS = {
    str(RDF),
    str(RDFS),
    str(OWL),
    str(XSD),
    "http://www.w3.org/2004/02/skos/core#",
    "http://purl.org/dc/terms/",
    "http://qudt.org/schema/qudt/",
    "http://qudt.org/vocab/unit/",
    "http://www.w3.org/XML/1998/namespace",
}


def _is_foundational(uri_str):
    """
    Check whether a URI belongs to a foundational / upper-level namespace.

    Foundational namespaces (RDF, RDFS, OWL, XSD, SKOS, Dublin Core, QUDT,
    XML) are excluded from the domain term set because they represent
    general-purpose vocabulary rather than domain-specific concepts.

    Parameters
    ----------
    uri_str : str
        The full URI string to check.

    Returns
    -------
    bool
        True if the URI starts with any foundational namespace prefix.
    """
    for ns in _FOUNDATIONAL_NS:
        if uri_str.startswith(ns):
            return True
    return False


def _get_local_name(uri_str):
    """
    Extract the local name fragment from a URI.

    Splits on ``#`` first; if the fragment itself contains ``/``, a second
    split is performed.  Falls back to splitting on ``/`` when no ``#`` is
    present.

    Parameters
    ----------
    uri_str : str
        The full URI string.

    Returns
    -------
    str
        The local name portion of the URI.
    """
    uri_str = str(uri_str)
    if "#" in uri_str:
        fragment = uri_str.rsplit("#", 1)[-1]
        if "/" in fragment:
            return fragment.rsplit("/", 1)[-1]
        return fragment
    elif "/" in uri_str:
        return uri_str.rsplit("/", 1)[-1]
    return uri_str


# ---------------------------------------------------------------------------
# Namespace fragment derivation
# ---------------------------------------------------------------------------

def _derive_ns_fragments(g, domain_prefixes):
    """
    Derive namespace URI fragments from the graph's own prefix bindings.

    Definitions
    -----------
    - Derivation: for each prefix in *domain_prefixes*, the namespace URI it is
      bound to in the parsed graph is looked up and used as the restricting
      fragment. The bindings come from the ``@prefix`` directives of the
      Turtle file itself, so the result matches what the query author meant by
      that prefix.

    - Why this matters: without a fragment filter, T_o contains every
      non-foundational term in the graph. A domain ontology that declares stub
      entries for imported upper-level terms -- ``cco:ont00000324 a owl:Class ;
      rdfs:label "Width"`` -- contributes those stubs to the denominator of
      Precision, understating it.

    Version: 0.0.2

    Parameters
    ----------
    g : rdflib.Graph
        The merged ontology graph.
    domain_prefixes : list of str
        Prefixes used in the SPARQL queries, e.g. ``["mds"]``.

    Returns
    -------
    list of str
        Namespace URI strings, one per prefix that could be resolved. Empty
        when none could be, in which case the caller should fall back to
        including all non-foundational terms and warn.

    Notes
    -----
    The MDS ontologies bind a namespace whose URI embeds a second URI
    (``.../index-en.html#https://cwrusdle.bitbucket.io/mds/``). Since matching
    is by substring containment, the derived fragment works unchanged.

    Examples
    --------
    >>> _derive_ns_fragments(g, ["mds"])   # doctest: +SKIP
    ['https://cwrusdle.bitbucket.io/files/MDS_Onto/index-en.html#https://cwrusdle.bitbucket.io/mds/']
    """
    bindings = {prefix: str(ns) for prefix, ns in g.namespaces()}
    fragments = []
    for prefix in domain_prefixes or []:
        ns = bindings.get(prefix)
        if ns:
            fragments.append(ns)
        else:
            logger.warning(
                f"Prefix '{prefix}' is not bound in the ontology; no namespace "
                f"fragment could be derived for it."
            )
    return fragments


# ---------------------------------------------------------------------------
# Ontology term extraction
# ---------------------------------------------------------------------------

def _get_ontology_terms(ttl_files, domain_ns_fragments=None):
    """
    Parse one or more Turtle files and return the set of domain term local
    names (T_o).

    Terms are discovered through three complementary SPARQL queries:

    1. Entities explicitly typed as ``owl:Class``, ``rdfs:Class``,
       ``owl:ObjectProperty``, ``owl:DatatypeProperty``, or ``rdf:Property``.
    2. Subjects that carry an ``rdfs:label`` (catches properties defined
       without explicit typing).
    3. Subjects of ``rdfs:domain`` or ``rdfs:range`` declarations.

    Foundational-namespace URIs are always excluded.  When
    *domain_ns_fragments* is provided, only URIs whose string representation
    contains at least one of the given fragments are retained.

    Parameters
    ----------
    ttl_files : list of str or list of pathlib.Path
        Paths to Turtle (.ttl) ontology files.
    domain_ns_fragments : list of str or None, optional
        Namespace URI sub-strings used to restrict results to domain-specific
        terms.  If ``None``, all non-foundational terms are included.

    Returns
    -------
    tuple
        ``(terms, graph)`` where *terms* is a set of local names and *graph* is
        the merged graph, returned so the caller can derive namespace
        fragments from its prefix bindings without re-parsing.
    """
    g = Graph()
    for f in ttl_files:
        g.parse(str(f), format="turtle")

    queries = [
        """
        SELECT DISTINCT ?term WHERE {
            { ?term a owl:Class } UNION
            { ?term a rdfs:Class } UNION
            { ?term a owl:ObjectProperty } UNION
            { ?term a owl:DatatypeProperty } UNION
            { ?term a rdf:Property }
        }
        """,
        """
        SELECT DISTINCT ?term WHERE {
            ?term rdfs:label ?label .
            FILTER(isIRI(?term))
        }
        """,
        """
        SELECT DISTINCT ?term WHERE {
            { ?term rdfs:domain ?d } UNION
            { ?term rdfs:range ?r }
            FILTER(isIRI(?term))
        }
        """,
    ]

    ontology_terms = set()
    for q in queries:
        for row in g.query(q):
            if not isinstance(row.term, URIRef):
                continue
            uri = str(row.term)
            if _is_foundational(uri):
                continue
            local = _get_local_name(uri)
            if not local or not local.strip():
                continue
            if domain_ns_fragments:
                if any(frag in uri for frag in domain_ns_fragments):
                    ontology_terms.add(local)
            else:
                ontology_terms.add(local)

    return ontology_terms, g


# ---------------------------------------------------------------------------
# SPARQL term extraction
# ---------------------------------------------------------------------------

def _extract_terms_from_sparql(sparql_query, domain_prefixes):
    """
    Extract prefixed local names from a SPARQL query string.

    For each prefix in *domain_prefixes*, a regex search finds all occurrences
    of ``prefix:LocalName`` and collects the local name parts.

    Definitions
    -----------
    - Local name: matched as ``[A-Za-z_][A-Za-z0-9_.-]*`` with any trailing
      ``.`` or ``-`` stripped, since SPARQL permits hyphens and interior dots
      in a PN_LOCAL but a trailing dot is statement punctuation.

    - Prefix boundary: the prefix must be preceded by a non-name character, so
      that scanning for ``mds`` does not match inside ``xmds:Foo``.

    Version: 0.0.2

    Parameters
    ----------
    sparql_query : str
        A single SPARQL query string.
    domain_prefixes : list of str
        Namespace prefixes to scan for (e.g., ``["mds"]``).

    Returns
    -------
    set of str
        Local names referenced in the query under the given prefixes.

    Notes
    -----
    In version 0.0.1 the local-name pattern was ``[A-Za-z_][A-Za-z0-9_]*``,
    which truncated any term containing a hyphen or a dot -- ``mds:has-part``
    yielded ``has``. Such terms were then counted as absent from the ontology
    and depressed Recall.

    Examples
    --------
    >>> sorted(_extract_terms_from_sparql(
    ...     "SELECT ?x WHERE { ?x a mds:XrayDetector ; mds:has-part ?y }",
    ...     ["mds"]))
    ['XrayDetector', 'has-part']
    """
    terms = set()
    for prefix in domain_prefixes:
        pattern = rf'(?<![A-Za-z0-9_]){re.escape(prefix)}:([A-Za-z_][A-Za-z0-9_.\-]*)'
        for match in re.findall(pattern, sparql_query):
            cleaned = match.rstrip(".-")
            if cleaned:
                terms.add(cleaned)
    return terms


# ---------------------------------------------------------------------------
# Question loaders
# ---------------------------------------------------------------------------

def _load_json_questions(json_path):
    """
    Load SPARQL queries from a JSON competency-question file.

    Each element of the JSON array is expected to contain a ``sparql_query``
    key whose value is a SPARQL query string.  Elements without this key are
    skipped, and the number skipped is logged.

    Parameters
    ----------
    json_path : str or pathlib.Path
        Path to the JSON file.

    Returns
    -------
    list of str
        SPARQL query strings extracted from the file.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    queries = []
    skipped = 0
    for item in data:
        q = item.get("sparql_query", "")
        if q:
            queries.append(q)
        else:
            skipped += 1
    if skipped:
        logger.warning(
            f"{skipped} question(s) in {json_path} have no 'sparql_query' key "
            f"and were skipped."
        )
    return queries


def _extract_sparql_from_markdown(md_path):
    """
    Extract SPARQL queries from fenced code blocks in a Markdown file.

    Looks for blocks delimited by ````sparql`` and the closing ``````` and
    returns the content of each block as a separate string.

    Parameters
    ----------
    md_path : str or pathlib.Path
        Path to the Markdown file.

    Returns
    -------
    list of str
        SPARQL query strings found in the file.
    """
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    return re.findall(r"```sparql\s*(.*?)```", content, re.DOTALL)


# ---------------------------------------------------------------------------
# Main Function
# ---------------------------------------------------------------------------

def task_based_metric_v_0_0_1(ttl_file, questions, domain_prefixes,
                      domain_ns_fragments=None, auto_derive_fragments=True):
    """
    Compute task-based Recall and Precision for an ontology.

    Given an ontology (one or more Turtle files) and a set of competency
    questions expressed as SPARQL queries, this function computes two
    term-overlap metrics:

        Recall    = \\|T_a intersection T_o\\| / \\|T_a\\|
        Precision  = \\|T_a intersection T_o\\| / \\|T_o\\|

    where *T_a* is the union of domain terms extracted from all SPARQL
    queries and *T_o* is the set of domain terms defined in the ontology.

    Definitions
    -----------
    - T_a: local names appearing under any of *domain_prefixes* in the query
      set.

    - T_o: local names of non-foundational terms declared in the ontology,
      restricted to *domain_ns_fragments* when one is available.

    - Fragment derivation: when *domain_ns_fragments* is not supplied and
      *auto_derive_fragments* is true, the fragments are read from the parsed
      graph's own prefix bindings for *domain_prefixes*. Without this, stub
      declarations of imported CCO and BFO terms enter T_o and understate
      Precision.

    Version: 0.0.2

    Parameters
    ----------
    ttl_file : str, pathlib.Path, or list thereof
        Path(s) to Turtle (.ttl) ontology file(s).  A single string or
        ``Path`` is automatically wrapped in a list.
    questions : str, pathlib.Path, or list of str
        The competency questions to evaluate against.  Accepted forms:

        * **str / Path ending in .json** -- path to a JSON file where each
          array element has a ``sparql_query`` key.
        * **str / Path ending in .md** -- path to a Markdown file with
          SPARQL queries inside fenced ``sparql`` code blocks.
        * **list of str** -- raw SPARQL query strings.
    domain_prefixes : list of str
        Namespace prefixes used in the SPARQL queries to identify domain
        terms (e.g., ``["mds"]``).
    domain_ns_fragments : list of str or None, optional
        Sub-strings of namespace URIs used to restrict which ontology terms
        count as domain-specific.  When ``None`` and *auto_derive_fragments*
        is true, they are derived from the ontology's prefix bindings.
    auto_derive_fragments : bool, optional
        Whether to derive namespace fragments from the ontology's own prefix
        bindings when *domain_ns_fragments* is not supplied.  Default
        ``True``.  Set to ``False`` to restore the version 0.0.1 behaviour of
        including every non-foundational term in T_o.

    Returns
    -------
    dict
        A dictionary with the following keys:

        - ``recall`` (float): Recall -- fraction of task terms present
          in the ontology.
        - ``precision`` (float): Precision -- fraction of ontology terms
          referenced by the tasks.
        - ``task_coverage`` (float): alias of ``recall``.
        - ``ontology_utilization`` (float): alias of ``precision``, under the
          name the README uses for the same quantity.
        - ``T_o_count`` (int): Number of ontology domain terms.
        - ``T_a_count`` (int): Number of unique task terms.
        - ``intersection`` (int): Number of terms in both sets.
        - ``missing_from_onto`` (set of str): Task terms absent from the
          ontology.
        - ``unused_in_onto`` (set of str): Ontology terms not referenced
          by any task query.
        - ``domain_ns_fragments_used`` (list of str): the fragments actually
          applied, whether supplied or derived. Record this alongside any
          reported score.

    Raises
    ------
    ValueError
        If *questions* is not a recognized type (list, JSON path, or
        Markdown path).

    Notes
    -----
    Scores are not comparable between runs that used different namespace
    fragments. ``domain_ns_fragments_used`` is returned so that the setting
    can be reported with the score.

    Examples
    --------
    >>> result = task_based_metric_v_0_0_1(
    ...     ttl_file="my_ontology.ttl",
    ...     questions="competency_questions.json",
    ...     domain_prefixes=["mds"],
    ... )
    >>> print(f"Recall: {result['recall']:.2%}")
    >>> print(f"Precision:  {result['precision']:.2%}")
    """
    # Normalise ttl_file to a list
    if isinstance(ttl_file, (str, Path)):
        ttl_files = [ttl_file]
    else:
        ttl_files = list(ttl_file)

    # First pass: parse the graph without filtering, so that its prefix
    # bindings are available for fragment derivation.
    _, graph = _get_ontology_terms(ttl_files, None)

    fragments = domain_ns_fragments
    if not fragments and auto_derive_fragments:
        fragments = _derive_ns_fragments(graph, domain_prefixes)
        if fragments:
            logger.info(
                f"domain_ns_fragments not supplied; derived from the "
                f"ontology's prefix bindings: {fragments}"
            )
        else:
            logger.warning(
                "domain_ns_fragments not supplied and none could be derived. "
                "T_o will include every non-foundational term, including stub "
                "declarations of imported upper-level terms, which understates "
                "Precision. Pass --domain-ns-fragments explicitly."
            )

    # Build ontology term set (T_o) with the resolved fragments
    T_o, _ = _get_ontology_terms(ttl_files, fragments)

    # Build task term set (T_a) from SPARQL queries
    if isinstance(questions, (str, Path)):
        qs = str(questions)
        if qs.endswith(".json"):
            sparql_queries = _load_json_questions(qs)
        elif qs.endswith(".md"):
            sparql_queries = _extract_sparql_from_markdown(qs)
        else:
            raise ValueError(
                f"Unrecognised question file extension: {qs!r}. "
                "Expected .json or .md, or pass a list of SPARQL strings."
            )
    elif isinstance(questions, list):
        sparql_queries = questions
    else:
        raise ValueError(
            "The 'questions' argument must be a file path (str/Path to .json "
            "or .md) or a list of SPARQL query strings."
        )

    T_a = set()
    for q in sparql_queries:
        T_a.update(_extract_terms_from_sparql(q, domain_prefixes))

    # Compute metrics
    intersection = T_a & T_o
    i_count = len(intersection)

    recall = (i_count / len(T_a)) if len(T_a) > 0 else 0.0
    precision = (i_count / len(T_o)) if len(T_o) > 0 else 0.0

    return {
        "recall": recall,
        "precision": precision,
        # Aliases under the names the README uses for the same two quantities.
        "task_coverage": recall,
        "ontology_utilization": precision,
        "T_o_count": len(T_o),
        "T_a_count": len(T_a),
        "intersection": i_count,
        "missing_from_onto": T_a - T_o,
        "unused_in_onto": T_o - T_a,
        "domain_ns_fragments_used": list(fragments) if fragments else [],
        "query_count": len(sparql_queries),
    }
