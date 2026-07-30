"""
Ontology Assessment Runner

Provides a unified ``run_assessment`` entry point that runs any combination
of task-agnostic structural metrics and task-based Relevance/Accuracy
metrics on one or more ontologies.
"""

import csv
import logging
import sys
from pathlib import Path

from .altLabelCheck import mainAltLabelCheck_v_0_0_1
from .check_class_name_capital import mainClassNameCapitalCheck_v_0_0_1
from .check_class_name_space import mainClassNameSpaceCheck_v_0_0_1
from .check_external_data_provider_links_ttl import (
    check_external_data_provider_links_ttl,
)
from .check_for_isolated_elements import check_for_isolated_elements
from .check_human_readable_license_ttl import check_human_readable_license_ttl
from .check_label import mainLabelCheck_v_0_0_1
from .check_rdf_dump_accessibility_ttl import check_rdf_dump_accessibility_ttl
from .check_sparql_accessibility_ttl import check_sparql_accessibility_ttl
from .class_search import mainClassSearch_v_0_0_1
from .count_class_connected_components import count_class_connected_components
from .defCheck import mainDefCheck_v_0_0_1
from .find_duplicate_labels_from_graph import find_duplicate_labels_from_graph
from .get_properties_missing_domain_and_range import (
    get_properties_missing_domain_and_range,
)
from .leafNodeCheck import mainLeafNodeCheck_v_0_0_1
from .mds_design_check import mds_design_check_v_0_0_1
from .semanticConnection import mainSemanticConnection_v_0_0_1
from .spell_check import spell_check_v_0_0_1
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
# Unified assessment runner
# ---------------------------------------------------------------------------

_MDS_DESIGN_CHECK_METRICS = [
    "checkLabel",
    "definitionCheck",
    "semanticConnection",
    "classCapitalCheck",
    "classSpaceCheck",
    "duplicateLabels",
]


def run_assessment(
    ttl_files,
    metrics=None,
    questions=None,
    domain_prefixes=None,
    domain_ns_fragments=None,
    search_term=None,
    mds_design_check=False,
    output_log_file="assessment.log",
    output_csv_file="assessment_scores.csv",
):
    """Run ontology assessment with any combination of metrics.

    Parameters
    ----------
    ttl_files : str, pathlib.Path, or list thereof
        Path(s) to Turtle (.ttl) ontology file(s).  A single path is
        accepted and will be wrapped in a list internally.  When multiple
        files are provided they are merged for the task-based assessment.
    metrics : list of str, ``"all"``, or None
        Task-agnostic metric names to run, or ``"all"`` to run every
        metric in ``METRIC_DISPATCHER``.  May be ``None`` if only
        task-based metrics are desired.
    questions : str, pathlib.Path, list of str, or None
        Competency questions for the task-based assessment.  Accepted
        forms: path to a ``.json`` or ``.md`` file of SPARQL queries,
        or a list of raw SPARQL query strings.  When provided,
        Relevance and Accuracy are computed automatically.
    domain_prefixes : list of str or None
        Namespace prefixes used in the SPARQL queries (e.g.,
        ``["mds"]``).  Required when *questions* is provided.
    domain_ns_fragments : list of str or None, optional
        Namespace URI fragments to restrict domain-term filtering.
    search_term : str or None, optional
        Search string for the ``searchClass`` metric.  When ``None``
        and ``searchClass`` is requested, the metric is skipped with a
        warning.
    mds_design_check : bool, optional
        When ``True``, runs a predefined set of MDS ontology design
        metrics (checkLabel, definitionCheck, semanticConnection,
        classCapitalCheck, classSpaceCheck, duplicateLabels) and
        prepends a summary to the log file.
    output_log_file : str, optional
        Output log file path.
    output_csv_file : str, optional
        Output CSV file path.

    Returns
    -------
    dict or None
        The task-based result dictionary when *questions* is provided,
        otherwise ``None``.
    """
    if isinstance(ttl_files, (str, Path)):
        ttl_files = [ttl_files]

    if mds_design_check:
        metrics = _MDS_DESIGN_CHECK_METRICS

    console = _setup_logging(output_log_file)

    logging.info("--- Starting OntoCheck Assessment ---")
    logging.info(f"Ontologies: {', '.join(str(f) for f in ttl_files)}")

    results = []
    task_result = None

    if questions is not None:
        logging.info("--- Running task-based assessment (Relevance / Accuracy) ---")
        task_result = task_based_metric_v_0_0_1(
            ttl_file=ttl_files,
            questions=questions,
            domain_prefixes=domain_prefixes,
            domain_ns_fragments=domain_ns_fragments,
        )
        _log_task_based_result(task_result)
        results.extend(_task_based_result_to_rows(task_result))

    if metrics is not None:
        logging.info("--- Running task-agnostic metrics ---")
        for f in ttl_files:
            if len(ttl_files) > 1:
                logging.info(f"--- Metrics for: {f} ---")
            results.extend(_run_agnostic_metrics(str(f), metrics, search_term))

    _write_csv(results, output_csv_file)

    logging.info("--- Assessment Complete ---")
    _teardown_logging(console)

    if mds_design_check:
        _prepend_design_check_summary(results, ttl_files, output_log_file)

    return task_result


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


def _prepend_design_check_summary(results, ttl_files, log_file):
    """Build a summary block from metric results and prepend it to the log."""
    lines = [
        "=" * 60,
        "  MDS ONTOLOGY DESIGN CHECK SUMMARY",
        "=" * 60,
        f"  Ontologies: {', '.join(Path(f).name for f in ttl_files)}",
        "-" * 60,
    ]

    for row in results:
        name = row["Metric"]
        status = row["Status"]
        score = row["Score"]
        if status == "Success":
            if score == "" or score is None:
                lines.append(f"  {name:<25s}  PASS")
            else:
                lines.append(f"  {name:<25s}  {score}")
        else:
            lines.append(f"  {name:<25s}  {status}")

    lines.append("-" * 60)

    passed = sum(1 for r in results if r["Status"] == "Success")
    failed = sum(1 for r in results if r["Status"].startswith("Error"))
    skipped = len(results) - passed - failed
    lines.append(f"  Passed: {passed}  |  Failed: {failed}  |  Skipped: {skipped}")
    lines.append("=" * 60)
    lines.append("")

    summary = "\n".join(lines) + "\n"

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            existing = f.read()
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(summary + existing)
    except OSError:
        pass


def _write_csv(results, output_csv_file):
    """Write a list of result row dicts to a CSV file."""
    try:
        with open(output_csv_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["Metric", "Score", "Status"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        logging.info(f"--- Successfully wrote results to {output_csv_file} ---")
    except OSError as e:
        logging.error(f"Failed to write to CSV file {output_csv_file}: {e}")
