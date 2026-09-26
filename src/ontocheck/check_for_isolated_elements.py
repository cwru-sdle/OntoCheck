"""
check_for_isolated_elements metric implementation.

Changelog (v0.0.2)
------------------
- FIXED: every value in the returned dictionary was wrapped in braces, e.g.
  ``{"Number of isolated classes": {len(isolated_atomic_classes)}}``, which
  produced a one-element ``set`` rather than a number. Any downstream
  arithmetic, comparison or CSV formatting on these values misbehaved. The
  braces have been removed.
- FIXED: ``len(isolated_atomic_classes) / len(atomic_classes)`` and the
  equivalent for properties raised ``ZeroDivisionError`` on an ontology with
  no atomic classes or no declared object/datatype properties. Both are now
  guarded.
- FIXED: the log message used a forward slash, ``f"/nProportion ..."``,
  instead of a newline escape. Corrected to ``\\n``.
- ADDED: snake_case keys alongside the original human-readable keys, so
  results can be accessed programmatically without string literals containing
  spaces. The original keys are retained for backward compatibility.
"""

from rdflib import OWL, SKOS, RDF, RDFS, Graph, Namespace, DCAT, URIRef, BNode
import networkx as nx
import rdflib
import logging
from .helpers.helpers import _parse_rdf_list, _constructed_class_has_atomic_class, _get_operands

logger = logging.getLogger(__name__)

def check_for_isolated_elements(ttl_file: str):
    """
    C1 - Number of isolated elements

    Analyze an OWL ontology in Turtle format to identify isolated atomic classes and isolated properties.

    Definitions
    -----------
    - Atomic classes are named classes (with URI) that are NOT constructed classes
      (i.e., they do not have owl:unionOf, owl:intersectionOf, or owl:complementOf).

    - A class (atomic or constructed with URI) is considered connected if it:
        * participates in rdfs:subClassOf, owl:equivalentClass, or owl:disjointWith relations
          involving atomic classes, OR
        * is used as domain or range of properties and contains at least one atomic class
          inside its construction.

    - A property is considered connected if it is related by any of:
      rdfs:subPropertyOf, owl:inverseOf, owl:propertyDisjointWith, or owl:equivalentProperty.

    - Proportion: the count of isolated elements divided by the total count of
      elements of that kind. Defined as 0.0 when the total is zero, so that an
      ontology with no declared properties reports "no isolated properties"
      rather than raising.

    Author: Van Tran
    Version: 0.0.2

    Parameters
    ----------
    ttl_file : str
        File path to the ontology Turtle (.ttl) file.

    Returns
    -------
    dict
        A dictionary containing both human-readable and snake_case keys:

        - ``"Number of isolated classes"`` / ``num_isolated_classes`` (int)
        - ``"Proportion of isolated classes"`` / ``proportion_isolated_classes`` (float)
        - ``"Number of isolated properties"`` / ``num_isolated_properties`` (int)
        - ``"Proportion of isolated properties"`` / ``proportion_isolated_properties`` (float)
        - ``total_atomic_classes`` (int)
        - ``total_properties`` (int)
        - ``isolated_classes`` (list of str): the URIs themselves
        - ``isolated_properties`` (list of str): the URIs themselves

        In version 0.0.1 the four original values were ``set`` objects
        containing a single number, because each was written as ``{value}``.
        They are now plain ``int`` and ``float``.

    Prints
    ------
    Lists of isolated atomic classes and isolated properties.

    Notes
    -----
    - Only named classes explicitly declared as owl:Class are considered.
    - Only properties explicitly declared as owl:ObjectProperty or owl:DatatypeProperty are considered.
    - Relations checked for classes include rdfs:subClassOf, owl:equivalentClass, owl:disjointWith,
      and usage as domain or range of properties.
    - Relations checked for properties include rdfs:subPropertyOf, owl:inverseOf, owl:propertyDisjointWith,
      and owl:equivalentProperty.

    References
    -----
    Mc Gurk, S., Abela, C., & Debattista, J. (2017). Towards ontology quality assessment.
    4th Workshop on Linked Data Quality (LDQ2017), co-located with the 14th Extended Semantic Web Conference (ESWC),
    Portorož, 94-106.

    """
    g = Graph()
    g.parse(ttl_file, format="turtle")

    # All named classes
    named_classes = set(g.subjects(RDF.type, OWL.Class))

    # Identify atomic classes: named classes without OWL class constructors
    atomic_classes = set()
    for c in named_classes:
        # Check for Boolean class expressions
        has_boolean = any(
            len(list(g.objects(c, p))) > 0
            for p in [OWL.unionOf, OWL.intersectionOf, OWL.complementOf]
        )

        # Check for restrictions in equivalentClass or subClassOf
        has_restriction = False
        for p in [OWL.equivalentClass, RDFS.subClassOf]:
            for obj in g.objects(c, p):
                if (obj, RDF.type, OWL.Restriction) in g:
                    has_restriction = True
                    logger.debug(f"{c} has restriction via {p} → {obj}")

        if has_boolean:
            logger.debug(f"{c} excluded because it has a boolean expression")

        if not has_boolean and not has_restriction:
            atomic_classes.add(c)
            logger.info(f"Added atomic class: {c}")
        else:
            logger.info(f"Skipped non-atomic class: {c}")

    properties = set(g.subjects(RDF.type, OWL.ObjectProperty)) | set(g.subjects(RDF.type, OWL.DatatypeProperty))

    connected_atomic = set()

    # Relations linking atomic classes
    for pred in [RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith]:
        for s, o in g.subject_objects(pred):
            if s in atomic_classes and o in atomic_classes:
                connected_atomic.add(s)
                connected_atomic.add(o)
            else:
                # If constructed classes involved, check their atomic content
                if _constructed_class_has_atomic_class(s, g, atomic_classes):
                    if isinstance(o, URIRef) and o in atomic_classes:
                        connected_atomic.add(o)
                if _constructed_class_has_atomic_class(o, g, atomic_classes):
                    if isinstance(s, URIRef) and s in atomic_classes:
                        connected_atomic.add(s)

    # Consider domain and range usage of properties
    for prop in properties:
        for domain in g.objects(prop, RDFS.domain):
            if _constructed_class_has_atomic_class(domain, g, atomic_classes):
                if isinstance(domain, URIRef):
                    connected_atomic.add(domain)
        for range_ in g.objects(prop, RDFS.range):
            if _constructed_class_has_atomic_class(range_, g, atomic_classes):
                if isinstance(range_, URIRef):
                    connected_atomic.add(range_)

    isolated_atomic_classes = atomic_classes - connected_atomic

    # Properties isolation
    connected_properties = set()
    for pred in [RDFS.subPropertyOf, OWL.inverseOf, OWL.propertyDisjointWith, OWL.equivalentProperty, SKOS.broader]:
        for s, o in g.subject_objects(pred):
            if isinstance(s, URIRef):
                connected_properties.add(s)
            if isinstance(o, URIRef):
                connected_properties.add(o)

    isolated_properties = properties - connected_properties

    logger.info("Isolated Atomic Classes:")
    for cls in sorted(isolated_atomic_classes):
        logger.info(f"  {cls}")

    # Guard against division by zero: an ontology with no atomic classes or no
    # declared properties previously raised ZeroDivisionError here.
    ratio_iso_to_total_class = (
        len(isolated_atomic_classes) / len(atomic_classes) if atomic_classes else 0.0
    )

    logger.info(f"Number of isolated classes: {len(isolated_atomic_classes)}")
    logger.info(f"\nProportion of isolated classes: {ratio_iso_to_total_class}")

    logger.info("Isolated Properties:")
    for prop in sorted(isolated_properties):
        logger.info(f"  {prop}")

    ratio_iso_to_total_prop = (
        len(isolated_properties) / len(properties) if properties else 0.0
    )

    logger.info(f"Number of isolated properties: {len(isolated_properties)}")
    logger.info(f"\nProportion of isolated properties: {ratio_iso_to_total_prop}")

    return {
        # Original human-readable keys, now holding plain numbers rather than
        # single-element sets.
        "Number of isolated classes": len(isolated_atomic_classes),
        "Proportion of isolated classes": ratio_iso_to_total_class,
        "Number of isolated properties": len(isolated_properties),
        "Proportion of isolated properties": ratio_iso_to_total_prop,
        # Programmatic keys.
        "num_isolated_classes": len(isolated_atomic_classes),
        "proportion_isolated_classes": ratio_iso_to_total_class,
        "num_isolated_properties": len(isolated_properties),
        "proportion_isolated_properties": ratio_iso_to_total_prop,
        "total_atomic_classes": len(atomic_classes),
        "total_properties": len(properties),
        "isolated_classes": sorted(str(c) for c in isolated_atomic_classes),
        "isolated_properties": sorted(str(p) for p in isolated_properties),
    }
