from .helpers.helpers import _find_all_named_classes, _analyze_capital_coverage, _print_capital_summary_statistics, _print_classes_with_capital, _print_classes_without_capital, _export_non_capital_classes_template
from rdflib import Graph

def mainClassNameCapitalCheck_v_0_0_1(ttl_file, show="all", export_template=None):
    """
    Class Name Capital Letter Check Analysis

    Analyze an OWL ontology in Turtle (ttl) format to assess whether all
    named classes follow the convention of starting their local name with
    a capital letter

    This main function loads an ontology file, identifies all named classes,
    and provides comprehensive analysis of capital letter compliance with
    various display options and export capabilities

    Definitions
    -----------
    - Named classes: Classes with URIRef identifiers that are explicitly declared
      as owl:Class or rdfs:Class, or participate in rdfs:subClassOf relations

    - Local name: The fragment of a class URI after the last '#' or '/' character.
      Only this portion is checked, not the full namespace URI

    - Compliant class: A class whose local name begins with an uppercase letter
      as determined by Python's str.isupper() check on the first character

    - Coverage percentage: The proportion of named classes whose local name
      starts with a capital letter

    Author: Rishabh Kundu
    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle (.ttl) file to analyze -- input file

    show : str, optional
        Display option controlling what information to show:
        - "all" (default): Shows summary statistics, compliant classes, and non-compliant classes
        - "with": Shows only classes whose local name starts with a capital letter
        - "without": Shows only classes whose local name does not start with a capital letter
        - "summary": Shows only summary statistics

    export_template : str, optional
        Export a CSV report file for classes that do not start with a capital letter.
        Provide the desired output filename (e.g. "non_capital_classes.csv").
        Default is None (no export)

    Returns
    -------
    None
        This function does not directly return values. It prints analysis results
        to your terminal/CLI and optionally exports a CSV report file. The function
        may exit early on errors (file not found, parsing errors, or no classes found)

    Output Information
    ------------------
    When executed successfully, the analysis provides:
    - Total no. of named classes analyzed
    - No. of classes whose local name starts with a capital letter
    - No. of classes whose local name does not start with a capital letter
    - Coverage percentage of compliant classes
    - Prefixed class name, full URI/IRI, and local name for each class

    Error Handling
    --------------
    - FileNotFoundError: When the specified TTL file cannot be found
    - Parsing errors: When the TTL file cannot be parsed as valid Turtle
    - Empty ontology: When no named classes are found in the ontology

    Notes
    -----
    - Only named classes (URIRef instances) are considered in the analysis
    - Only the local name fragment is checked, not the full URI
    - Classes with an empty local name are treated as non-compliant
    - show and export_template parameters are set to default values ("all" and None)
        - thus, CSV export must be explicitly requested

    LLM Usage Declaration
    ---------------------
    - Claude AI (Sonnet 4.6) was employed chiefly to support documentation efforts

    Examples
    --------
    Basic usage (show all):
        mainClassNameCapitalCheck_v_0_0_1("ontology.ttl")

    Show only summary:
        mainClassNameCapitalCheck_v_0_0_1("ontology.ttl", show="summary")

    Show only non-compliant classes:
        mainClassNameCapitalCheck_v_0_0_1("ontology.ttl", show="without")

    Export CSV report of non-compliant classes:
        mainClassNameCapitalCheck_v_0_0_1("ontology.ttl", export_template="non_capital_classes.csv")
            - a desired export path can also be inserted in the filename

    Export report while showing summary only:
        mainClassNameCapitalCheck_v_0_0_1("ontology.ttl", show="summary", export_template="non_capital_classes.csv")
            - a desired export path can also be inserted in the filename
    """
    valid_show_options = ["all", "with", "without", "summary"]
    if show not in valid_show_options:
        print(f"Error: Invalid 'show' parameter. Must be one of {valid_show_options}")
        return

    g = Graph()
    try:
        print(f"Parsing file: {ttl_file}...")
        # more can be added in the future as needed
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

    # Analyze capital letter compliance
    classes_with_capital, classes_without_capital = _analyze_capital_coverage(g, all_classes)

    # Display results as desired by user
    if show in ["summary", "all"]:
        _print_capital_summary_statistics(g, classes_with_capital, classes_without_capital, all_classes)
    if show in ["with", "all"]:
        _print_classes_with_capital(g, classes_with_capital)
    if show in ["without", "all"]:
        _print_classes_without_capital(g, classes_without_capital)

    # Export template if explicitly requested by user
    if export_template and classes_without_capital:
        _export_non_capital_classes_template(g, classes_without_capital, export_template)
    elif export_template and not classes_without_capital:
        print("All classes start with a capital letter — no report export needed!")