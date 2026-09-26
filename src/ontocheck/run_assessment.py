"""
Ontology Assessment Runner

Provides a unified ``run_assessment`` entry point that runs any combination
of task-agnostic structural metrics, task-based Recall/Precision metrics, and
the OQuaRE / OOPS! / FOOPS! framework metrics on one or more ontologies.

Changelog (v0.0.2)
------------------
- FIXED: ``mds_design_check=True`` silently discarded any user-supplied
  ``metrics``. ``ontocheck onto.ttl --metrics all --mds-ontodesigncheck`` ran
  six metrics rather than all of them, with no warning. The design-check set
  is now unioned with whatever the user asked for, and the CSV records which
  metrics belong to the design-check suite.
- FIXED: metrics that return ``None`` or a dictionary wrote an empty or
  unreadable ``Score`` column. ``_scalarize`` now reduces a returned
  dictionary to a single headline value and preserves the full dictionary in
  the log, so every row carries a usable score.
- ADDED: the OQuaRE, OOPS! and FOOPS! framework metrics, wired in through
  ``framework_metrics.extend_dispatcher`` and selectable with the
  ``frameworks`` argument.
- ADDED: ``allow_network`` and ``has_abox`` so that metrics whose
  requirements cannot be met are skipped with an explanatory status rather
  than failing or recording a misleading zero.
- CHANGED: ``--metrics all`` expands to the original eighteen metrics only.
  The framework metrics are reached through their own flags, so an existing
  invocation behaves exactly as before.
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

# The metric names that existed before the framework metrics were added.
# ``--metrics all`` expands to exactly these, so that an existing invocation
# keeps its original meaning after ``extend_dispatcher`` has run.
CORE_METRIC_NAMES = list(METRIC_DISPATCHER.keys())

from .framework_metrics import (  # noqa: E402
    extend_dispatcher,
    run_framework_metrics,
    summarise_results,
    write_extended_csv,
)

# Registers the OQuaRE, OOPS! and FOOPS! metrics so that they are reachable by
# name through ``--metrics``. Existing entries are never overwritten.
extend_dispatcher(METRIC_DISPATCHER)


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

# Preferred headline key per metric, used by ``_scalarize`` when a metric
# returns a dictionary of several values.
_HEADLINE_KEYS = (
    "connection_ratio",
    "coverage",
    "proportion_isolated_classes",
    "recall",
    "score",
    "ratio",
    "proportion",
)


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
    frameworks=None,
    allow_network=True,
    has_abox=False,
    framework_csv_file="framework_scores.csv",
):
    """Run ontology assessment with any combination of metrics.

    Version: 0.0.2

    Parameters
    ----------
    ttl_files : str, pathlib.Path, or list thereof
        Path(s) to Turtle (.ttl) ontology file(s).  A single path is
        accepted and will be wrapped in a list internally.  When multiple
        files are provided they are merged for the task-based assessment.
    metrics : list of str, ``"all"``, or None
        Task-agnostic metric names to run, or ``"all"`` to run every metric
        that shipped with the package.  ``"all"`` does **not** expand to the
        framework metrics; use *frameworks* or the ``--oops`` / ``--foops`` /
        ``--oquare`` flags for those.  May be ``None`` if only task-based
        metrics are desired.
    questions : str, pathlib.Path, list of str, or None
        Competency questions for the task-based assessment.  Accepted
        forms: path to a ``.json`` or ``.md`` file of SPARQL queries,
        or a list of raw SPARQL query strings.  When provided,
        Recall and Precision are computed automatically.
    domain_prefixes : list of str or None
        Namespace prefixes used in the SPARQL queries (e.g.,
        ``["mds"]``).  Required when *questions* is provided.
    domain_ns_fragments : list of str or None, optional
        Namespace URI fragments to restrict domain-term filtering.  When
        omitted these are now derived from the ontology's own prefix
        bindings; see ``task_based_metric`` for why that matters.
    search_term : str or None, optional
        Search string for the ``searchClass`` metric.  When ``None``
        and ``searchClass`` is requested, the metric is skipped with a
        warning.
    mds_design_check : bool, optional
        When ``True``, adds the predefined set of MDS ontology design
        metrics (checkLabel, definitionCheck, semanticConnection,
        classCapitalCheck, classSpaceCheck, duplicateLabels) to whatever
        *metrics* already requests, and prepends a summary to the log file.

        In version 0.0.1 this **replaced** *metrics* rather than adding to
        it, so ``--metrics all --mds-ontodesigncheck`` silently ran six
        metrics instead of all of them.
    output_log_file : str, optional
        Output log file path.
    output_csv_file : str, optional
        Output CSV file path.
    frameworks : list of str or None, optional
        Framework metric families to run: any of ``"OOPS!"``, ``"FOOPS!"``,
        ``"OQuaRE"``.  ``None`` runs none of them.
    allow_network : bool, optional
        Whether outbound HTTP requests are permitted.  Metrics that require
        the network are skipped with an explanatory status when ``False``.
        Default ``True``.
    has_abox : bool, optional
        Whether the input contains instance data.  Metrics undefined over a
        schema alone, such as OQuaRE ``CROnto``, are skipped when ``False``.
        Default ``False``.
    framework_csv_file : str, optional
        Path for the extended framework results CSV.

    Returns
    -------
    dict or None
        When *frameworks* is falsy, the task-based result dictionary if
        *questions* was provided and ``None`` otherwise -- the version 0.0.1
        contract, so ``result['recall']`` continues to work.

        When *frameworks* is given, a dictionary with ``task_based``,
        ``framework`` and ``framework_summary`` keys.

    Examples
    --------
    >>> run_assessment("onto.ttl", metrics="all")                # doctest: +SKIP
    >>> run_assessment("onto.ttl", frameworks=["OOPS!"])         # doctest: +SKIP
    >>> r = run_assessment("onto.ttl", questions="q.json",
    ...                    domain_prefixes=["mds"])              # doctest: +SKIP
    >>> r["recall"]                                              # doctest: +SKIP
    0.82
    """
    if isinstance(ttl_files, (str, Path)):
        ttl_files = [ttl_files]

    # Union rather than replace: a user who asked for metrics AND the design
    # check should get both. Version 0.0.1 discarded the former.
    design_check_names = []
    if mds_design_check:
        design_check_names = list(_MDS_DESIGN_CHECK_METRICS)
        if metrics == "all":
            pass  # "all" already includes every design-check metric
        elif metrics is None:
            metrics = design_check_names
        else:
            requested = list(metrics)
            merged = requested + [
                m for m in design_check_names if m not in requested
            ]
            if len(merged) != len(requested):
                logging.info(
                    f"--mds-ontodesigncheck added "
                    f"{len(merged) - len(requested)} metric(s) to the "
                    f"{len(requested)} already requested."
                )
            metrics = merged

    console = _setup_logging(output_log_file)

    logging.info("--- Starting OntoCheck Assessment ---")
    logging.info(f"Ontologies: {', '.join(str(f) for f in ttl_files)}")

    results = []
    task_result = None
    framework_results = None

    if questions is not None:
        logging.info("--- Running task-based assessment (Recall / Precision) ---")
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

    if frameworks:
        logging.info(
            "--- Running framework metrics (OQuaRE / OOPS! / FOOPS!) ---"
        )
        framework_results = []
        for f in ttl_files:
            if len(ttl_files) > 1:
                logging.info(f"--- Framework metrics for: {f} ---")
            framework_results.extend(run_framework_metrics(
                str(f),
                frameworks=frameworks,
                allow_network=allow_network,
                has_abox=has_abox,
                questions=questions,
                domain_prefixes=domain_prefixes,
                domain_ns_fragments=domain_ns_fragments,
            ))
        summary = summarise_results(framework_results)
        logging.info(
            f"Framework metrics: {summary['run']} run, "
            f"{summary['passed']} passed, {summary['failed']} failed, "
            f"{summary['skipped']} skipped, "
            f"weighted penalty {summary['weighted_penalty']}"
        )
        for severity, count in sorted(summary["by_severity"].items()):
            logging.info(f"  {severity}: {count} failing check(s)")
        write_extended_csv(framework_results, framework_csv_file)
        results.extend(r.to_row() for r in framework_results)

    _write_csv(results, output_csv_file)

    logging.info("--- Assessment Complete ---")
    _teardown_logging(console)

    if mds_design_check:
        _prepend_design_check_summary(
            results, ttl_files, output_log_file, design_check_names
        )

    if framework_results is not None:
        return {
            "task_based": task_result,
            "framework": framework_results,
            "framework_summary": summarise_results(framework_results),
        }
    return task_result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_task_based_result(result):
    """Log the task-based Recall/Precision results."""
    logging.info(f"Recall:    {result['recall']:.4f}")
    logging.info(f"Precision : {result['precision']:.4f}")
    logging.info(f"Ontology terms  (T_o): {result['T_o_count']}")
    logging.info(f"Task terms      (T_a): {result['T_a_count']}")
    logging.info(f"Intersection:          {result['intersection']}")
    fragments = result.get("domain_ns_fragments_used")
    if fragments:
        logging.info(f"Domain namespace fragments applied: {fragments}")
    else:
        logging.warning(
            "No domain namespace fragments applied; T_o includes every "
            "non-foundational term, which understates Precision."
        )
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
        {"Metric": "Recall", "Score": f"{result['recall']:.4f}", "Status": "Success"},
        {"Metric": "Precision", "Score": f"{result['precision']:.4f}", "Status": "Success"},
        {"Metric": "T_o_count", "Score": result["T_o_count"], "Status": "Success"},
        {"Metric": "T_a_count", "Score": result["T_a_count"], "Status": "Success"},
        {"Metric": "Intersection", "Score": result["intersection"], "Status": "Success"},
    ]


def _scalarize(metric_name, value):
    """
    Reduce a metric's return value to something printable in a CSV cell.

    Definitions
    -----------
    - Scalar pass-through: ``None``, ``bool``, ``int``, ``float`` and ``str``
      are returned unchanged.

    - Dictionary reduction: the first key present from
      :data:`_HEADLINE_KEYS` is used, so that a metric returning several
      values still writes a meaningful score. When no headline key matches,
      the number of entries is written instead and the full dictionary is
      logged.

    - ``None``: rendered as the empty string, as before, but now logged so
      that a silently scoreless metric is visible.

    Version: 0.0.2

    Parameters
    ----------
    metric_name : str
        Name of the metric, for logging.
    value : object
        Whatever the metric returned.

    Returns
    -------
    object
        A value suitable for a CSV cell.
    """
    if value is None:
        logging.debug(
            f"Metric '{metric_name}' returned None; the Score column will be "
            f"empty. Consider returning a value from this metric."
        )
        return ""
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        for key in _HEADLINE_KEYS:
            if key in value:
                logging.info(f"Metric '{metric_name}' full result: {value}")
                return value[key]
        logging.info(f"Metric '{metric_name}' full result: {value}")
        return len(value)
    if isinstance(value, (list, set, tuple)):
        return len(value)
    return str(value)


def _run_agnostic_metrics(ttl_file, metrics, search_term=None):
    """Run task-agnostic metrics and return a list of result row dicts."""
    if metrics == "all":
        # Expands to the metrics that shipped with the package, not to the
        # framework metrics added by extend_dispatcher.
        metrics_to_run = list(CORE_METRIC_NAMES)
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
            rows.append({
                "Metric": metric_name,
                "Score": _scalarize(metric_name, score),
                "Status": "Success",
            })
        except Exception as e:
            logging.error(f"Metric '{metric_name}' failed with an error: {e}", exc_info=True)
            rows.append({"Metric": metric_name, "Score": "N/A", "Status": f"Error: {e}"})

    return rows


def _prepend_design_check_summary(results, ttl_files, log_file,
                                  design_check_names=None):
    """
    Build a summary block from metric results and prepend it to the log.

    Parameters
    ----------
    results : list of dict
        Metric result rows.
    ttl_files : list
        Ontology paths, for the header.
    log_file : str
        Log file to prepend to.
    design_check_names : list of str or None, optional
        The metrics that belong to the design-check suite.  When given, rows
        are marked so that a combined run makes clear which metrics the design
        check contributed.
    """
    design_check_names = set(design_check_names or _MDS_DESIGN_CHECK_METRICS)

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
        marker = " *" if name in design_check_names else "  "
        if status == "Success":
            if score == "" or score is None:
                lines.append(f" {marker}{name:<25s}  PASS")
            else:
                lines.append(f" {marker}{name:<25s}  {score}")
        else:
            lines.append(f" {marker}{name:<25s}  {status}")

    lines.append("-" * 60)
    lines.append("  * = part of the MDS design-check suite")

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
