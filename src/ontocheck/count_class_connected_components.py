from rdflib import OWL, SKOS, RDF, RDFS, Graph, Namespace, DCAT, URIRef, BNode
import networkx as nx
import rdflib

def count_class_connected_components(ttl_file_path: str) -> int:
    """
    C3 - Count number of connected subgraphs

    Count the number of connected components in the "class graph" (TBox) of an OWL ontology.
    The "class graph" is constructed by creating undirected edges between classes that are connected
    by any of the following OWL predicates:

    - rdfs:subClassOf
    - owl:equivalentClass
    - owl:disjointWith

    Nodes in the graph represent named classes (URIRefs) from the ontology. Edges represent these
    relationships between named classes. Classes involved only in subclass/equivalent/disjointWith
    axioms pointing to blank nodes (i.e. constructed classes) are excluded.

    Author: Van Tran
    Version: 0.0.1

    Parameters
    ----------
    ttl_file_path : str
        Path to the ontology Turtle (.ttl) file.

    Returns
    -------
    int
        The number of connected components in the class graph.

    Notes
    -----
    - The graph is undirected; directionality of subclass relations is ignored.
    - Only named OWL classes are considered.
    - Classes that participate in subclass/equivalent/disjoint axioms involving blank nodes are excluded.
    """

    g = Graph()
    g.parse(ttl_file_path, format="turtle")

    class_predicates = [RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith, SKOS.broader]

    # Filter out named classes that are involved in axioms with blank nodes
    named_classes = set()
    for c in g.subjects(RDF.type, OWL.Class):
        if not any(
            (p in class_predicates) and isinstance(o, BNode)
            for (_, p, o) in g.triples((c, None, None))
        ):
            if isinstance(c, URIRef):
                named_classes.add(c)

    class_graph = nx.Graph()

    # Add all valid named classes as nodes
    class_graph.add_nodes_from(named_classes)

    # Add edges between named classes, only if both ends are valid named classes
    for pred in class_predicates:
        for s, o in g.subject_objects(pred):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                if s in named_classes and o in named_classes:
                    class_graph.add_edge(s, o)
    
    print(f"Number of connected components: {nx.number_connected_components(class_graph)}")
    return nx.number_connected_components(class_graph)
