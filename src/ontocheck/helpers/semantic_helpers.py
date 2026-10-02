"""
Helpers for the lexical, axiom-pattern and network OOPS!/FOOPS! checks.

These helpers support the pitfalls that need more than a single graph
traversal: WordNet lookups (P01, P02, P07, P12, P30), restriction and
subsumption analysis (P14, P15, P16, P18, P27, P28, P29, P31), an optional
DL reasoner (P31), and HTTP dereferencing (P37 and the FOOPS! access tests).

Every dependency beyond ``rdflib`` is optional.  When NLTK's WordNet corpus,
``owlready2`` with a Java runtime, or ``requests`` is unavailable, the helper
returns ``None`` and the calling check reports what it could not do rather
than raising.

Source
------
OntoCheck (SDLE Research Center, Case Western Reserve University).

Version: 0.0.1

.. note::

   Claude AI (Opus 5) was employed chiefly to support documentation efforts.
"""

import logging
import os
import re
import shutil
import tempfile
from functools import lru_cache

from rdflib import BNode, Graph, Literal, OWL, RDF, RDFS, SKOS, URIRef

from .oops_helpers import _local_name, _parse_rdf_list, _split_identifier

logger = logging.getLogger(__name__)

# Label-like predicates accepted by OOPS! P08 and FOOPS! VOC3.
LABEL_PREDICATES = (
    RDFS.label,
    SKOS.prefLabel,
    SKOS.altLabel,
    URIRef("http://www.w3.org/ns/lemon/ontolex#writtenRep"),
)

# Definition-like predicates.  OOPS! P08 names rdfs:comment and
# dc:description; skos:definition and IAO_0000115 are the conventions used by
# MDS-Onto and OBO ontologies respectively.
DEFINITION_PREDICATES = (
    RDFS.comment,
    SKOS.definition,
    URIRef("http://purl.org/dc/elements/1.1/description"),
    URIRef("http://purl.org/dc/terms/description"),
    URIRef("http://purl.obolibrary.org/obo/IAO_0000115"),
)

RESTRICTION_FILLERS = (
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.hasValue,
    OWL.onClass,
    OWL.onDataRange,
)


# ---------------------------------------------------------------------------
# Graph utilities
# ---------------------------------------------------------------------------

def _declared_kind(g, term):
    """
    Return the set of OWL kinds a term is declared as.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    term : rdflib.URIRef
        Term to inspect.

    Returns
    -------
    set of str
        Any of ``"class"``, ``"object"``, ``"datatype"``, ``"annotation"``
        and ``"individual"``.
    """
    kinds = set()
    types = set(g.objects(term, RDF.type))
    if types & {OWL.Class, RDFS.Class}:
        kinds.add("class")
    if OWL.ObjectProperty in types:
        kinds.add("object")
    if OWL.DatatypeProperty in types:
        kinds.add("datatype")
    if OWL.AnnotationProperty in types:
        kinds.add("annotation")
    if OWL.NamedIndividual in types:
        kinds.add("individual")
    return kinds


def _object_and_datatype_properties(g):
    """
    Return the declared object and datatype properties.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    set of rdflib.URIRef
        Properties typed ``owl:ObjectProperty`` or ``owl:DatatypeProperty``.
    """
    out = set()
    for t in (OWL.ObjectProperty, OWL.DatatypeProperty):
        out |= {s for s in g.subjects(RDF.type, t) if isinstance(s, URIRef)}
    return out


def _labels(g, term, predicates=LABEL_PREDICATES):
    """
    Return the non-empty label strings of a term.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    term : rdflib.term.Node
        Term to inspect.
    predicates : tuple of rdflib.URIRef, optional
        Predicates to read.  Defaults to :data:`LABEL_PREDICATES`.

    Returns
    -------
    list of rdflib.Literal
        Label literals with surrounding whitespace preserved.
    """
    out = []
    for p in predicates:
        for o in g.objects(term, p):
            if isinstance(o, Literal) and str(o).strip():
                out.append(o)
    return out


def _normalise(text):
    """
    Normalise an identifier or label for equality comparison.

    Parameters
    ----------
    text : str
        Identifier or label.

    Returns
    -------
    str
        Lower-case word tokens joined by single spaces, so that
        ``"XrayDetector"``, ``"x-ray detector"`` and ``"Xray_Detector"`` map
        to comparable strings.

    Examples
    --------
    >>> _normalise("Xray_Detector")
    'xray detector'
    """
    return " ".join(_split_identifier(re.sub(r"[^\w\s\-]", " ", str(text))))


def _is_opaque_identifier(name):
    """
    Test whether a local name is an opaque (numeric) identifier.

    Parameters
    ----------
    name : str
        Local name.

    Returns
    -------
    bool
        ``True`` for identifiers such as ``BFO_0000019`` or ``ont00000908``,
        which carry no lexical meaning and must not be compared lexically.
    """
    return bool(re.fullmatch(r"[A-Za-z]{0,6}_?\d{4,}", name))


def _lexical_forms(g, term):
    """
    Return the normalised lexical forms of a term.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    term : rdflib.URIRef
        Term to inspect.

    Returns
    -------
    set of str
        The normalised local name (unless opaque) and every normalised
        ``rdfs:label`` / ``skos:prefLabel``.
    """
    forms = set()
    name = _local_name(term)
    if name and not _is_opaque_identifier(name):
        forms.add(_normalise(name))
    for p in (RDFS.label, SKOS.prefLabel):
        for o in g.objects(term, p):
            if str(o).strip():
                forms.add(_normalise(o))
    forms.discard("")
    return forms


def _told_superclasses(g):
    """
    Compute the reflexive-transitive closure of told named subsumption.

    ``owl:equivalentClass`` between named classes is treated as mutual
    subsumption.  No reasoning over class expressions is performed.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    callable
        ``supers(c)`` returning the frozenset of named classes that subsume
        ``c``, including ``c`` itself.
    """
    direct = {}
    for s, o in g.subject_objects(RDFS.subClassOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            direct.setdefault(s, set()).add(o)
    for s, o in g.subject_objects(OWL.equivalentClass):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            direct.setdefault(s, set()).add(o)
            direct.setdefault(o, set()).add(s)

    cache = {}

    def supers(c):
        """Return the told superclasses of ``c``, including ``c``."""
        if c in cache:
            return cache[c]
        seen, stack = {c}, [c]
        while stack:
            for p in direct.get(stack.pop(), ()):
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        cache[c] = frozenset(seen)
        return cache[c]

    return supers


def _subsumed(supers, c, d):
    """
    Test told subsumption ``c`` ⊑ ``d``, treating ``owl:Thing`` as top.

    Parameters
    ----------
    supers : callable
        Closure returned by :func:`_told_superclasses`.
    c, d : rdflib.term.Node
        Classes to compare.

    Returns
    -------
    bool
        ``True`` if ``d`` is ``owl:Thing``/``rdfs:Resource`` or a told
        superclass of ``c``.
    """
    if d in (OWL.Thing, RDFS.Resource) or c == d:
        return True
    if not isinstance(c, URIRef):
        return False
    return d in supers(c)


def _restrictions_on(g, cls):
    """
    List the property restrictions used to describe a named class.

    Restrictions are collected from ``rdfs:subClassOf`` (necessary
    conditions) and from ``owl:equivalentClass`` (necessary and sufficient),
    including restrictions nested one level inside an ``owl:intersectionOf``.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    cls : rdflib.URIRef
        Class to inspect.

    Returns
    -------
    list of dict
        One dict per restriction with keys ``node``, ``property``,
        ``kind`` (the filler predicate or cardinality predicate),
        ``filler`` and ``axiom`` (``"subClassOf"`` or ``"equivalentClass"``).
    """
    out = []

    def collect(node, axiom):
        """Append the restrictions found in ``node`` to ``out``."""
        if not isinstance(node, BNode):
            return
        if (node, RDF.type, OWL.Restriction) in g:
            prop = g.value(node, OWL.onProperty)
            kind, filler = None, None
            for p in RESTRICTION_FILLERS + (
                OWL.minCardinality, OWL.maxCardinality, OWL.cardinality,
                OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality,
                OWL.qualifiedCardinality,
            ):
                v = g.value(node, p)
                if v is not None:
                    if p in RESTRICTION_FILLERS:
                        filler = v
                        if kind is None or p in (OWL.someValuesFrom,
                                                 OWL.allValuesFrom,
                                                 OWL.hasValue):
                            kind = p
                    else:
                        kind = p if kind is None else kind
            out.append({"node": node, "property": prop, "kind": kind,
                        "filler": filler, "axiom": axiom})
            return
        members = g.value(node, OWL.intersectionOf)
        if members is not None:
            for m in _parse_rdf_list(g, members):
                collect(m, axiom)

    for o in g.objects(cls, RDFS.subClassOf):
        collect(o, "subClassOf")
    for o in g.objects(cls, OWL.equivalentClass):
        collect(o, "equivalentClass")
    return out


def _owning_class(g, node, _depth=0):
    """
    Find the named class whose description contains an anonymous node.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.
    node : rdflib.BNode
        Restriction or class-expression node.

    Returns
    -------
    rdflib.URIRef or None
        The named subject of the ``rdfs:subClassOf`` or
        ``owl:equivalentClass`` axiom that (possibly through
        ``owl:intersectionOf`` lists) contains ``node``.
    """
    if _depth > 8:
        return None
    for p in (RDFS.subClassOf, OWL.equivalentClass):
        for s in g.subjects(p, node):
            if isinstance(s, URIRef):
                return s
    # node is an rdf:first of a list
    for lst in g.subjects(RDF.first, node):
        head = lst
        for _ in range(500):
            prev = next(g.subjects(RDF.rest, head), None)
            if prev is None:
                break
            head = prev
        for p in (OWL.intersectionOf, OWL.unionOf):
            for expr in g.subjects(p, head):
                owner = _owning_class(g, expr, _depth + 1)
                if owner is not None:
                    return owner
    return None


def _individuals(g):
    """
    Return the individuals asserted in the graph.

    Parameters
    ----------
    g : rdflib.Graph
        Parsed ontology graph.

    Returns
    -------
    dict
        Mapping from individual to the set of its asserted named types.
        An individual is any subject typed ``owl:NamedIndividual`` or typed
        with a class declared in the graph.

    Notes
    -----
    Punned IRIs -- declared as a class or property *and* as an individual
    (OOPS! P01) -- are excluded.  They are schema terms, not instance data,
    and counting them made a TBox-only file look like it carried an ABox.
    """
    classes = {s for t in (OWL.Class, RDFS.Class) for s in g.subjects(RDF.type, t)}
    schema = classes | {s for t in (OWL.ObjectProperty, OWL.DatatypeProperty,
                                    OWL.AnnotationProperty, RDF.Property)
                        for s in g.subjects(RDF.type, t)}
    out = {}
    for s, t in g.subject_objects(RDF.type):
        if s in schema:
            continue
        if t == OWL.NamedIndividual or t in classes:
            out.setdefault(s, set())
            if t in classes:
                out[s].add(t)
    return out


# ---------------------------------------------------------------------------
# WordNet
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _wordnet():
    """
    Load NLTK's WordNet corpus, downloading it once if necessary.

    Returns
    -------
    module or None
        ``nltk.corpus.wordnet`` when available, else ``None``.

    Notes
    -----
    Recent NLTK releases refuse downloads through an HTTP proxy unless
    ``nltk.pathsec.ALLOW_PROXIED_FETCH`` is set.  The flag is set only for
    the duration of the download attempt.
    """
    try:
        import nltk
        from nltk.corpus import wordnet as wn
    except ImportError:
        logger.warning("NLTK is not installed; WordNet-based checks degrade "
                       "to exact lexical matching.")
        return None
    try:
        wn.ensure_loaded()
        return wn
    except LookupError:
        pass
    try:
        pathsec = getattr(nltk, "pathsec", None)
        previous = getattr(pathsec, "ALLOW_PROXIED_FETCH", None)
        if pathsec is not None:
            pathsec.ALLOW_PROXIED_FETCH = True
        ok = nltk.download("wordnet", quiet=True)
        if pathsec is not None:
            pathsec.ALLOW_PROXIED_FETCH = previous
        if ok:
            wn.ensure_loaded()
            return wn
    except Exception as e:  # pragma: no cover - network dependent
        logger.warning(f"WordNet could not be loaded: {e}")
    return None


@lru_cache(maxsize=20000)
def _synsets(word, pos=None):
    """
    Return the WordNet synset names for a word.

    Parameters
    ----------
    word : str
        Lower-case word or underscore-joined phrase.
    pos : str or None, optional
        WordNet part of speech (``"n"``, ``"v"``, ``"a"``, ``"r"``).

    Returns
    -------
    frozenset of str
        Synset identifiers; empty when WordNet is unavailable or the word is
        unknown.
    """
    wn = _wordnet()
    if wn is None:
        return frozenset()
    try:
        return frozenset(s.name() for s in wn.synsets(word, pos=pos))
    except Exception:
        return frozenset()


@lru_cache(maxsize=20000)
def _dominant_and_all(word, pos):
    """
    Return a word's most frequent WordNet sense and all of its senses.

    Parameters
    ----------
    word : str
        Lower-case word.
    pos : str
        WordNet part of speech.

    Returns
    -------
    tuple
        ``(dominant, senses)`` where ``dominant`` is the first synset name
        (WordNet orders senses by frequency) or ``None``, and ``senses`` is
        a frozenset of all synset names.
    """
    wn = _wordnet()
    if wn is None:
        return None, frozenset()
    try:
        syns = wn.synsets(word, pos=pos)
    except Exception:
        return None, frozenset()
    return (syns[0].name() if syns else None,
            frozenset(s.name() for s in syns))


def _are_synonyms(a, b, pos="n"):
    """
    Test whether two words are synonyms in their dominant WordNet senses.

    Parameters
    ----------
    a, b : str
        Lower-case words.
    pos : str, optional
        Part of speech.  Default ``"n"``.

    Returns
    -------
    bool
        ``True`` when the words differ and each word's most frequent sense is
        also a sense of the other word.

    Notes
    -----
    Sharing *any* synset is too permissive for technical vocabularies:
    WordNet lists "capacitance" as a rare synonym of the device "capacitor",
    so an any-sense test would call ``Capacitor`` and ``Capacitance``
    synonyms.  Requiring mutual dominant senses keeps pairs such as
    car/automobile, detector/sensor and solvent/dissolvent.

    Examples
    --------
    >>> _are_synonyms("detector", "sensor")      # doctest: +SKIP
    True
    >>> _are_synonyms("capacitor", "capacitance")  # doctest: +SKIP
    False
    """
    if a == b or len(a) < 3 or len(b) < 3:
        return False
    da, sa = _dominant_and_all(a, pos)
    db, sb = _dominant_and_all(b, pos)
    return bool(da and db and da in sb and db in sa)


def _synonym_variant(tokens_a, tokens_b, pos="n"):
    """
    Test whether two identifiers differ by exactly one synonymous token.

    Parameters
    ----------
    tokens_a, tokens_b : list of str
        Tokenised identifiers.
    pos : str, optional
        Part of speech used for the differing token.

    Returns
    -------
    tuple of str or None
        The differing ``(token_a, token_b)`` pair when the identifiers have
        equal length, differ in exactly one position, and the differing
        tokens are WordNet synonyms; otherwise ``None``.
    """
    if len(tokens_a) != len(tokens_b) or not tokens_a:
        return None
    diff = [(x, y) for x, y in zip(tokens_a, tokens_b) if x != y]
    if len(diff) != 1:
        return None
    x, y = diff[0]
    return (x, y) if _are_synonyms(x, y, pos) else None


# ---------------------------------------------------------------------------
# Reasoner
# ---------------------------------------------------------------------------

def _reasoner_available():
    """
    Report whether a DL reasoner can be run.

    Returns
    -------
    bool
        ``True`` when ``owlready2`` imports and a ``java`` executable is on
        the path (HermiT runs on the JVM).
    """
    try:
        import owlready2  # noqa: F401
    except ImportError:
        return False
    return shutil.which("java") is not None


# Datatypes in the OWL 2 datatype map (OWL 2 Structural Specification, 4).
# HermiT rejects any other datatype, e.g. xsd:date or xsd:gYear.
_XSD_NS = "http://www.w3.org/2001/XMLSchema#"
OWL2_DATATYPES = {URIRef(_XSD_NS + n) for n in (
    "decimal", "integer", "nonNegativeInteger", "nonPositiveInteger",
    "positiveInteger", "negativeInteger", "long", "int", "short", "byte",
    "unsignedLong", "unsignedInt", "unsignedShort", "unsignedByte", "double",
    "float", "string", "normalizedString", "token", "language", "Name",
    "NCName", "NMTOKEN", "boolean", "hexBinary", "base64Binary", "anyURI",
    "dateTime", "dateTimeStamp")} | {
    URIRef("http://www.w3.org/2002/07/owl#real"),
    URIRef("http://www.w3.org/2002/07/owl#rational"),
    RDF.PlainLiteral, RDF.XMLLiteral, RDF.langString, RDFS.Literal}


def _relax_datatypes(g):
    """
    Replace datatypes outside the OWL 2 datatype map by ``rdfs:Literal``.

    Parameters
    ----------
    g : rdflib.Graph
        Graph to modify in place.

    Returns
    -------
    list of str
        The datatype IRIs that were relaxed, sorted.

    Notes
    -----
    Affects XSD types such as ``xsd:date``, ``xsd:time`` and ``xsd:gYear``,
    undeclared datatypes used as the range of a datatype property (e.g. a
    mistyped XSD namespace), and typed literals of either.  Only datatype
    reasoning is weakened; class and property reasoning, which P31 relies
    on, is unaffected.
    """
    data_props = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    declared = set(g.subjects(RDF.type, RDFS.Datatype))
    relaxed = set()
    for s, p, o in list(g):
        if isinstance(o, Literal) and o.datatype is not None \
                and o.datatype not in OWL2_DATATYPES and o.datatype not in declared:
            relaxed.add(str(o.datatype))
            g.remove((s, p, o))
            g.add((s, p, Literal(str(o))))
        elif isinstance(o, URIRef) and o not in OWL2_DATATYPES and o not in declared and (
                str(o).startswith(_XSD_NS)
                or (p == RDFS.range and s in data_props)):
            relaxed.add(str(o))
            g.remove((s, p, o))
            g.add((s, p, RDFS.Literal))
    return sorted(relaxed)


def _declare_untyped_classes(g):
    """
    Declare as ``owl:Class`` the untyped IRIs that are used as classes.

    Parameters
    ----------
    g : rdflib.Graph
        Graph to modify in place.

    Returns
    -------
    list of str
        The IRIs that were declared, sorted.

    Notes
    -----
    An IRI used as an ``rdfs:domain``, an ``rdfs:subClassOf`` term, or the
    range or restriction filler of an object property, but never typed (OOPS!
    P34), is ambiguous to the OWL API: in a data-property axiom it can be
    read as a datatype, which HermiT then rejects.  Declaring it as a class
    is the repair P34 recommends and leaves the ontology's meaning intact.
    """
    typed = set(g.subjects(RDF.type, None))
    obj_props = set(g.subjects(RDF.type, OWL.ObjectProperty))
    used = set(g.objects(None, RDFS.domain)) | set(g.objects(None, RDFS.subClassOf)) \
        | set(g.subjects(RDFS.subClassOf, None))
    used |= {o for s, o in g.subject_objects(RDFS.range) if s in obj_props}
    for r in g.subjects(RDF.type, OWL.Restriction):
        if g.value(r, OWL.onProperty) in obj_props:
            used |= {g.value(r, p) for p in (OWL.someValuesFrom, OWL.allValuesFrom,
                                              OWL.onClass)}
    declared = sorted(str(u) for u in used
                      if isinstance(u, URIRef) and u not in typed
                      and not str(u).startswith((str(OWL), str(RDFS), str(RDF), _XSD_NS)))
    for u in declared:
        g.add((URIRef(u), RDF.type, OWL.Class))
    return declared


@lru_cache(maxsize=16)
def _run_reasoner(ttl_file):
    """
    Classify an ontology with HermiT and return the inferences of interest.

    Parameters
    ----------
    ttl_file : str
        Path to the Turtle file.

    Returns
    -------
    dict or None
        ``None`` when no reasoner is available or reasoning failed.
        Otherwise a dict with ``consistent`` (bool), ``unsatisfiable``
        (sorted list of class IRIs) and ``equivalent_sets`` (list of sorted
        lists of named class IRIs that the reasoner places in one
        equivalence set, including asserted equivalences),
        ``relaxed_datatypes`` (see :func:`_relax_datatypes`) and
        ``declared_untyped_classes`` (see :func:`_declare_untyped_classes`).

    Notes
    -----
    The Turtle file is re-serialised to N-Triples because ``owlready2`` does
    not parse Turtle.  Datatypes HermiT cannot handle are relaxed to
    ``rdfs:Literal`` and untyped IRIs used as classes are declared first.
    Results are cached per path.
    """
    if not _reasoner_available():
        return None
    import owlready2

    g = Graph()
    try:
        g.parse(str(ttl_file), format="turtle")
    except Exception as e:
        logger.error(f"Reasoner input could not be parsed: {e}")
        return None
    relaxed = _relax_datatypes(g)
    if relaxed:
        logger.info(f"Datatypes relaxed for HermiT: {relaxed}")
    untyped = _declare_untyped_classes(g)
    if untyped:
        logger.info(f"Untyped classes declared for HermiT: {untyped}")
    fd, path = tempfile.mkstemp(suffix=".nt")
    os.close(fd)
    try:
        g.serialize(path, format="nt", encoding="utf-8")
        world = owlready2.World()
        onto = world.get_ontology("file://" + path).load()
        try:
            with onto:
                owlready2.sync_reasoner_hermit(
                    world, infer_property_values=False, debug=0
                )
        except owlready2.OwlReadyInconsistentOntologyError:
            return {"consistent": False, "unsatisfiable": [],
                    "equivalent_sets": [], "relaxed_datatypes": relaxed,
                    "declared_untyped_classes": untyped}
        unsat = sorted(c.iri for c in world.inconsistent_classes()
                       if hasattr(c, "iri"))
        eq_sets = set()
        for c in world.classes():
            equivs = {e.iri for e in c.equivalent_to
                      if isinstance(e, owlready2.ThingClass)}
            if equivs:
                eq_sets.add(tuple(sorted(equivs | {c.iri})))
        return {"consistent": True, "unsatisfiable": unsat,
                "equivalent_sets": sorted(list(s) for s in eq_sets),
                "relaxed_datatypes": relaxed,
                "declared_untyped_classes": untyped}
    except Exception as e:
        lines = [ln for ln in str(e).splitlines() if ln.strip()]
        reason = next((ln for ln in lines if "Exception" in ln), lines[0] if lines else "")
        logger.warning(f"Reasoning failed ({type(e).__name__}): {reason.strip()[:300]}")
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

RDF_MEDIA_TYPES = {
    "application/rdf+xml": "xml",
    "text/turtle": "turtle",
    "application/n-triples": "nt",
    "text/n3": "n3",
    "application/ld+json": "json-ld",
}


def _http_get(url, accept, timeout=10):
    """
    Dereference a URL with content negotiation.

    Parameters
    ----------
    url : str
        URL to request.
    accept : str
        Value of the ``Accept`` header.
    timeout : int or float, optional
        Timeout in seconds.  Default 10.

    Returns
    -------
    dict
        Keys ``status`` (int or None), ``final_url``, ``content_type``
        (media type without parameters, lower-cased), ``text`` (body, at most
        5 MB) and ``error`` (str or None).  Redirects are followed.
    """
    out = {"status": None, "final_url": None, "content_type": None,
           "text": None, "error": None}
    try:
        import requests
    except ImportError:
        out["error"] = "requests is not installed"
        return out
    try:
        r = requests.get(url, headers={"Accept": accept}, timeout=timeout,
                         allow_redirects=True)
        out["status"] = r.status_code
        out["final_url"] = r.url
        ct = r.headers.get("Content-Type", "") or ""
        out["content_type"] = ct.split(";")[0].strip().lower() or None
        out["text"] = r.text[:5_000_000] if r.status_code < 400 else None
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _parse_rdf_response(response):
    """
    Parse the body of an HTTP response as RDF.

    Parameters
    ----------
    response : dict
        Result of :func:`_http_get`.

    Returns
    -------
    rdflib.Graph or None
        The parsed graph when the response carried a recognised RDF media
        type (or an untyped body that parses as RDF) and was non-empty;
        otherwise ``None``.

    Notes
    -----
    HTML is never parsed.  A server that answers an RDF request with an HTML
    page (common for static documentation hosts) must count as "no RDF".
    Feeding HTML to the lenient Turtle parser yields junk triples such as
    ``<file:///cwd/!DOCTYPE html>``, which earlier made CN1, URI1, URI2 and
    P37 report RDF as available when it was not.  Relative IRIs are resolved
    against the response URL, not the working directory.
    """
    text = response.get("text")
    if not text:
        return None
    ct = response.get("content_type") or ""
    head = text.lstrip()[:200].lower()
    if ct in ("text/html", "application/xhtml+xml") or head.startswith(
            ("<!doctype html", "<html")):
        return None
    if ct in RDF_MEDIA_TYPES:
        formats = [RDF_MEDIA_TYPES[ct]]
    elif ct in ("", "text/plain", "application/octet-stream", "application/xml",
                "text/xml", "application/json"):
        formats = ["turtle", "xml", "json-ld", "nt"]
    else:
        return None
    base = response.get("final_url") or None
    for fmt in formats:
        g = Graph()
        try:
            g.parse(data=text, format=fmt, publicID=base)
            if len(g):
                return g
        except Exception:
            continue
    return None