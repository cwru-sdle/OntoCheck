"""
Task-Based Ontology Assessment Metric

Evaluates an ontology against a set of competency questions (encoded as SPARQL
queries) by computing term-overlap metrics. For each question set, two scores
are produced:

    Relevance (Recall)    = \|T_a intersection T_o\| / \|T_a\|
    Accuracy  (Precision) = \|T_a intersection T_o\| / \|T_o\|

where T_a is the set of domain terms referenced in the SPARQL queries (the
"task vocabulary") and T_o is the set of domain terms defined in the ontology.

Questions can be supplied as:
    - A path to a JSON file where each item contains a ``sparql_query`` key.
    - A path to a Markdown file with SPARQL queries inside ``sparql`` blocks.
    - A plain list of SPARQL query strings.

Author: Redad Mehdi
"""

import re
import json
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD


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
    set of str
        Local names of the ontology's domain terms.
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

    return ontology_terms


# ---------------------------------------------------------------------------
# SPARQL term extraction
# ---------------------------------------------------------------------------

def _extract_terms_from_sparql(sparql_query, domain_prefixes):
    """
    Extract prefixed local names from a SPARQL query string.

    For each prefix in *domain_prefixes*, a regex search finds all occurrences
    of ``prefix:LocalName`` and collects the local name parts.

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
    """
    terms = set()
    for prefix in domain_prefixes:
        pattern = rf'{re.escape(prefix)}:([A-Za-z_][A-Za-z0-9_]*)'
        matches = re.findall(pattern, sparql_query)
        terms.update(matches)
    return terms


# ---------------------------------------------------------------------------
# Question loaders
# ---------------------------------------------------------------------------

def _load_json_questions(json_path):
    """
    Load SPARQL queries from a JSON competency-question file.

    Each element of the JSON array is expected to contain a ``sparql_query``
    key whose value is a SPARQL query string.  Elements without this key are
    silently skipped.

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
    for item in data:
        q = item.get("sparql_query", "")
        if q:
            queries.append(q)
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
                      domain_ns_fragments=None):
    """
    Compute task-based Relevance and Accuracy for an ontology.

    Given an ontology (one or more Turtle files) and a set of competency
    questions expressed as SPARQL queries, this function computes two
    term-overlap metrics:

        Relevance (Recall)    = \|T_a intersection T_o\| / \|T_a\|
        Accuracy  (Precision) = \|T_a intersection T_o\| / \|T_o\|

    where *T_a* is the union of domain terms extracted from all SPARQL
    queries and *T_o* is the set of domain terms defined in the ontology.

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
        count as domain-specific.  When ``None``, every non-foundational
        term is included.

    Returns
    -------
    dict
        A dictionary with the following keys:

        - ``relevance`` (float): Recall -- fraction of task terms present
          in the ontology.
        - ``accuracy`` (float): Precision -- fraction of ontology terms
          referenced by the tasks.
        - ``T_o_count`` (int): Number of ontology domain terms.
        - ``T_a_count`` (int): Number of unique task terms.
        - ``intersection`` (int): Number of terms in both sets.
        - ``missing_from_onto`` (set of str): Task terms absent from the
          ontology.
        - ``unused_in_onto`` (set of str): Ontology terms not referenced
          by any task query.

    Raises
    ------
    ValueError
        If *questions* is not a recognized type (list, JSON path, or
        Markdown path).

    Examples
    --------
    >>> result = task_based_metric_v_0_0_1(
    ...     ttl_file="my_ontology.ttl",
    ...     questions="competency_questions.json",
    ...     domain_prefixes=["mds"],
    ...     domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
    ... )
    >>> print(f"Relevance: {result['relevance']:.2%}")
    >>> print(f"Accuracy:  {result['accuracy']:.2%}")
    """
    # Normalise ttl_file to a list
    if isinstance(ttl_file, (str, Path)):
        ttl_files = [ttl_file]
    else:
        ttl_files = list(ttl_file)

    # Build ontology term set (T_o)
    T_o = _get_ontology_terms(ttl_files, domain_ns_fragments)

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

    relevance = (i_count / len(T_a)) if len(T_a) > 0 else 0.0
    accuracy = (i_count / len(T_o)) if len(T_o) > 0 else 0.0

    return {
        "relevance": relevance,
        "accuracy": accuracy,
        "T_o_count": len(T_o),
        "T_a_count": len(T_a),
        "intersection": i_count,
        "missing_from_onto": T_a - T_o,
        "unused_in_onto": T_o - T_a,
    }
