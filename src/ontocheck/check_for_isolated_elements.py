from rdflib import OWL, SKOS, RDF, RDFS, Graph, Namespace, DCAT, URIRef, BNode
import networkx as nx
import rdflib
from .helpers.helpers import _parse_rdf_list, _constructed_class_has_atomic_class, _get_operands

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

    Author: Van Tran
    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str
        File path to the ontology Turtle (.ttl) file.

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
                    print(f"[DEBUG] {c} has restriction via {p} → {obj}")

        if has_boolean:
            print(f"[DEBUG] {c} excluded because it has a boolean expression")

        if not has_boolean and not has_restriction:
            atomic_classes.add(c)
            print(f"[INFO] Added atomic class: {c}")
        else:
            print(f"[INFO] Skipped non-atomic class: {c}")

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

    print("Isolated Atomic Classes:")
    for cls in sorted(isolated_atomic_classes):
        print(f"  {cls}")

    ratio_iso_to_total_class = len(isolated_atomic_classes)/len(atomic_classes)

    print(f"Number of isolated classes: {len(isolated_atomic_classes)}")
    print(f"/nProportion of isolated classes: {ratio_iso_to_total_class}")

    print("\nIsolated Properties:")
    for prop in sorted(isolated_properties):
        print(f"  {prop}")

    ratio_iso_to_total_prop = len(isolated_properties)/len(properties)
    
    print(f"Number of isolated properties: {len(isolated_properties)}")
    print(f"/nProportion of isolated properties: {ratio_iso_to_total_prop}")

    return {
        "Number of isolated classes": {len(isolated_atomic_classes)},
        "Proportion of isolated classes": {ratio_iso_to_total_class},
        "Number of isolated properties": {len(isolated_properties)},
        "Proportion of isolated properties": {ratio_iso_to_total_prop}
    }
