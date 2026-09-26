"""
mainLabelCheck_v_0_0_1 metric implementation.

Changelog (v0.0.2)
------------------
- FIXED: the function returned ``None`` on every path, so ``run_assessment``
  wrote an empty ``Score`` column for this metric. It now returns a result
  dictionary whose ``coverage`` key is the headline score; the printing and
  export behaviour is unchanged.
- FIXED: the early-return paths (invalid ``show``, missing file, parse error,
  no classes) also returned ``None`` indistinguishably from a successful run.
  They now return ``None`` only for genuine failure, and the successful
  "no classes found" case returns a result with ``coverage`` of 0.0 and a
  ``status`` key explaining why.
"""

import logging

from .helpers.helpers import _find_all_named_classes, _export_missing_labels_template,  _print_classes_without_labels, _print_classes_with_labels,  _print_label_summary_statistics, _analyze_label_coverage
from rdflib import Graph

logger = logging.getLogger(__name__)

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
      valid rdfs:label. This is the value returned as the metric score.

    Author: Rishabh Kundu
    Version: 0.0.2

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
    dict or None
        On success, a dictionary with the following keys:

        - ``coverage`` (float): proportion of named classes carrying a valid
          ``rdfs:label``, in [0, 1].  This is the headline score.
        - ``total_classes`` (int)
        - ``classes_with_label`` (int)
        - ``classes_without_label`` (int)
        - ``missing`` (list of str): URIs of classes lacking a label
        - ``status`` (str): ``"Success"``, or an explanation when no classes
          were found
        - ``exported_template`` (str or None): path written, if any

        ``None`` is returned only on genuine failure: an invalid ``show``
        value, a missing file, or a Turtle parse error.

        In version 0.0.1 this function returned ``None`` on every path,
        including success, which left the ``Score`` column of
        ``assessment_scores.csv`` empty for this metric.

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
    - This metric covers named classes only.  FOOPS! VOC3-T requires label
      coverage across *all* terms, including properties and individuals; see
      ``foops_metadata_checks.foops_voc3_all_terms_labelled_v_0_0_1``.

    .. note::

       Claude AI (Sonnet 4.6) was employed chiefly to support documentation efforts.

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

    Read the score:
        result = mainLabelCheck_v_0_0_1("ontology.ttl", show="summary")
        print(f"Label coverage: {result['coverage']:.1%}")
    """
    # Validate "show" parameter of main function
    valid_show_options = ["all", "with", "without", "summary"]
    if show not in valid_show_options:
        logger.error(f"Invalid 'show' parameter. Must be one of {valid_show_options}")
        return None

    g = Graph()
    try:
        logger.info(f"Parsing file: {ttl_file}...")
        # Bind common prefixes for cleaner output (future users can add more here)
        g.bind("mds",  "https://cwrusdle.bitbucket.io/mds/")
        g.bind("cco",  "https://www.commoncoreontologies.org/")
        g.bind("obo",  "http://purl.obolibrary.org/obo/")
        g.bind("owl",  "http://www.w3.org/2002/07/owl#")
        g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
        g.bind("skos", "http://www.w3.org/2004/02/skos/core#")
        g.parse(ttl_file, format="turtle")
    except FileNotFoundError:
        logger.error(f"The file '{ttl_file}' was not found.")
        return None
    except Exception as e:
        logger.error(f"An error occurred while parsing the TTL file: {e}")
        return None

    # Find all named classes
    all_classes = _find_all_named_classes(g)
    if not all_classes:
        logger.info("No named classes found in the ontology.")
        return {
            "coverage": 0.0,
            "total_classes": 0,
            "classes_with_label": 0,
            "classes_without_label": 0,
            "missing": [],
            "status": "No named classes found in the ontology",
            "exported_template": None,
        }

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
    exported = None
    if export_template and classes_without_label:
        _export_missing_labels_template(g, classes_without_label, export_template)
        exported = export_template
    elif export_template and not classes_without_label:
        logger.info("All classes have rdfs:label — no template needed!")

    total = len(all_classes)
    with_count = len(classes_with_label)
    coverage = (with_count / total) if total else 0.0

    return {
        "coverage": coverage,
        "total_classes": total,
        "classes_with_label": with_count,
        "classes_without_label": len(classes_without_label),
        "missing": sorted(str(c) for c in classes_without_label),
        "status": "Success",
        "exported_template": exported,
    }
