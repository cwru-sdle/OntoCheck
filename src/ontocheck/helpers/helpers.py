"""
Helper functions extracted from the codebase.
"""

from collections import defaultdict
from rdflib import Graph, RDFS, RDF, OWL, SKOS
from rdflib import Graph, RDFS, RDF, OWL, URIRef
from rdflib import Graph, RDFS, RDF, OWL, URIRef, Namespace, BNode
import argparse

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/AltLabelCheck.py
def _analyze_altlabel_coverage(graph, all_classes):
    """
    Analyze which classes have SKOS altLabel properties

    This function categorizes classes based on their SKOS altLabel coverage, filtering out empty or whitespace-only alternative labels to ensure only meaningful labels are counted

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    all_classes : set
        A set of URIRef objects representing all named classes to analyze

    Returns
    -------
    tuple
        A tuple containing:
        - classes_with_altlabel (defaultdict): Maps class URIs to lists of non-empty altLabels
        - classes_without_altlabel (set): Set of class URIs lacking meaningful altLabels

    Notes
    -----
    - Empty strings and whitespace-only altLabels are filtered out
    - Classes with only empty altLabels are categorized as "without altLabel"
    - Handles both literal values and string representations of labels
    """
    classes_with_altlabel = defaultdict(list)
    classes_without_altlabel = set()
    
    # Check each class for altLabel properties
    for class_uri in all_classes:
        altlabels = list(graph.objects(class_uri, SKOS.altLabel))
        
        if altlabels:
            # Convert literals to string values for display and filter out empty strings
            altlabel_values = []
            for label in altlabels:
                if hasattr(label, 'value'):
                    label_str = str(label.value)
                else:
                    label_str = str(label)
                # Only add non-empty strings
                if label_str.strip():
                    altlabel_values.append(label_str)
            # Only consider as having altLabels if there are non-empty values
            if altlabel_values:
                classes_with_altlabel[class_uri] = altlabel_values
            else:
                classes_without_altlabel.add(class_uri)
        else:
            classes_without_altlabel.add(class_uri)
    
    return classes_with_altlabel, classes_without_altlabel

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
def _analyze_definition_coverage(graph, all_classes):
    """
    Analyze which classes have SKOS definition properties

    This function categorizes classes based on their SKOS definition coverage, identifying classes with definitions and those lacking them

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    all_classes : set
        A set of URIRef objects representing all named classes to analyze

    Returns
    -------
    tuple
        A tuple containing:
        - classes_with_definition (dict): Maps class URIs to their definition text
        - classes_without_definition (set): Set of class URIs lacking definition properties

    Notes
    -----
    - Uses skos:definition property to identify definitions
    - Handles both literal values and string representations of definitions
    - Each class can have at most one definition 
    """
    classes_with_definition = {}
    classes_without_definition = set()
    
    # Check each class for definition properties
    for class_uri in all_classes:
        definition = graph.value(subject=class_uri, predicate=SKOS.definition)
        
        if definition:
            # Convert literal to string value for display
            if hasattr(definition, 'value'):
                definition_text = str(definition.value)
            else:
                definition_text = str(definition)
            classes_with_definition[class_uri] = definition_text
        else:
            classes_without_definition.add(class_uri)
    
    return classes_with_definition, classes_without_definition

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/SemanticConnection.py
def _find_root_classes(all_classes, children_of):
    """
    Find classes that have no parent classes (root classes = level 0)

    Identifies top-level classes in the hierarchy that do not have any superclasses, making them root nodes of hierarchy trees

    Parameters
    ----------
    all_classes : set
        Set of all named classes in the ontology
    children_of : defaultdict
        Mapping of child classes to their parent classes

    Returns
    -------
    set
        A set of URIRef objects representing root classes (classes with no parents)

    Notes
    -----
    - Root classes are those not present in children_of or having empty parent sets
    - These classes represent the top level (= level 0) of independent hierarchy trees
    - Used to identify starting/top points for hierarchical tree traversal
    """
    root_classes = set()
    for class_uri in all_classes:
        if class_uri not in children_of or len(children_of[class_uri]) == 0:
            root_classes.add(class_uri)
    return root_classes

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/SemanticConnection.py
def _is_connected_to_higher_ontology(class_uri, graph):
    """
    Check if a class is connected to CCO or BFO higher-level ontologies | maybe expanded in future versions

    Determines semantic connection by examining class URI prefixes to identify classes that belong to established upper-level ontologies

    Parameters
    ----------
    class_uri : rdflib.term.URIRef
        The URI of the class to check for higher ontology connection
    graph : rdflib.Graph
        The RDF graph containing the ontology (used for namespace management)

    Returns
    -------
    bool
        True if the class is connected to higher-level ontologies, False elsewise

    Notes
    -----
    - Looks for prefixes: 'cco:', 'obo:bfo', or 'bfo:' (case-insensitive) -- scope may be expanded in future versions
    - CCO = Common Core Ontology, BFO = Basic Formal Ontology
    - Uses prefixed name representation for pattern matching
    - Returns False for non-URIRef inputs as safety measure
    - Connection determination is based SOLELY on naming conventions
    """
    if not isinstance(class_uri, URIRef):
        return False
    
    prefixed_name = class_uri.n3(graph.namespace_manager)
    pn_lower = prefixed_name.lower()
    
    # Check for Common Core Ontology and Basic Formal Ontology prefixes -- may expand scope in future versions
    if (pn_lower.startswith('cco:') or 
        pn_lower.startswith('obo:bfo') or 
        pn_lower.startswith('bfo:')):
        return True
    return False

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/SemanticConnection.py
def _analyze_hierarchy_connections(graph, hierarchy, all_classes, children_of):
    """
    Analyze which hierarchy chains are connected to higher-level ontologies

    Evaluates the connection status of root classes to determine which hierarchy trees have semantic grounding in established upper ontologies

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    hierarchy : defaultdict
        Mapping of parent classes to their direct children
    all_classes : set
        Set of all named classes in the ontology
    children_of : defaultdict
        Mapping of child classes to their parent classes

    Returns
    -------
    tuple
        A tuple containing:
        - connection_status (dict): Maps root class URIs to their connection status (bool)
        - root_classes (set): Set of all root classes found in the hierarchy

    Notes
    -----
    - Only analyzes root classes for connection status
    - Connection status applies to entire hierarchy chains rooted at each root class
    - Used to generate summary statistics about ontology grounding
    """
    root_classes = _find_root_classes(all_classes, children_of)
    connection_status = {}
    
    for root in root_classes:
        is_connected = _is_connected_to_higher_ontology(root, graph)
        connection_status[root] = is_connected
    
    return connection_status, root_classes

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/SemanticConnection.py
def _build_class_hierarchy(graph, all_classes):
    """
    Build a hierarchy mapping from parent classes to their direct children

    Creates bidirectional mappings of class relationships to enable navigation both down the hierarchy (parent to children) and up (child to parents)

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    all_classes : set
        A set of URIRef objects representing all named classes to consider

    Returns
    -------
    tuple
        A tuple containing:
        - hierarchy (defaultdict): Maps parent class URIs to sets of their direct children
        - children_of (defaultdict): Maps child class URIs to sets of their direct parents

    Notes
    -----
    - Considers rdfs:subClassOf relationships for hierarchy building
    - Filters relationships to include only classes present in all_classes set
    - Creates bidirectional mapping for efficient hierarchy traversal
    """
    hierarchy = defaultdict(set)
    children_of = defaultdict(set)
    
    # Get all subClassOf relationships
    for subclass, pred, superclass in graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(subclass, URIRef) and isinstance(superclass, URIRef):
            if subclass in all_classes and superclass in all_classes:
                hierarchy[superclass].add(subclass)
                children_of[subclass].add(superclass)
    
    return hierarchy, children_of

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
def _get_preferred_label(graph, class_uri):
    """
    Get the preferred label for a class (skos:prefLabel or rdfs:label)

    Attempts to retrieve the most appropriate human-readable label for a class, following a priority hierarchy: SKOS prefLabel > RDFS label > prefixed URI

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    class_uri : rdflib.term.URIRef
        The URI of the class for which to retrieve the preferred label

    Returns
    -------
    str
        The preferred label as a string, or the prefixed URI if no label is found

    Notes
    -----
    - Prioritizes skos:prefLabel over rdfs:label for SKOS-compliant ontologies
    - Falls back to the prefixed name representation if no labels are available
    - Uses the graph's namespace manager for clean URI representation
    - This is a utility function for ease of identifying classes with their intended labels (not altLabels)
    """
    # Try SKOS prefLabel first
    pref_label = graph.value(subject=class_uri, predicate=SKOS.prefLabel)
    if pref_label:
        return str(pref_label)
    
    # Try RDFS label
    rdfs_label = graph.value(subject=class_uri, predicate=RDFS.label)
    if rdfs_label:
        return str(rdfs_label)
    
    # Fallback to URI fragment or prefixed name
    return class_uri.n3(graph.namespace_manager)

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/AltLabelCheck.py
def _export_missing_altlabels_template(graph, classes_without_altlabel, output_file):
    """
    Export a template file for classes missing altLabels

    Creates a Turtle format template file that can be used to systematically add alternative labels to classes that currently lack them

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    classes_without_altlabel : set
        Set of class URIs that lack meaningful altLabel properties
    output_file : str
        Path where the template file should be written

    Notes
    -----
    - Generates valid Turtle syntax with proper prefixes
    - Includes comments with current class labels for context
    - Uses placeholder text that needs to be replaced with actual labels
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# Classes Missing SKOS altLabel - Template for Adding Alternative Labels\n")
            f.write("# Add appropriate alternative labels for each class\n\n")
            f.write("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n")
            f.write("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n\n")
            
            sorted_classes = sorted(classes_without_altlabel, 
                                  key=lambda x: x.n3(graph.namespace_manager))
            
            for class_uri in sorted_classes:
                prefixed_name = class_uri.n3(graph.namespace_manager)
                preferred_label = _get_preferred_label(graph, class_uri)
                
                f.write(f"# Class: {prefixed_name}\n")
                if preferred_label != prefixed_name:
                    f.write(f"# Current label: {preferred_label}\n")
                f.write(f"{prefixed_name} skos:altLabel \"ADD_ALTERNATIVE_LABEL_HERE\" .\n\n")
        
        print(f"\nTemplate file exported to: {output_file}")
    except Exception as e:
        print(f"Error exporting template: {e}")

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/SemanticConnection.py
def _find_all_named_classes(graph):
    """
    Find all explicitly declared named classes in the ontology

    This function identifies named classes by examining:
    1. Classes explicitly declared with rdf:type owl:Class or rdfs:Class
    2. Classes that appear as subjects in rdfs:subClassOf relations
    3. Classes that appear as objects in rdfs:subClassOf relations (parent classes)

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology

    Returns
    -------
    set
        A set of URIRef objects representing all named classes found in the ontology

    Notes
    -----
    - Only returns URIRef instances (named classes), filtering out blank nodes
    - Combines multiple methods of class discovery to ensure comprehensive coverage
    - Adding subclass objects helps find parent classes not explicitly declared as owl:Class
    """
    all_subjects = set(s for s, p, o in graph)
    potential_classes = set(s for s, p, o in graph if p == RDF.type and (o == RDFS.Class or o == OWL.Class))
    subclass_subjects = set(s for s, p, o in graph.triples((None, RDFS.subClassOf, None)))
    subclass_objects = set(o for s, p, o in graph.triples((None, RDFS.subClassOf, None))) #added to find out parent classes not explicitly mentioned
    
    # Combine them and filter for only named URIs
    all_found = potential_classes.union(subclass_subjects).union(subclass_objects)
    named_classes = {c for c in all_found if isinstance(c, URIRef)}
    
    print(f"Found {len(named_classes)} unique named classes.")
    return named_classes

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/LeafNodeCheck.py
def _find_leaf_nodes(graph):
    """
    Find all leaf nodes in the ontology hierarchy

    Identifies leaf nodes by finding classes that have no subclasses, meaning they appear as classes but never as superclasses in rdfs:subClassOf or skos:broader relations

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology

    Returns
    -------
    set
        A set of URIRef objects representing all leaf nodes found in the ontology

    Notes
    -----
    - Leaf nodes are classes that are not superclasses of any other classes
    - Uses set difference operation: all_classes - super_classes = leaf_nodes
    - Considers both rdfs:subClassOf and skos:broader relationships for hierarchy detection
    - Only considers explicitly declared classes (rdf:type owl:Class or rdfs:Class)

    """
 
    # Find everything that are declared as rdfs:Class
    all_classes = set(s for s, p, o in graph if p == RDF.type and (o == RDFS.Class or o == OWL.Class))
    
    # Find all objects of rdfs:subClassOf triples, which are the superclasses
    super_classes = set(graph.objects(None, (RDFS.subClassOf or SKOS.broader)))
    
    # Leaf nodes (are essentially) = all classes - super classes 
    leaf_nodes = all_classes - super_classes
    print("\n Total number of leaf nodes:- ", len(leaf_nodes))
    return leaf_nodes

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
def _get_additional_labels(graph, class_uri):
    """
    Get additional labeling information (altLabels) for context

    Retrieves all SKOS alternative labels associated with a class to provide additional context when displaying class information

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    class_uri : rdflib.term.URIRef
        The URI of the class for which to retrieve alternative labels

    Returns
    -------
    list
        A list of alternative label strings, or empty list if none exist

    Notes
    -----
    - Uses skos:altLabel property to retrieve alternative labels
    - Handles both literal values and string representations of labels
    - Returns all alternative labels found (unlike preferred labels which return first match)
    """
    altlabels = list(graph.objects(class_uri, SKOS.altLabel))
    if altlabels:
        altlabel_values = []
        for label in altlabels:
            if hasattr(label, 'value'):
                altlabel_values.append(str(label.value))
            else:
                altlabel_values.append(str(label))
        return altlabel_values
    return []

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/AltLabelCheck.py
def _print_classes_with_altlabels(graph, classes_with_altlabel):
    """
    Print all classes that have SKOS altLabel properties

    Displays a formatted list of classes with their preferred labels and all associated alternative labels for comprehensive review

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    classes_with_altlabel : defaultdict
        Dictionary mapping class URIs to lists of their alternative labels

    Notes
    -----
    - Classes are sorted alphabetically by their prefixed names for consistency
    - Shows preferred labels when they differ from the prefixed name
    - Displays each alternative label
    """
    print(f"\n--- Classes WITH altLabel ({len(classes_with_altlabel)}) ---")
    
    if not classes_with_altlabel:
        print("No classes found with altLabel properties.")
        return
    
    # Sort classes for consistent output
    sorted_classes = sorted(classes_with_altlabel.keys(), 
                          key=lambda x: x.n3(graph.namespace_manager))
    
    for class_uri in sorted_classes:
        prefixed_name = class_uri.n3(graph.namespace_manager)
        preferred_label = _get_preferred_label(graph, class_uri)
        altlabels = classes_with_altlabel[class_uri]
        
        print(f"\nClass: {prefixed_name}")
        if preferred_label != prefixed_name:
            print(f"  Preferred Label: {preferred_label}")
        print(f"  Alternative Labels ({len(altlabels)}):")
        for altlabel in altlabels:
            print(f"    - \"{altlabel}\"")

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
def _truncate_definition(definition, max_length=150):
    """
    Truncate long definitions for summary display

    Shortens definition text to a specified maximum length for cleaner display in summary views, adding ellipsis to indicate truncation

    Parameters
    ----------
    definition : str
        The full definition text to potentially truncate
    max_length : int, optional
        Maximum number of characters to display (default/set by RK: 150)

    Returns
    -------
    str
        The definition text, truncated if necessary with "..." appended
    """
    if len(definition) <= max_length:
        return definition
    return definition[:max_length].strip() + "..."

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
def _print_classes_with_definitions(graph, classes_with_definition, show_full_definitions=False):
    """
    Print all classes that have SKOS definition properties

    Displays a formatted list of classes with their preferred labels and definitions, with options for full or truncated definition display

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    classes_with_definition : dict
        Dictionary mapping class URIs to their definition text
    show_full_definitions : bool, optional
        If True, show full definitions; if False, show truncated versions (default: False)

    Notes
    -----
    - Classes are sorted alphabetically by their prefixed names for consistency
    - Shows preferred labels when they differ from the prefixed name
    - Displays definition length information when definitions are truncated
    """
    print(f"\n--- Classes WITH Definitions ({len(classes_with_definition)}) ---")
    
    if not classes_with_definition:
        print("No classes found with definition properties.")
        return
    
    # Sort classes for consistent output
    sorted_classes = sorted(classes_with_definition.keys(), 
                          key=lambda x: x.n3(graph.namespace_manager))
    
    for class_uri in sorted_classes:
        prefixed_name = class_uri.n3(graph.namespace_manager)
        preferred_label = _get_preferred_label(graph, class_uri)
        definition = classes_with_definition[class_uri]
        altlabels = _get_additional_labels(graph, class_uri)
        
        print(f"\nClass: {prefixed_name}")
        if preferred_label != prefixed_name:
            print(f"  Preferred Label: \"{preferred_label}\"")
        
        if show_full_definitions:
            print(f"  Definition: \"{definition}\"")
        else:
            truncated_def = _truncate_definition(definition)
            print(f"  Definition: \"{truncated_def}\"")
            if len(definition) > len(truncated_def):
                print(f"    [Full definition: {len(definition)} characters]")

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/AltLabelCheck.py
def _print_classes_without_altlabels(graph, classes_without_altlabel):
    """
    Print all classes that do NOT have SKOS altLabel properties

    Displays classes lacking alternative labels to help identify ontology completeness gaps

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    classes_without_altlabel : set
        Set of class URIs that lack meaningful altLabel properties

    Notes
    -----
    - Classes are sorted alphabetically by their prefixed names for consistency
    - Shows preferred labels when they differ from the prefixed name
    - Useful for identifying classes that may benefit from alternative labels
    """
    print(f"\n--- Classes WITHOUT altLabel ({len(classes_without_altlabel)}) ---")
    
    if not classes_without_altlabel:
        print("All classes have altLabel properties!")
        return
    
    # Sort classes for consistent output
    sorted_classes = sorted(classes_without_altlabel, 
                          key=lambda x: x.n3(graph.namespace_manager))
    
    for class_uri in sorted_classes:
        prefixed_name = class_uri.n3(graph.namespace_manager)
        preferred_label = _get_preferred_label(graph, class_uri)
        
        if preferred_label != prefixed_name:
            print(f"{prefixed_name} (Label: \"{preferred_label}\")")
        else:
            print(f"{prefixed_name}")

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
def _print_classes_without_definitions(graph, classes_without_definition):
    """
    Print all classes that do NOT have SKOS definition properties

    Displays classes lacking definitions to help identify ontology completeness gaps

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    classes_without_definition : set
        Set of class URIs that lack definition properties

    Notes
    -----
    - Classes are sorted alphabetically by their prefixed names for consistency
    - Shows preferred labels when they differ from the prefixed name for better identification
    - Useful for identifying classes that may benefit from definitions
    """
    print(f"\n--- Classes WITHOUT Definitions ({len(classes_without_definition)}) ---")
    
    if not classes_without_definition:
        print("All classes have definition properties!")
        return
    
    # Sort classes for consistent output
    sorted_classes = sorted(classes_without_definition, 
                          key=lambda x: x.n3(graph.namespace_manager))
    
    for class_uri in sorted_classes:
        prefixed_name = class_uri.n3(graph.namespace_manager)
        preferred_label = _get_preferred_label(graph, class_uri)
        altlabels = _get_additional_labels(graph, class_uri)
        
        output = f"{prefixed_name}"
        if preferred_label != prefixed_name:
            output += f" (Label: \"{preferred_label}\")"
        
        print(output)

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/SemanticConnection.py
def _print_hierarchy_with_connection(graph, class_uri, hierarchy, connection_status, level=0, visited=None):
    """
    Recursively print the class hierarchy with connection status indicators

    Displays hierarchical tree structure with indentation and connection status annotations for root classes to show semantic grounding

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    class_uri : rdflib.term.URIRef
        The current class URI being printed
    hierarchy : defaultdict
        Mapping of parent classes to their direct children
    connection_status : dict
        Mapping of root classes to their connection status
    level : int, optional
        Current indentation level for tree display (default: 0)
    visited : set, optional
        Set of already visited classes to prevent infinite recursion (default: None)

    Notes
    -----
    - Uses recursive traversal with cycle detection via visited set
    - Indents child classes to show hierarchical structure
    - Shows connection status only for root classes (= level 0)
    - Sorts children (at a particular level) alphabetically for consistent output
    """
    if visited is None:
        visited = set()
    
    if class_uri in visited:
        return
    visited.add(class_uri)
    
    indent = "  " * level
    prefixed_name = class_uri.n3(graph.namespace_manager)
    
    # Add connection indicator for root classes
    if level == 0:
        status = "CONNECTED" if connection_status.get(class_uri, False) else "NOT CONNECTED"
        print(f"{indent}{prefixed_name} [{status}]")
    else:
        print(f"{indent}{prefixed_name}")
    
    # Print all direct children
    children = sorted(hierarchy[class_uri], key=lambda x: x.n3(graph.namespace_manager))
    for child in children:
        _print_hierarchy_with_connection(graph, child, hierarchy, connection_status, level + 1, visited)

# From: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
def _print_summary_statistics(graph, classes_with_definition, classes_without_definition, all_classes):
    """
    Print summary statistics about definition coverage

    Calculates and displays comprehensive metrics about definition coverage including percentages, totals, and qualitative quality assessments

    Parameters
    ----------
    graph : rdflib.Graph
        The RDF graph containing the ontology
    classes_with_definition : dict
        Dictionary mapping class URIs to their definition text
    classes_without_definition : set
        Set of class URIs that lack definition properties
    all_classes : set
        Set of all named classes in the ontology

    Notes
    -----
    - Calculates coverage percentage based on classes with definitions
    - Provides qualitative assessment based on coverage thresholds
    - Uses ontology quality benchmarks for assessment categories: ≥90%: Excellent, ≥75%: Good, ≥50%: Moderate, ≥25%: Low, <25%: Very low
    - Calculates definition length statistics but doesn't currently display them (maybe looked into a future version)
    - Higher thresholds than altLabel coverage due to importance of definitions
    """
    total_classes = len(all_classes)
    with_definition = len(classes_with_definition)
    without_definition = len(classes_without_definition)
    coverage_percentage = (with_definition / total_classes * 100) if total_classes > 0 else 0
    
    # Calculate definition length statistics
    if classes_with_definition:
        definition_lengths = [len(def_text) for def_text in classes_with_definition.values()]
    
    print(f"\n--- SKOS Definition Coverage Summary ---")
    print(f"Total classes analyzed: {total_classes}")
    print(f"Classes with definitions: {with_definition} ({coverage_percentage:.1f}%)")
    print(f"Classes without definitions: {without_definition} ({100-coverage_percentage:.1f}%)")
    
    # Coverage assessment
    if coverage_percentage >= 90:
        assessment = "Excellent definition coverage!"
    elif coverage_percentage >= 75:
        assessment = "Good definition coverage"
    elif coverage_percentage >= 50:
        assessment = "Moderate definition coverage"
    elif coverage_percentage >= 25:
        assessment = "Low definition coverage"
    else:
        assessment = "Very low definition coverage - consider adding definitions for better semantic clarity"
    
    print(f"\nAssessment: {assessment}")

def _parse_rdf_list(node, graph):
    """
    Parses an RDF list starting at the given node into a Python list.

    Parameters
    ----------
    node : rdflib.term.Identifier
        The starting node of the RDF list (usually a blank node).
    graph : rdflib.Graph
        The RDF graph to parse the list from.

    Returns
    -------
    list
        A list of RDF nodes contained in the RDF collection.
    """
    items = []
    while node and node != RDF.nil:
        firsts = list(graph.objects(node, RDF.first))
        if not firsts:
            break
        items.append(firsts[0])
        rests = list(graph.objects(node, RDF.rest))
        node = rests[0] if rests else None
    return items

def _get_operands(node, graph):
    """
    Extracts operands of OWL class constructors (unionOf, intersectionOf, complementOf) from a given node.

    Parameters
    ----------
    node : rdflib.term.Identifier
        The node representing a class expression.
    graph : rdflib.Graph
        The RDF graph containing the ontology.

    Returns
    -------
    list
        A list of operand nodes that compose the class expression.
    """
    operands = []
    # Handle unionOf and intersectionOf which are RDF lists
    for constructor in [OWL.unionOf, OWL.intersectionOf]:
        for collection_node in graph.objects(node, constructor):
            operands.extend(_parse_rdf_list(collection_node, graph))
    # complementOf has a single operand
    for comp_node in graph.objects(node, OWL.complementOf):
        operands.append(comp_node)
    return operands

def _constructed_class_has_atomic_class(node, graph, atomic_classes, visited=None):
    """
    Recursively checks whether a class expression (named or anonymous) contains
    at least one atomic named class inside.

    Parameters
    ----------
    node : rdflib.term.Identifier
        The class expression node to check.
    graph : rdflib.Graph
        The RDF graph containing the ontology.
    atomic_classes : set
        A set of URIRefs that are identified as atomic named classes.
    visited : set, optional
        A set of nodes already visited to avoid cycles (default is None).

    Returns
    -------
    bool
        True if the class expression contains at least one atomic named class,
        False otherwise.
    """
    if visited is None:
        visited = set()
    if node in visited:
        return False
    visited.add(node)

    # If node is an atomic named class, return True
    if isinstance(node, URIRef) and node in atomic_classes:
        return True

    # Check operands if this node is constructed via OWL constructors
    operands = _get_operands(node, graph)
    if operands:
        for op in operands:
            if _constructed_class_has_atomic_class(op, graph, atomic_classes, visited):
                return True

    # If node is a blank node, recursively check all objects linked to it
    if isinstance(node, BNode):
        for _, o in graph.predicate_objects(node):
            if _constructed_class_has_atomic_class(o, graph, atomic_classes, visited):
                return True

    return False