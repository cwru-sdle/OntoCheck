from .helpers.helpers import _analyze_altlabel_coverage, _export_missing_altlabels_template, _find_all_named_classes, _get_preferred_label, _print_classes_with_altlabels, _print_classes_without_altlabels, _print_summary_statistics
from collections import defaultdict
from rdflib import Graph, RDFS, RDF, OWL, URIRef, Namespace
import argparse

def mainAltLabelCheck_v_0_0_1():
    """
    SKOS Alternative Label Coverage Analysis

    Analyze an OWL ontology in Turtle (ttl) format to assess the coverage and quality of SKOS alternative labels (skos:altLabel) across all named classes.
    This main function parses command-line arguments, loads an ontology file, identifies all named classes, and provides comprehensive analysis of alternative label coverage with various display options and export capabilities.

    Definitions
    -----------
    - Named classes: Classes with URIRef identifiers that are explicitly declared as owl:Class or rdfs:Class, or participate in rdfs:subClassOf relations
    - Valid altLabels: SKOS altLabel values that are non-empty strings after whitespace trimming. Empty strings and whitespace-only altLabels are not accounted as valid altLabels
    - Coverage percentage: The proportion of named classes that have at least one valid altLabel inclusion

    Author: Rishabh Kundu
    Version: 0.0.1

    Command Line Arguments
    ----------------------
    ttl_file : str (positional)
        Path to the ontology Turtle (.ttl) file to analyze -- input file

    --show : str, optional
        Display option controlling what information to show:

        - "all" (default): Shows summary statistics, classes with altLabels, and classes without altLabels
        - "with": Shows only classes that have altLabels
        - "without": Shows only classes that lack altLabels
        - "summary": Shows only summary statistics

    --export-template : str, optional
        Export a Turtle format template file for classes missing altLabels.
        Provide the desired output filename.

    Returns
    -------
    None
        This function does not (directly) return values. It prints analysis results to your terminal/CLI and optionally exports a template file. The function may exit early on errors (file not found, parsing errors, or no classes found).

    Output Information
    ------------------
    When executed successfully, the analysis provides:

    - Total number of named classes analyzed
    - Number of classes with valid altLabel properties
    - Number of classes lacking valid altLabel properties
    - Coverage percentage of classes with altLabels
    - Total count of altLabel instances across all classes
    - Average number of altLabels per class (for classes with altLabels)
    - Qualitative assessment based on coverage thresholds

    Error Handling
    --------------
    The function handles several error conditions:

    - FileNotFoundError: When the specified TTL file cannot be found
    - Parsing errors: When the TTL file cannot be parsed as valid Turtle
    - Empty ontology: When no named classes are found in the ontology
    - Template export errors: File I/O issues when exporting templates

    Notes
    -----
    - Only named classes (URIRef instances) are considered in the analysis
    - Empty strings and whitespace-only altLabels are filtered out
    - Coverage assessment follows established ontology quality thresholds: ≥80%: Excellent, ≥60%: Good, ≥40%: Moderate, ≥20%: Low, <20%: Very low
    - Classes are displayed with their preferred labels (skos:prefLabel or rdfs:label) when available
    - Template export generates valid Turtle syntax for adding missing altLabels
    - Uses argparse for command-line interface, not direct function parameters

    LLM Usage Declaration
    ---------------------
    - Claude AI (Sonnet 4) was employed chiefly to support documentation efforts

    Examples
    --------
    Basic usage::

        python script.py ontology.ttl

    Show only summary::

        python script.py ontology.ttl --show summary

    Export template for missing labels::

        python script.py ontology.ttl --export-template missing_labels.ttl
    """
    parser = argparse.ArgumentParser(
        description="Analyzes SKOS altLabel coverage in an ontology file."
    )
    parser.add_argument("ttl_file", help="Path to the ontology .ttl file.")
    parser.add_argument("--show", choices=["all", "with", "without", "summary"], 
                       default="all", help="What to display: 'all' (default), 'with' (classes with altLabels), 'without' (classes without altLabels), 'summary' (statistics only)")
    parser.add_argument("--export-template", type=str, 
                       help="Export a template file for classes missing altLabels (provide filename)")
    
    args = parser.parse_args()

    g = Graph()
    try:
        print(f"Parsing file: {args.ttl_file}...")
        # Bind common prefixes for cleaner output (future users can add more here)
        g.bind("mds", "https://cwrusdle.bitbucket.io/mds/")
        g.bind("cco", "https://www.commoncoreontologies.org/")
        g.bind("obo", "http://purl.obolibrary.org/obo/")
        g.bind("owl", "http://www.w3.org/2002/07/owl#")
        g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
        g.bind("skos", "http://www.w3.org/2004/02/skos/core#")
        g.parse(args.ttl_file, format="turtle")
    except FileNotFoundError:
        print(f"Error: The file '{args.ttl_file}' was not found.")
        return
    except Exception as e:
        print(f"Error: An error occurred while parsing the TTL file: {e}")
        return

    # Find all classes
    all_classes = _find_all_named_classes(g)
    if not all_classes:
        print("No named classes found in the ontology.")
        return

    # Analyze altLabel coverage
    classes_with_altlabel, classes_without_altlabel = _analyze_altlabel_coverage(g, all_classes)

    # Display results based on show choice
    if args.show in ["summary", "all"]:
        _print_summary_statistics(g, classes_with_altlabel, classes_without_altlabel, all_classes)

    if args.show in ["with", "all"]:
        _print_classes_with_altlabels(g, classes_with_altlabel)

    if args.show in ["without", "all"]:
        _print_classes_without_altlabels(g, classes_without_altlabel)

    # Export template if requested
    if args.export_template and classes_without_altlabel:
        _export_missing_altlabels_template(g, classes_without_altlabel, args.export_template)
    elif args.export_template and not classes_without_altlabel:
        print("No classes missing altLabels - no template needed!")
