from .helpers.helpers import _export_space_errors, _print_space_errors, _scan_file_for_space_errors

def mainClassNameSpaceCheck_v_0_0_1(ttl_file, export_template=None):
    """
    Class Name Space Check Analysis

    Scan an OWL ontology in Turtle (ttl) format for class names containing
    spaces. Spaces in prefixed class names make a TTL file unparseable, so
    this function works directly on the raw file text rather than parsing it
    through rdflib.

    Handles both single-line and multi-line class declarations by grouping
    lines into declaration blocks before checking for spaces.

    Author: Rishabh Kundu
    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle (.ttl) file to analyze -- input file

    export_template : str, optional
        Export a CSV report of all class names containing spaces.
        Provide the desired output filename (e.g. "classes_with_spaces_in_names.csv").
        Default is None (no export)

    Returns
    -------
    None
        Prints results to terminal/CLI and optionally exports a CSV report.

    Output Information
    ------------------
    When executed successfully, the analysis provides:
    - Total number of class names with spaces detected
    - The class names with space, line number, and full line text for each

    Error Handling
    --------------
    - FileNotFoundError: When the specified TTL file cannot be found

    Notes
    -----
    - Does not use rdflib parsing - works on raw file text so it catches
      errors that would prevent parsing entirely
    - Detects owl:Class and rdfs:Class declarations
    - Handles multi-line declarations by grouping on '.' block terminators
    - Comments and string literals are handled to avoid false matches

    LLM Usage Declaration
    ---------------------
    - Claude AI (Sonnet 4.6) was employed chiefly to support documentation efforts

    Examples
    --------
    Basic usage:
        mainClassNameSpaceCheck_v_0_0_1("ontology.ttl")

    Export CSV report:
        mainClassNameSpaceCheck_v_0_0_1("ontology.ttl", export_template="classes_with_spaces_in_names.csv")
    """
    try:
        errors = _scan_file_for_space_errors(ttl_file)
    except FileNotFoundError:
        print(f"Error: The file '{ttl_file}' was not found.")
        return

    _print_space_errors(errors)

    if export_template and errors:
        _export_space_errors(errors, export_template)
    elif export_template and not errors:
        print("No class names with spaces detected — no report needed!")