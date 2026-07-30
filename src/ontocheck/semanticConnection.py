"""
mainSemanticConnection_v_0_0_1 metric implementation.
"""

from .helpers.helpers import _analyze_hierarchy_connections, _build_class_hierarchy, _find_all_named_classes, _find_root_classes, _is_connected_to_higher_ontology, _print_hierarchy_with_connection
from collections import defaultdict
from rdflib import Graph, RDFS, RDF, OWL, URIRef
import logging

logger = logging.getLogger(__name__)

def mainSemanticConnection_v_0_0_1(ttl_file):
    """
    Ontology Semantic Connection Analysis

    Analyze an OWL ontology in Turtle (ttl) format and assess the semantic connection of class hierarchies to established upper-level ontologies (specifically, Common Core Ontology and Basic Formal Ontology)

    This main function loads an ontology file, builds the complete class hierarchy, identifies root classes, and determines which hierarchy chains are semantically grounded in higher-level ontologies through naming convention analysis

    Definitions
    -----------
    - Named classes: Classes with URIRef identifiers that are explicitly declared as owl:Class or rdfs:Class, or participate in rdfs:subClassOf relations
    
    - Class hierarchy: The tree structure of classes connected via rdfs:subClassOf relationships

    - Root classes: Classes that have no parent classes, representing the top level of independent hierarchy trees

    - Semantic connection: Connection to higher-level ontologies (CCO/BFO) determined by URI prefix analysis (cco:, obo:bfo, bfo:)

    - Hierarchy chains: Complete trees of classes rooted at root classes, inheriting the connection status of their root

    Author: Rishabh Kundu
    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle (.ttl) file to analyze

    Returns
    -------
    None
        This function does not (directly) return values. It prints comprehensive hierarchy analysis to terminal/CLI. The function may exit early on errors (file not found, parsing errors, no classes found, or no hierarchy relationships found)

    Output Information
    -----------------
    When executed successfully, the analysis provides:
    - Total number of named classes
    - Number of classes with children (parent classes)
    - Total parent-child relationships
    - Number of root classes
    - Number of root classes connected to higher ontologies
    - Summary of connected vs disconnected hierarchy chains
    - Complete hierarchical tree view with connection status indicators

    Error Handling
    -------------
    The function handles several error conditions:
    - FileNotFoundError: When the specified TTL file cannot be found
    - Parsing errors: When the TTL file cannot be parsed as valid Turtle
    - Empty ontology: When no named classes are found
    - Missing hierarchy: When no rdfs:subClassOf relationships are found

    Notes
    -----
    - Only considers explicitly declared classes and rdfs:subClassOf relationships
    - Connection analysis based on URI prefix patterns (cco:, obo:bfo, bfo:)
    - Provides both statistical summary and detailed tree visualization
    - Includes namespace bindings for common ontology prefixes

    .. note::

       Claude AI (Sonnet 4) was employed chiefly to support documentation efforts.

    Examples
    --------
    Basic usage:
        python script.py ontology.ttl
    """

    g = Graph()
    try:
        logger.info(f"Parsing file: {ttl_file}...")
        # Bind common prefixes for cleaner output (future users can add more here)
        g.bind("mds", "https://cwrusdle.bitbucket.io/mds/")
        g.bind("cco", "https://www.commoncoreontologies.org/")
        g.bind("obo", "http://purl.obolibrary.org/obo/")
        g.bind("owl", "http://www.w3.org/2002/07/owl#")
        g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
        g.parse(ttl_file, format="turtle")
    except FileNotFoundError:
        logger.error(f"The file '{ttl_file}' was not found.")
        return
    except Exception as e:
        logger.error(f"An error occurred while parsing the TTL file: {e}")
        return

    # Find all classes
    all_classes = _find_all_named_classes(g)
    if not all_classes:
        logger.info("No named classes found in the ontology.")
        return

    # Build hierarchy
    hierarchy, children_of = _build_class_hierarchy(g, all_classes)
    
    if not hierarchy:
        logger.info("No class hierarchy relationships found in the ontology.")
        return

    # Analyze connections to higher level ontologies
    connection_status, root_classes = _analyze_hierarchy_connections(g, hierarchy, all_classes, children_of)

    # Count statistics
    classes_with_children = len([p for p in hierarchy.keys() if hierarchy[p]])
    total_relationships = sum(len(children) for children in hierarchy.values())
    connected_roots = sum(1 for status in connection_status.values() if status)
    
    logger.info(f"Hierarchy Statistics:")
    logger.info(f"Total classes: {len(all_classes)}")
    logger.info(f"Classes with children: {classes_with_children}")
    logger.info(f"Total parent-child relationships: {total_relationships}")
    logger.info(f"Root classes: {len(root_classes)}")
    logger.info(f"Root classes connected to higher ontologies (CCO/BFO): {connected_roots}/{len(root_classes)}")

    # Show connection summary (overview stats)
    logger.info(f"--- Connection Summary ---")
    connected_chains = []
    disconnected_chains = []

    for root in sorted(root_classes, key=lambda x: x.n3(g.namespace_manager)):
        root_name = root.n3(g.namespace_manager)
        if connection_status.get(root, False):
            connected_chains.append(root_name)
        else:
            disconnected_chains.append(root_name)

    if connected_chains:
        logger.info(f"Hierarchy chains CONNECTED to higher ontologies ({len(connected_chains)}):")
        for chain in connected_chains:
            logger.info(f"  {chain}")

    if disconnected_chains:
        logger.info(f"Hierarchy chains NOT CONNECTED to higher ontologies ({len(disconnected_chains)}):")
        for chain in disconnected_chains:
            logger.info(f"  {chain}")

    # Display results in another format
    #Other output forms can be displayed together with this only one by adding something like "both"
    
        logger.info("--- Hierarchical Tree View with Connection Status ---")

        if root_classes:
            logger.info(f"Displaying {len(root_classes)} root class hierarchies:")
            sorted_roots = sorted(root_classes, key=lambda x: x.n3(g.namespace_manager))
            for root in sorted_roots:
                _print_hierarchy_with_connection(g, root, hierarchy, connection_status)
                logger.info("")  # Add spacing between root hierarchies
        else:
            logger.info("No clear root classes found. Displaying all parent-child relationships:")
            for parent in sorted(hierarchy.keys(), key=lambda x: x.n3(g.namespace_manager)):
                if hierarchy[parent]:  # Only show parents that have children
                    _print_hierarchy_with_connection(g, parent, hierarchy, connection_status)
                    logger.info("")
