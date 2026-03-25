from .helpers.helpers import _find_all_named_classes, _export_missing_labels_template,  _print_classes_without_labels, _print_classes_with_labels,  _print_label_summary_statistics, _analyze_label_coverage
from rdflib import Graph

def mainLabelCheck_v_0_0_1(ttl_file, show="all", export_template=None):
    """
    RDFS Label Coverage Analysis

    Analyze an OWL ontology in Turtle (ttl) format to assess the coverage and
    quality of RDFS labels (rdfs:label) across all named classes

    This main function loads an ontology file, identifies all named classes, and
    provides comprehensive analysis of label coverage with various display options
    and export capabilities

    Definitions
    -----------
    - Named classes: Classes with URIRef identifiers that are explicitly declared
      as owl:Class or rdfs:Class, or participate in rdfs:subClassOf relations

    - Valid labels: rdfs:label values that are non-empty strings after whitespace
      trimming. Empty strings and whitespace-only labels are not counted as valid labels

    - Coverage percentage: The proportion of named classes that have at least one
      valid rdfs:label

    Author: Rishabh Kundu
    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle (.ttl) file to analyze -- input file

    show : str, optional
        Display option controlling what information to show:
        - "all" (default): Shows summary statistics, classes with labels, and classes without labels
        - "with": Shows only classes that have rdfs:label
        - "without": Shows only classes that lack rdfs:label
        - "summary": Shows only summary statistics

    export_template : str, optional
        Export a CSV template file for classes missing rdfs:label.
        Provide the desired output filename (e.g. "missing_labels_in_classes.csv").
        Default is None (no export)

    Returns
    -------
    None
        This function does not directly return values. It prints analysis results
        to your terminal/CLI and optionally exports a CSV template file. The function
        may exit early on errors (file not found, parsing errors, or no classes found)

    Output Information
    ------------------
    When executed successfully, the analysis provides:
    - Total number of named classes analyzed
    - Number of classes with valid rdfs:label properties
    - Number of classes lacking valid rdfs:label properties
    - Coverage percentage of classes with rdfs:label
    - Prefixed class name and full URI/IRI for each class

    Error Handling
    --------------
    - FileNotFoundError: When the specified TTL file cannot be found
    - Parsing errors: When the TTL file cannot be parsed as valid Turtle
    - Empty ontology: When no named classes are found in the ontology

    Notes
    -----
    - Only named classes (URIRef instances) are considered in the analysis
    - Empty strings and whitespace-only labels are treated as missing labels
    - Classes are displayed with both their prefixed name and full URI/IRI
    - show and export_template parameters are set to default values ("all" and None)
        - thus, CSV export request must be explicitly mentioned

    LLM Usage Declaration
    ---------------------
    - Claude AI (Sonnet 4.6) was employed chiefly to support documentation efforts

    Examples
    --------
    Basic usage (show all):
        mainLabelCheck_v_0_0_1("ontology.ttl")

    Show only summary:
        mainLabelCheck_v_0_0_1("ontology.ttl", show="summary")

    Show only classes missing labels:
        mainLabelCheck_v_0_0_1("ontology.ttl", show="without")

    Export CSV template for missing labels:
        mainLabelCheck_v_0_0_1("ontology.ttl", export_template="missing_labels.csv")

    Export template while showing summary only:
        mainLabelCheck_v_0_0_1("ontology.ttl", show="summary", export_template="missing_labels.csv")
            - in the afore a desired export path can also be inserted
    """
    # Validate "show" parameter of main function
    valid_show_options = ["all", "with", "without", "summary"]
    if show not in valid_show_options:
        print(f"Error: Invalid 'show' parameter. Must be one of {valid_show_options}")
        return

    g = Graph()
    try:
        print(f"Parsing file: {ttl_file}...")
        # Bind common prefixes for cleaner output (future users can add more here)
        g.bind("mds",  "https://cwrusdle.bitbucket.io/mds/")
        g.bind("cco",  "https://www.commoncoreontologies.org/")
        g.bind("obo",  "http://purl.obolibrary.org/obo/")
        g.bind("owl",  "http://www.w3.org/2002/07/owl#")
        g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
        g.bind("skos", "http://www.w3.org/2004/02/skos/core#")
        g.parse(ttl_file, format="turtle")
    except FileNotFoundError:
        print(f"Error: The file '{ttl_file}' was not found.")
        return
    except Exception as e:
        print(f"Error: An error occurred while parsing the TTL file: {e}")
        return

    # Find all named classes
    all_classes = _find_all_named_classes(g)
    if not all_classes:
        print("No named classes found in the ontology.")
        return

    # Analyze rdfs:label coverage
    classes_with_label, classes_without_label = _analyze_label_coverage(g, all_classes)

    # Display results as desired by user
    if show in ["summary", "all"]:
        _print_label_summary_statistics(g, classes_with_label, classes_without_label, all_classes)
    if show in ["with", "all"]:
        _print_classes_with_labels(g, classes_with_label)
    if show in ["without", "all"]:
        _print_classes_without_labels(g, classes_without_label)

    # Export template if requested explicitly by user
    if export_template and classes_without_label:
        _export_missing_labels_template(g, classes_without_label, export_template)
    elif export_template and not classes_without_label:
        print("All classes have rdfs:label — no template needed!")