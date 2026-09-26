"""
mainSemanticConnection_v_0_0_1 metric implementation.

Changelog (v0.0.2)
------------------
- FIXED: the hierarchical tree view was indented inside ``if
  disconnected_chains:``, so it was never printed for an ontology in which
  every root chain is grounded in CCO/BFO -- that is, for the passing case.
  The block is now dedented to function scope and always runs.
- FIXED: ``show`` parameter added so the tree view can be suppressed on large
  ontologies without losing the statistics.
- FIXED: the function now returns a result dictionary instead of ``None``, so
  ``run_assessment`` writes a value into the ``Score`` column rather than a
  blank.
"""

from .helpers.helpers import _analyze_hierarchy_connections, _build_class_hierarchy, _find_all_named_classes, _find_root_classes, _is_connected_to_higher_ontology, _print_hierarchy_with_connection
from collections import defaultdict
from rdflib import Graph, RDFS, RDF, OWL, URIRef
import logging

logger = logging.getLogger(__name__)

def mainSemanticConnection_v_0_0_1(ttl_file, show="all"):
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

    - Connection ratio: The proportion of root classes that are semantically grounded in a higher-level ontology. This is the value returned as the metric score.

    Author: Rishabh Kundu
    Version: 0.0.2

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle (.ttl) file to analyze

    show : str, optional
        Display option controlling what information to show:
        - "all" (default): Shows statistics, the connection summary, and the full hierarchical tree view
        - "summary": Shows statistics and the connection summary only, suppressing the tree view
        - "tree": Shows statistics and the tree view, suppressing the per-chain summary

        On large ontologies the tree view dominates the log file; use
        ``show="summary"`` to keep the log readable.

    Returns
    -------
    dict or None
        A dictionary with the following keys, or ``None`` when the ontology
        could not be loaded or contains no hierarchy:

        - ``connection_ratio`` (float): connected root classes divided by total
          root classes. This is the headline score.
        - ``total_classes`` (int)
        - ``root_classes`` (int)
        - ``connected_roots`` (int)
        - ``disconnected_roots`` (int)
        - ``classes_with_children`` (int)
        - ``total_relationships`` (int)
        - ``connected_chains`` (list of str)
        - ``disconnected_chains`` (list of str)

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

    In every one of these cases the function logs the condition and returns
    ``None`` rather than raising.

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
        mainSemanticConnection_v_0_0_1("ontology.ttl")

    Suppress the tree view on a large ontology:
        mainSemanticConnection_v_0_0_1("ontology.ttl", show="summary")

    Read the score:
        result = mainSemanticConnection_v_0_0_1("ontology.ttl")
        print(f"Grounded chains: {result['connection_ratio']:.1%}")
    """

    valid_show_options = ["all", "summary", "tree"]
    if show not in valid_show_options:
        logger.error(f"Invalid 'show' parameter. Must be one of {valid_show_options}")
        return None

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
        return None
    except Exception as e:
        logger.error(f"An error occurred while parsing the TTL file: {e}")
        return None

    # Find all classes
    all_classes = _find_all_named_classes(g)
    if not all_classes:
        logger.info("No named classes found in the ontology.")
        return None

    # Build hierarchy
    hierarchy, children_of = _build_class_hierarchy(g, all_classes)

    if not hierarchy:
        logger.info("No class hierarchy relationships found in the ontology.")
        return None

    # Analyze connections to higher level ontologies
    connection_status, root_classes = _analyze_hierarchy_connections(g, hierarchy, all_classes, children_of)

    # Count statistics
    classes_with_children = len([p for p in hierarchy.keys() if hierarchy[p]])
    total_relationships = sum(len(children) for children in hierarchy.values())
    connected_roots = sum(1 for status in connection_status.values() if status)

    # Guard against division by zero on an ontology with no root classes
    connection_ratio = (connected_roots / len(root_classes)) if root_classes else 0.0

    logger.info(f"Hierarchy Statistics:")
    logger.info(f"Total classes: {len(all_classes)}")
    logger.info(f"Classes with children: {classes_with_children}")
    logger.info(f"Total parent-child relationships: {total_relationships}")
    logger.info(f"Root classes: {len(root_classes)}")
    logger.info(f"Root classes connected to higher ontologies (CCO/BFO): {connected_roots}/{len(root_classes)}")
    logger.info(f"Connection ratio: {connection_ratio:.2%}")

    # Partition chains by connection status
    connected_chains = []
    disconnected_chains = []

    for root in sorted(root_classes, key=lambda x: x.n3(g.namespace_manager)):
        root_name = root.n3(g.namespace_manager)
        if connection_status.get(root, False):
            connected_chains.append(root_name)
        else:
            disconnected_chains.append(root_name)

    # Show connection summary (overview stats)
    if show in ["summary", "all"]:
        logger.info(f"--- Connection Summary ---")

        if connected_chains:
            logger.info(f"Hierarchy chains CONNECTED to higher ontologies ({len(connected_chains)}):")
            for chain in connected_chains:
                logger.info(f"  {chain}")

        if disconnected_chains:
            logger.info(f"Hierarchy chains NOT CONNECTED to higher ontologies ({len(disconnected_chains)}):")
            for chain in disconnected_chains:
                logger.info(f"  {chain}")

    # Display results in another format
    #
    # NOTE (v0.0.2): this block was previously indented inside the
    # "if disconnected_chains:" branch above, which meant the tree view was
    # only ever printed for an ontology that had at least one DISCONNECTED
    # chain. A fully grounded ontology -- the passing case -- printed no tree
    # at all. It is now at function scope and runs whenever requested.
    if show in ["tree", "all"]:
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

    return {
        "connection_ratio": connection_ratio,
        "total_classes": len(all_classes),
        "root_classes": len(root_classes),
        "connected_roots": connected_roots,
        "disconnected_roots": len(root_classes) - connected_roots,
        "classes_with_children": classes_with_children,
        "total_relationships": total_relationships,
        "connected_chains": connected_chains,
        "disconnected_chains": disconnected_chains,
    }
