"""
Ontology Assessment Runner

Provides runner functions for the four OntoCheck assessment modes:

    Mode 1 -- Task-agnostic:  structural, labeling, accessibility, and
              naming-convention metrics applied to a single ontology.
    Mode 2 -- Task-specific Web ontology:  task-based Relevance/Accuracy
              validated against a knowledge graph (e.g., DBpedia via LC-QuAD).
    Mode 3 -- Task-based Scientific:  domain ontology assessed against
              competency questions encoded as SPARQL queries.
    Mode 4 -- Cross-Domain:  multiple ontologies merged and assessed against
              cross-domain competency questions.
"""

import logging
import sys
import csv
from pathlib import Path

from .altLabelCheck import mainAltLabelCheck_v_0_0_1
from .check_external_data_provider_links_ttl import check_external_data_provider_links_ttl
from .check_for_isolated_elements import check_for_isolated_elements
from .check_human_readable_license_ttl import check_human_readable_license_ttl
from .check_rdf_dump_accessibility_ttl import check_rdf_dump_accessibility_ttl
from .check_sparql_accessibility_ttl import check_sparql_accessibility_ttl
from .count_class_connected_components import count_class_connected_components
from .defCheck import mainDefCheck_v_0_0_1
from .find_duplicate_labels_from_graph import find_duplicate_labels_from_graph
from .get_properties_missing_domain_and_range import get_properties_missing_domain_and_range
from .leafNodeCheck import mainLeafNodeCheck_v_0_0_1
from .semanticConnection import mainSemanticConnection_v_0_0_1
from .mds_design_check import mds_design_check_v_0_0_1
from .spell_check import spell_check_v_0_0_1
from .check_class_name_capital import mainClassNameCapitalCheck_v_0_0_1
from .check_class_name_space import mainClassNameSpaceCheck_v_0_0_1
from .check_label import mainLabelCheck_v_0_0_1
from .class_search import mainClassSearch_v_0_0_1
from .task_based_metric import task_based_metric_v_0_0_1

METRIC_DISPATCHER = {
    "altLabelCheck": mainAltLabelCheck_v_0_0_1,
    "externalLinks": check_external_data_provider_links_ttl,
    "isolatedElements": check_for_isolated_elements,
    "humanLicense": check_human_readable_license_ttl,
    "rdfDump": check_rdf_dump_accessibility_ttl,
    "sparqlEndpoint": check_sparql_accessibility_ttl,
    "classConnections": count_class_connected_components,
    "definitionCheck": mainDefCheck_v_0_0_1,
    "duplicateLabels": find_duplicate_labels_from_graph,
    "missingDomainRange": get_properties_missing_domain_and_range,
    "leafNodeCheck": mainLeafNodeCheck_v_0_0_1,
    "semanticConnection": mainSemanticConnection_v_0_0_1,
    "mdsDesignCheck": mds_design_check_v_0_0_1,
    "spellCheck": spell_check_v_0_0_1,
    "classCapitalCheck": mainClassNameCapitalCheck_v_0_0_1,
    "classSpaceCheck": mainClassNameSpaceCheck_v_0_0_1,
    "checkLabel": mainLabelCheck_v_0_0_1,
    "searchClass": mainClassSearch_v_0_0_1,
}


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _setup_logging(output_log_file):
    """Configure file and console logging, returning the console handler."""
    logging.basicConfig(
        filename=output_log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="w",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    logging.getLogger().addHandler(console_handler)
    return console_handler


def _teardown_logging(console_handler):
    """Remove the console handler added by ``_setup_logging``."""
    logging.getLogger().removeHandler(console_handler)


# ---------------------------------------------------------------------------
# Mode 1: Task-agnostic assessment
# ---------------------------------------------------------------------------

def run_ontology_assessment(
    ttl_file,
    metrics,
    search_term=None,
    output_log_file="assessment.log",
    output_csv_file="assessment_scores.csv",
):
    """Run task-agnostic metrics on a single ontology (Mode 1).

    Parameters
    ----------
    ttl_file : str
        Path to the input Turtle (.ttl) ontology file.
    metrics : list of str or str
        Metric names to execute, or ``"all"`` to run every metric in
        ``METRIC_DISPATCHER``.
    search_term : str or None, optional
        Search string for the ``searchClass`` metric.  When ``None`` and
        ``searchClass`` is requested, the metric is skipped with a warning.
    output_log_file : str, optional
        Output log file path.
    output_csv_file : str, optional
        Output CSV file path.
    """
    console = _setup_logging(output_log_file)

    if metrics == "all":
        metrics_to_run = list(METRIC_DISPATCHER.keys())
        logging.info("Running all available metrics.")
    elif isinstance(metrics, (list, set, tuple)):
        metrics_to_run = list(metrics)
    else:
        raise ValueError(
            "The 'metrics' argument must be a list of metric names or the string 'all'."
        )

    logging.info(f"--- Starting ontology assessment for: {ttl_file} ---")
    logging.info(f"Metrics to run: {', '.join(metrics_to_run)}")

    results = []

    for metric_name in metrics_to_run:
        if metric_name not in METRIC_DISPATCHER:
            logging.warning(f"Metric '{metric_name}' not found. Skipping.")
            continue

        if metric_name == "searchClass" and search_term is None:
            logging.warning(
                "Skipping 'searchClass': --search-term not provided. "
                "Re-run with --search-term <term> to include this metric."
            )
            results.append({
                "Metric": metric_name,
                "Score": "N/A",
                "Status": "Skipped (--search-term not provided)",
            })
            continue

        metric_function = METRIC_DISPATCHER[metric_name]
        logging.info(f"--- Running Metric: {metric_name} ---")

        try:
            if metric_name == "searchClass":
                score = metric_function(ttl_file, search_term)
            else:
                score = metric_function(ttl_file)
            logging.info(f"Metric '{metric_name}' completed successfully.")
            results.append({"Metric": metric_name, "Score": score, "Status": "Success"})
        except Exception as e:
            logging.error(f"Metric '{metric_name}' failed with an error: {e}", exc_info=True)
            results.append({"Metric": metric_name, "Score": "N/A", "Status": f"Error: {e}"})

    _write_csv(results, output_csv_file)

    logging.info("--- Assessment Complete ---")
    _teardown_logging(console)


# ---------------------------------------------------------------------------
# Mode 2: Task-specific Web ontology assessment
# ---------------------------------------------------------------------------

def run_web_ontology_assessment(
    ttl_file,
    questions,
    domain_prefixes,
    knowledge_graph,
    domain_ns_fragments=None,
    metrics=None,
    search_term=None,
    output_log_file="assessment.log",
    output_csv_file="assessment_scores.csv",
):
    """Assess a Web ontology against KGQA benchmark queries (Mode 2).

    Runs the task-based Relevance/Accuracy assessment using competency
    queries drawn from a knowledge-graph question-answering benchmark
    (e.g., LC-QuAD over DBpedia).  Optionally runs task-agnostic metrics
    as well.

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle file.
    questions : str or list of str
        Path to a JSON/Markdown file of SPARQL queries, or a list of raw
        SPARQL query strings.
    domain_prefixes : list of str
        Namespace prefixes used in the SPARQL queries (e.g., ``["dbo"]``).
    knowledge_graph : str
        Path to the knowledge-graph file (Turtle/RDF) used for validation
        context.
    domain_ns_fragments : list of str or None, optional
        Namespace URI fragments to restrict domain-term filtering.
    metrics : list of str or None, optional
        Task-agnostic metric names to run alongside the task-based
        assessment.  Pass ``"all"`` for every available metric.
    output_log_file : str, optional
        Output log file path.
    output_csv_file : str, optional
        Output CSV file path.
    """
    console = _setup_logging(output_log_file)

    logging.info("--- Mode 2: Task-specific Web Ontology Assessment ---")
    logging.info(f"Ontology: {ttl_file}")
    logging.info(f"Knowledge graph: {knowledge_graph}")

    result = task_based_metric_v_0_0_1(
        ttl_file=ttl_file,
        questions=questions,
        domain_prefixes=domain_prefixes,
        domain_ns_fragments=domain_ns_fragments,
    )

    _log_task_based_result(result)

    results = _task_based_result_to_rows(result)

    if metrics:
        logging.info("--- Running task-agnostic metrics ---")
        results.extend(_run_agnostic_metrics(ttl_file, metrics, search_term))

    _write_csv(results, output_csv_file)

    logging.info("--- Assessment Complete ---")
    _teardown_logging(console)

    return result


# ---------------------------------------------------------------------------
# Mode 3 & 4: Task-based Scientific / Cross-Domain assessment
# ---------------------------------------------------------------------------

def run_task_based_assessment(
    ttl_files,
    questions,
    domain_prefixes,
    domain_ns_fragments=None,
    metrics=None,
    search_term=None,
    output_log_file="assessment.log",
    output_csv_file="assessment_scores.csv",
):
    """Assess one or more ontologies against competency questions (Modes 3/4).

    When a single ontology is provided this corresponds to Mode 3
    (task-based scientific assessment).  When multiple ontologies are
    provided they are merged and evaluated jointly, corresponding to
    Mode 4 (cross-domain assessment).

    Parameters
    ----------
    ttl_files : str or list of str
        Path(s) to Turtle (.ttl) ontology file(s).  A single path is
        accepted and will be wrapped in a list internally.
    questions : str or list of str
        Path to a JSON/Markdown file of SPARQL queries, or a list of raw
        SPARQL query strings.
    domain_prefixes : list of str
        Namespace prefixes used in the SPARQL queries (e.g., ``["mds"]``).
    domain_ns_fragments : list of str or None, optional
        Namespace URI fragments to restrict domain-term filtering.
    metrics : list of str or None, optional
        Task-agnostic metric names to run alongside the task-based
        assessment.  Pass ``"all"`` for every available metric.
    output_log_file : str, optional
        Output log file path.
    output_csv_file : str, optional
        Output CSV file path.

    Returns
    -------
    dict
        The result dictionary from ``task_based_metric_v_0_0_1``.
    """
    if isinstance(ttl_files, (str, Path)):
        ttl_files = [ttl_files]

    console = _setup_logging(output_log_file)

    if len(ttl_files) > 1:
        logging.info("--- Mode 4: Cross-Domain Ontology Assessment ---")
    else:
        logging.info("--- Mode 3: Task-based Scientific Ontology Assessment ---")
    logging.info(f"Ontologies: {', '.join(str(f) for f in ttl_files)}")

    result = task_based_metric_v_0_0_1(
        ttl_file=ttl_files,
        questions=questions,
        domain_prefixes=domain_prefixes,
        domain_ns_fragments=domain_ns_fragments,
    )

    _log_task_based_result(result)

    results = _task_based_result_to_rows(result)

    if metrics:
        logging.info("--- Running task-agnostic metrics ---")
        for f in ttl_files:
            logging.info(f"--- Task-agnostic metrics for: {f} ---")
            results.extend(_run_agnostic_metrics(str(f), metrics, search_term))

    _write_csv(results, output_csv_file)

    logging.info("--- Assessment Complete ---")
    _teardown_logging(console)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_task_based_result(result):
    """Log the task-based Relevance/Accuracy results."""
    logging.info(f"Relevance (Recall):    {result['relevance']:.4f}")
    logging.info(f"Accuracy  (Precision): {result['accuracy']:.4f}")
    logging.info(f"Ontology terms  (T_o): {result['T_o_count']}")
    logging.info(f"Task terms      (T_a): {result['T_a_count']}")
    logging.info(f"Intersection:          {result['intersection']}")
    if result["missing_from_onto"]:
        logging.info(
            f"Missing from ontology: {', '.join(sorted(result['missing_from_onto']))}"
        )
    if result["unused_in_onto"]:
        logging.info(
            f"Unused ontology terms: {len(result['unused_in_onto'])} terms"
        )


def _task_based_result_to_rows(result):
    """Convert a task-based result dict to CSV-compatible row dicts."""
    return [
        {"Metric": "Relevance", "Score": f"{result['relevance']:.4f}", "Status": "Success"},
        {"Metric": "Accuracy", "Score": f"{result['accuracy']:.4f}", "Status": "Success"},
        {"Metric": "T_o_count", "Score": result["T_o_count"], "Status": "Success"},
        {"Metric": "T_a_count", "Score": result["T_a_count"], "Status": "Success"},
        {"Metric": "Intersection", "Score": result["intersection"], "Status": "Success"},
    ]


def _run_agnostic_metrics(ttl_file, metrics, search_term=None):
    """Run task-agnostic metrics and return a list of result row dicts."""
    if metrics == "all":
        metrics_to_run = list(METRIC_DISPATCHER.keys())
    elif isinstance(metrics, (list, set, tuple)):
        metrics_to_run = list(metrics)
    else:
        metrics_to_run = []

    rows = []
    for metric_name in metrics_to_run:
        if metric_name not in METRIC_DISPATCHER:
            logging.warning(f"Metric '{metric_name}' not found. Skipping.")
            continue

        if metric_name == "searchClass" and search_term is None:
            logging.warning(
                "Skipping 'searchClass': --search-term not provided. "
                "Re-run with --search-term <term> to include this metric."
            )
            rows.append({
                "Metric": metric_name,
                "Score": "N/A",
                "Status": "Skipped (--search-term not provided)",
            })
            continue

        metric_function = METRIC_DISPATCHER[metric_name]
        logging.info(f"--- Running Metric: {metric_name} ---")

        try:
            if metric_name == "searchClass":
                score = metric_function(ttl_file, search_term)
            else:
                score = metric_function(ttl_file)
            logging.info(f"Metric '{metric_name}' completed successfully.")
            rows.append({"Metric": metric_name, "Score": score, "Status": "Success"})
        except Exception as e:
            logging.error(f"Metric '{metric_name}' failed with an error: {e}", exc_info=True)
            rows.append({"Metric": metric_name, "Score": "N/A", "Status": f"Error: {e}"})

    return rows


def _write_csv(results, output_csv_file):
    """Write a list of result row dicts to a CSV file."""
    try:
        with open(output_csv_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["Metric", "Score", "Status"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        logging.info(f"--- Successfully wrote results to {output_csv_file} ---")
    except IOError as e:
        logging.error(f"Failed to write to CSV file {output_csv_file}: {e}")
