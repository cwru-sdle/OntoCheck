"""
mainDefCheck_v_0_0_1 metric implementation.
Extracted from: /mnt/vstor/CSE_MSE_RXF131/cradle-members/mds3/mxm1684/Git/ontologyassessment/Scripts/Rishabh/DefCheck.py
"""

from .helpers.helpers import _analyze_definition_coverage, _find_all_named_classes, _get_additional_labels, _get_preferred_label, _print_classes_with_definitions, _print_classes_without_definitions, _print_summary_statistics, _truncate_definition
from collections import defaultdict
from rdflib import Graph, RDFS, RDF, OWL, URIRef, Namespace

def mainDefCheck_v_0_0_1(ttl_file, show="all", full_definitions=False): # show and full_definitions set to default values
    """
    SKOS Definition Coverage Analysis

    Analyze an OWL ontology in Turtle (ttl) format and assess the coverage and quality of SKOS definitions (skos:definition) across all named classes

    This main function loads an ontology file, identifies all named classes, and provides comprehensive analysis of definition coverage with various display options

    Definitions
    -----------
    - Named classes: Classes with URIRef identifiers that are explicitly declared as 
      owl:Class or rdfs:Class, or participate in rdfs:subClassOf relations
    
    - Valid definitions: SKOS definition values that exist as properties on classes
      Empty or missing definitions are identified as gaps in coverage

    - Coverage percentage: The proportion of named classes that have at least one 
      skos:definition property

    Author: Rishabh Kundu
    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle (.ttl) file to analyze
        
    show : str, optional
        Display option controlling what information to show:
        - "all" (default): Shows summary statistics, classes with definitions, and classes without definitions
        - "with": Shows only classes that have definitions
        - "without": Shows only classes that lack definitions  
        - "summary": Shows only summary statistics
        
    full_definitions : bool, optional
        Show full definitions instead of truncated versions (default: False, truncated to 150 chars)

    Returns
    -------
    None
        This function does not (directly) return values. It prints analysis results to terminal/CLI
        The function may exit early on errors (file not found, parsing errors, or no classes found)

    Output Information
    -----------------
    When executed successfully, the analysis provides:
    - Total number of named classes analyzed
    - Number of classes with definition properties
    - Number of classes lacking definition properties
    - Coverage percentage of classes with definitions
    - Qualitative assessment based on coverage thresholds

    Error Handling
    -------------
    The function handles several error conditions:
    - FileNotFoundError: When the specified TTL file cannot be found
    - Parsing errors: When the TTL file cannot be parsed as valid Turtle
    - Empty ontology: When no named classes are found in the ontology

    Notes
    -----
    - Only named classes (URIRef instances) are considered in the analysis
    - Uses skos:definition property specifically for definition identification
    - Coverage assessment follows ontology quality thresholds with higher standards than altLabels: ≥90%: Excellent, ≥75%: Good, ≥50%: Moderate, ≥25%: Low, <25%: Very low
    - Classes are displayed with their preferred labels (skos:prefLabel or rdfs:label) when available
    - show and full_definitions function parameters set to default values (all and False, respectively)

    LLM Usage Declaration
    ---------------------

    - Claude AI (Sonnet 4) was employed chiefly to support documentation efforts

    Examples
    --------
    Basic usage:
        python script.py ontology.ttl
        
    Show only summary:
        python script.py ontology.ttl --show summary
        
    Show full definitions:
        python script.py ontology.ttl --full-definitions
        
    Show only classes without definitions:
        python script.py ontology.ttl --show without
    """
    # Validate show parameter
    valid_show_options = ["all", "with", "without", "summary"]
    if show not in valid_show_options:
        print(f"Error: Invalid 'show' parameter. Must be one of {valid_show_options}")
        return

    g = Graph()
    try:
        print(f"Parsing file: {ttl_file}...")
        # Bind common prefixes for cleaner output (future users can add more here)
        g.bind("mds", "https://cwrusdle.bitbucket.io/mds/")
        g.bind("cco", "https://www.commoncoreontologies.org/")
        g.bind("obo", "http://purl.obolibrary.org/obo/")
        g.bind("owl", "http://www.w3.org/2002/07/owl#")
        g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
        g.bind("skos", "http://www.w3.org/2004/02/skos/core#")
        g.parse(ttl_file, format="turtle")
    except FileNotFoundError:
        print(f"Error: The file '{ttl_file}' was not found.")
        return
    except Exception as e:
        print(f"Error: An error occurred while parsing the TTL file: {e}")
        return

    # Find all classes
    all_classes = _find_all_named_classes(g)
    if not all_classes:
        print("No named classes found in the ontology.")
        return

    # Analyze definition coverage
    classes_with_definition, classes_without_definition = _analyze_definition_coverage(g, all_classes)

    # Display results based on show choice
    if show in ["summary", "all"]:
        _print_summary_statistics(g, classes_with_definition, classes_without_definition, all_classes)

    if show in ["with", "all"]:
        _print_classes_with_definitions(g, classes_with_definition, full_definitions)

    if show in ["without", "all"]:
        _print_classes_without_definitions(g, classes_without_definition)
