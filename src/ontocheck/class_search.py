from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, OWL

def mainClassSearch_v_0_0_1(ontology_graph_or_path, search_term: str) -> list:
    """
    Class Name Substring Search
    
    Evaluates an ontology file to find all class names that contain a specified
    substring, irrespective of capitalization.
    
    This metric assesses whether certain concepts can be resolved from a semantic 
    or string basis, which is important for identifying overlapping concepts, 
    naming consistency, or potential duplicates (e.g., 'VoltageRating' and 'VoltAgeRange').
    
    Author: Redad Mehdi
    Version: 0.0.1
    
    Parameters:
    -----------
    ontology_graph_or_path : str or rdflib.Graph
        Path to the Turtle (.ttl) file to analyze, or a pre-loaded rdflib.Graph object.
    search_term : str
        The string to search for within the class names (case-insensitive).
        
    Returns:
    --------
    list of dict
        A list containing dictionaries of the matched classes.
        Each dictionary contains:
        - 'class_name': The extracted local name of the class (str).
        - 'uri': The full URI string of the class (str).
        Returns an empty list if no matches are found.
        
    Notes:
    ------
    The function identifies class names by looking at subjects typed as owl:Class 
    or rdfs:Class. It extracts the local name by splitting the URI at the last 
    '#' or '/' character before performing the case-insensitive comparison.
    
    Example:
    --------
    >>> matches = mainClassSearch_v_0_0_1('dataset.ttl', 'VOLtage')
    >>> print(f"Found {len(matches)} matching classes.")
    """
    # Load the graph if a file path is provided, otherwise use the passed graph
    if isinstance(ontology_graph_or_path, str):
        g = Graph()
        g.parse(ontology_graph_or_path, format="turtle")
    else:
        g = ontology_graph_or_path

    search_term_lower = search_term.lower()
    matches = []

    # Get all unique classes (both OWL and RDFS classes just to be safe)
    classes = set(g.subjects(RDF.type, OWL.Class)).union(g.subjects(RDF.type, RDFS.Class))

    for class_uri in classes:
        # We only want to check actual URIs, not BNodes (blank nodes)
        if isinstance(class_uri, URIRef):
            uri_str = str(class_uri)
            
            # Extract the local class name (heuristic: get everything after the last '#' or '/')
            if '#' in uri_str:
                local_name = uri_str.split('#')[-1]
            else:
                local_name = uri_str.split('/')[-1]

            # Case-insensitive check
            if search_term_lower in local_name.lower():
                matches.append({
                    "class_name": local_name,
                    "uri": uri_str
                })
    print("\n" + "="*40)
    print(f"SEARCH RESULTS FOR: '{search_term}'")
    print("="*40)
    
    if matches:
        print(f"Found {len(matches)} matching class(es):\n")
        for match in matches:
            print(f"  * Class: {match['class_name']}")
            print(f"    URI:   {match['uri']}\n")
    else:
        print(f"No classes found containing '{search_term}'.\n")
        
    print("="*40 + "\n")

    return matches