from collections import defaultdict
from rdflib import Graph, RDF, RDFS, OWL

def find_duplicate_labels_from_graph(ttl_file):
    """
    IO8 - Semantically Identical Classes

    This metric identifies semantically identical  classes by checking if two IRIs in an ontology 
    has the same value for rdfs:label or not.

    Params
    ------
        ttl_file (string): path to ttl file

    Returns
    -------
        duplicates (dict): dictionary of URIs of duplicated terms

    Author: Van Tran
    Version: 0.0.1

    References
    ----------
    Mc Gurk, S., Abela, C., & Debattista, J. (2017). Towards ontology quality assessment. 
    4th Workshop on Linked Data Quality (LDQ2017), co-located with the 14th Extended Semantic Web Conference (ESWC), 
    Portorož, 94-106.
    """
    ontology_graph = Graph()
    ontology_graph.parse(ttl_file)

    label_to_entities = defaultdict(list)

    # Define entity types of interest
    target_types = [OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty]

    for s in ontology_graph.subjects(RDFS.label, None):
        # Check if s has one of the target rdf:type values
        types = list(ontology_graph.objects(s, RDF.type))
        if any(t in target_types for t in types):
            label = str(next(ontology_graph.objects(s, RDFS.label))).strip().lower()
            label_to_entities[label].append(s)

    # Find duplicates
    duplicates = {label: uris for label, uris in label_to_entities.items() if len(uris) > 1}

    if duplicates:
        print("Duplicate rdfs:label values found (case-insensitive):")
        for label, entities in duplicates.items():
            print(f"  Label: '{label}' used by:")
            for entity in entities:
                print(f"    - {entity}")
    else:
        print("No duplicate rdfs:label values found.")

    return len(duplicates)
