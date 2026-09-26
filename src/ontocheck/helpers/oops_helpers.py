"""
Helper routines shared by the OOPS!-derived structural checks.

Private helpers follow the existing OntoCheck convention of a leading
underscore and live apart from the metric implementations themselves.

Source
------
OOPS! Pitfall Catalogue -- https://oops.linkeddata.es/catalogue.jsp

Version: 0.0.1
"""

import logging
import re

from rdflib import BNode, Graph, OWL, RDF, RDFS, SKOS, URIRef
from rdflib.namespace import DCTERMS, XSD

logger = logging.getLogger(__name__)


# Namespaces treated as foundational / upper-level.  Terms drawn from these
# are referenced rather than defined by a domain ontology, so several checks
# report them separately from terms in the ontology's own namespace.
_FOUNDATIONAL_NS = (
    str(RDF),
    str(RDFS),
    str(OWL),
    str(XSD),
    str(SKOS),
    str(DCTERMS),
    "http://purl.org/dc/elements/1.1/",
    "http://www.w3.org/2004/02/skos/core#",
    "http://qudt.org/schema/qudt/",
    "http://qudt.org/vocab/unit/",
    "http://www.w3.org/XML/1998/namespace",
    "http://www.w3.org/ns/prov#",
    "http://xmlns.com/foaf/0.1/",
    "http://purl.org/vocommons/voaf#",
    "http://www.w3.org/2003/06/sw-vocab-status/ns#",
)

# Annotation properties commonly used to carry a textual definition.
_DEFINITION_PREDICATES = (
    SKOS.definition,
    RDFS.comment,
    URIRef("http://purl.obolibrary.org/obo/IAO_0000115"),
    DCTERMS.description,
    URIRef("http://purl.org/dc/elements/1.1/description"),
)


def _bind_common_prefixes(g):
    """
    Bind the prefixes used across the MDS ontologies for readable output.

    Mirrors the prefix binding performed by the existing metrics so that
    ``URIRef.n3()`` renders compactly in log messages.

    Parameters
    ----------
    g : rdflib.Graph
        Graph to bind prefixes on.

    Returns
    -------
    rdflib.Graph
        The same graph, for chaining.
    """
    g.bind("mds", "https://cwrusdle.bitbucket.io/mds/")
    g.bind("cco", "https://www.commoncoreontologies.org/")
    g.bind("obo", "http://purl.obolibrary.org/obo/")
    g.bind("owl", "http://www.w3.org/2002/07/owl#")
    g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
    g.bind("skos", "http://www.w3.org/2004/02/skos/core#")
    g.bind("qudt", "http://qudt.org/schema/qudt/")
    return g


def _load_graph(ttl_file):
    """
    Parse a Turtle file into a prefix-bound graph.

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the Turtle (.ttl) ontology file.

    Returns
    -------
    rdflib.Graph or None
        The parsed graph, or ``None`` when the file is missing or unparseable.
        Errors are logged rather than raised, matching the behaviour of the
        existing metrics.
    """
    g = Graph()
    _bind_common_prefixes(g)
    try:
        g.parse(str(ttl_file), format="turtle")
    except FileNotFoundError:
        logger.error(f"The file '{ttl_file}' was not found.")
        return None
    except Exception as e:
        logger.error(f"An error occurred while parsing the TTL file: {e}")
        return None
    return g


def _is_foundational(uri):
    """
    Test whether a URI belongs to a foundational or upper-level namespace.

    Parameters
    ----------
    uri : rdflib.URIRef or str
        URI to test.

    Returns
    -------
    bool
        ``True`` when the URI begins with a foundational namespace prefix.
    """
    s = str(uri)
    return any(s.startswith(ns) for ns in _FOUNDATIONAL_NS)


def _namespace_of(uri):
    """
    Return the namespace portion of a URI.

    Splits on the last ``#`` when present, otherwise on the last ``/``.

    Parameters
    ----------
    uri : rdflib.URIRef or str
        URI to split.

    Returns
    -------
    str
        The namespace, including its trailing delimiter.  Returns the input
        unchanged when neither delimiter is present.
    """
    s = str(uri)
    if "#" in s:
        return s.rsplit("#", 1)[0] + "#"
    if "/" in s:
        return s.rsplit("/", 1)[0] + "/"
    return s


def _local_name(uri):
    """
    Return the local-name portion of a URI.

    Parameters
    ----------
    uri : rdflib.URIRef or str
        URI to split.

    Returns
    -------
    str
        The fragment after the last ``#``, or after the last ``/`` when no
        fragment delimiter is present.
    """
    s = str(uri)
    if "#" in s:
        frag = s.rsplit("#", 1)[-1]
        return frag.rsplit("/", 1)[-1] if "/" in frag else frag
    if "/" in s:
        return s.rsplit("/", 1)[-1]
    return s


def _ontology_iri(g):
    """
    Return the ontology's own IRI.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    rdflib.URIRef or None
        The subject of the ``owl:Ontology`` declaration, or ``None`` when no
        such declaration exists.  When several are present the first in
        sorted order is returned, for determinism.
    """
    decls = sorted(
        (s for s in g.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)),
        key=str,
    )
    return decls[0] if decls else None


_UPPER_ONTOLOGY_NS = (
    "https://www.commoncoreontologies.org/",
    "http://www.ontologyrepository.com/CommonCoreOntologies/",
    "http://purl.obolibrary.org/obo/",
)


def _own_namespace(g, min_share=0.10):
    """
    Infer the namespace(s) the ontology owns and mints terms in.

    Counts the namespaces of declared classes, properties and named
    individuals that carry at least one statement beyond their type
    declaration, excluding foundational vocabularies (RDF, OWL, SKOS, ...)
    and imported upper ontologies (CCO, OBO/BFO).  Every namespace holding
    at least ``min_share`` of those declarations is treated as owned.  The
    ``owl:Ontology`` IRI is used only as a tie-breaker and as a fallback when
    no declarations are found.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    min_share : float, optional
        Minimum fraction of declared terms a namespace must hold to count as
        owned.  Default ``0.10``.

    Returns
    -------
    str, tuple of str, or None
        A single namespace string, a tuple of namespace strings when the
        graph is a merge of modules minted in different namespaces, or
        ``None`` when nothing can be inferred.  Both forms work with
        ``str.startswith``.

    Notes
    -----
    Source: OntoCheck (SDLE, CWRU).  Replaces an IRI-first rule that failed
    on MDS modules whose ontology IRI (e.g. ``.../mds/EC-Equipment/Ontology``)
    differs from the term namespace (``.../mds/``), and on merged case-study
    files that contain two MDS namespaces.
    """
    decl_types = (
        OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
        OWL.AnnotationProperty, RDF.Property, OWL.NamedIndividual,
    )
    counts = {}
    for t in decl_types:
        for s in g.subjects(RDF.type, t):
            if not isinstance(s, URIRef) or _is_foundational(s):
                continue
            if str(s).startswith(_UPPER_ONTOLOGY_NS):
                continue
            # Bare declarations (``X a owl:Class .`` and nothing else) are
            # stubs for external terms, not terms minted here.
            if sum(1 for _ in g.predicate_objects(s)) <= 1:
                continue
            ns = _namespace_of(s)
            counts[ns] = counts.get(ns, 0) + 1

    if not counts:
        iri = _ontology_iri(g)
        if iri is None:
            return None
        s = str(iri)
        return s if s.endswith(("#", "/")) else _namespace_of(s)

    total = sum(counts.values())
    owned = sorted(
        (ns for ns, c in counts.items() if c / total >= min_share),
        key=lambda ns: -counts[ns],
    )
    if not owned:
        owned = [max(counts, key=counts.get)]
    return owned[0] if len(owned) == 1 else tuple(owned)


def _named_classes(g):
    """
    Collect every named class in the graph.

    Definitions
    -----------
    A named class is a ``URIRef`` that is declared ``owl:Class`` or
    ``rdfs:Class``, or that participates in an ``rdfs:subClassOf`` relation as
    either subject or object.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    set of rdflib.URIRef
        The named classes.
    """
    out = set()
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef):
            out.add(s)
    for s in g.subjects(RDF.type, RDFS.Class):
        if isinstance(s, URIRef):
            out.add(s)
    for s, o in g.subject_objects(RDFS.subClassOf):
        if isinstance(s, URIRef):
            out.add(s)
        if isinstance(o, URIRef):
            out.add(o)
    return out


def _named_properties(g):
    """
    Collect every named property in the graph.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    set of rdflib.URIRef
        Resources declared ``owl:ObjectProperty``, ``owl:DatatypeProperty``,
        ``owl:AnnotationProperty`` or ``rdf:Property``.
    """
    out = set()
    for t in (OWL.ObjectProperty, OWL.DatatypeProperty,
              OWL.AnnotationProperty, RDF.Property):
        for s in g.subjects(RDF.type, t):
            if isinstance(s, URIRef):
                out.add(s)
    return out


def _parse_rdf_list(g, node):
    """
    Materialise an RDF collection as a Python list.

    Parameters
    ----------
    g : rdflib.Graph
        Graph containing the collection.
    node : rdflib.term.Node
        Head of the ``rdf:first``/``rdf:rest`` chain.

    Returns
    -------
    list
        Members in order.  Returns an empty list for ``rdf:nil`` or a
        malformed chain.

    Notes
    -----
    Guards against cyclic ``rdf:rest`` chains, which would otherwise loop
    indefinitely on a malformed file.
    """
    items = []
    seen = set()
    current = node
    while current and current != RDF.nil:
        if current in seen:
            logger.warning("Cyclic rdf:rest chain encountered; truncating.")
            break
        seen.add(current)
        first = g.value(current, RDF.first)
        if first is not None:
            items.append(first)
        current = g.value(current, RDF.rest)
    return items


def _split_identifier(name):
    """
    Split a CamelCase or snake_case identifier into lowercase words.

    Used by the recursive-definition check (OOPS! P24) to compare a term's
    identifier against the text of its own definition.

    Parameters
    ----------
    name : str
        Identifier to split.

    Returns
    -------
    list of str
        Lowercased word tokens.

    Examples
    --------
    >>> _split_identifier("AlphaLathWidth")
    ['alpha', 'lath', 'width']
    >>> _split_identifier("has_decoupled_kinetics_from")
    ['has', 'decoupled', 'kinetics', 'from']
    """
    spaced = re.sub(r"[_\-]+", " ", str(name))
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    return [w.lower() for w in spaced.split() if w]


def _definitions_of(g, term):
    """
    Return every textual definition attached to a term.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    term : rdflib.term.Node
        Term whose definitions are wanted.

    Returns
    -------
    list of str
        Definition strings drawn from ``skos:definition``, ``rdfs:comment``,
        ``obo:IAO_0000115`` and Dublin Core ``description``.
    """
    out = []
    for p in _DEFINITION_PREDICATES:
        for o in g.objects(term, p):
            text = str(o).strip()
            if text:
                out.append(text)
    return out


def _disjoint_pairs(g):
    """
    Collect every pair of classes asserted to be disjoint.

    Covers both the binary ``owl:disjointWith`` form and the n-ary
    ``owl:AllDisjointClasses`` form, expanding the latter into all unordered
    pairs of its members.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    set of frozenset
        Each element is a two-member frozenset of ``URIRef``.

    Notes
    -----
    The MDS ontologies express disjointness almost entirely through
    ``owl:AllDisjointClasses``, so a check that inspects only
    ``owl:disjointWith`` would report a large number of false positives.
    """
    pairs = set()
    for s, o in g.subject_objects(OWL.disjointWith):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            pairs.add(frozenset((s, o)))

    for axiom in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members_node = g.value(axiom, OWL.members)
        if members_node is None:
            continue
        members = [m for m in _parse_rdf_list(g, members_node)
                   if isinstance(m, URIRef)]
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                pairs.add(frozenset((a, b)))
    return pairs


def _direct_parents(g):
    """
    Map each named class to its named direct superclasses.

    Anonymous superclasses (restrictions and Boolean class expressions) are
    excluded, since they do not participate in sibling or cycle analysis.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    dict
        Mapping from ``URIRef`` to a set of ``URIRef`` superclasses.
    """
    parents = {}
    for s, o in g.subject_objects(RDFS.subClassOf):
        if not isinstance(s, URIRef) or isinstance(o, BNode):
            continue
        if not isinstance(o, URIRef):
            continue
        parents.setdefault(s, set()).add(o)
    return parents
