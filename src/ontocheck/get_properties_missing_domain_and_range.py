from rdflib import OWL, SKOS, RDF, RDFS, Graph, Namespace, DCAT, URIRef, BNode
import networkx as nx
import rdflib

def get_properties_missing_domain_and_range(ttl_file_path: str):
    """
    C2 - Missing Domain and Ranges in Properties

    Parse an OWL ontology Turtle file and identify object and datatype properties
    that are missing domain or range declarations.

    Author: Van Tran
    Version: 0.0.1

    Parameters
    ----------
    ttl_file_path : str
        Path to the Turtle (.ttl) file containing the ontology.

    Returns
    -------
    dict
        A dictionary containing:

        - 'count_missing_domain': int
            Number of properties missing an rdfs:domain declaration.
        - 'properties_missing_domain': list of rdflib.term.URIRef
            List of properties (URIs) missing an rdfs:domain.
        - 'count_missing_range': int
            Number of properties missing an rdfs:range declaration.
        - 'properties_missing_range': list of rdflib.term.URIRef
            List of properties (URIs) missing an rdfs:range.

    Notes
    -----
    - Only properties explicitly typed as owl:ObjectProperty or owl:DatatypeProperty
      are considered.

    References
    ----------
    Mc Gurk, S., Abela, C., & Debattista, J. (2017). Towards ontology quality assessment.
    4th Workshop on Linked Data Quality (LDQ2017), co-located with the 14th Extended Semantic Web Conference (ESWC),
    Portorož, 94-106.
    """
    g = Graph()
    g.parse(ttl_file_path, format="turtle")

    # Get all object and datatype properties
    object_props = set(g.subjects(RDF.type, OWL.ObjectProperty))
    datatype_props = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    all_props = object_props | datatype_props

    # Properties that have domain or range defined
    props_with_domain = set(g.subjects(RDFS.domain, None))
    props_with_range = set(g.subjects(RDFS.range, None))

    # Find properties missing domain or range
    missing_domain = [p for p in all_props if p not in props_with_domain]
    missing_range = [p for p in all_props if p not in props_with_range]

    return {
        "count_missing_domain": len(missing_domain),
        "properties_missing_domain": missing_domain,
        "count_missing_range": len(missing_range),
        "properties_missing_range": missing_range,
    }
