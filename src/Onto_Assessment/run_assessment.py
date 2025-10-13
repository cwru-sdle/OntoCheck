import logging
import sys
import csv

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
}

def run_ontology_assessment(
    ttl_file,
    metrics,
    output_log_file="assessment.log",
    output_csv_file="assessment_scores.csv"
):
    """Runs ontology assessment metrics on a given TTL file.

    Args:
        ttl_file (str): Path to the input Turtle (.ttl) ontology file.
        metrics (list[str] | str): List of metric names to execute, or "all"
            to run every available metric in METRIC_DISPATCHER.
        output_log_file (str, optional): Output log file path. Defaults to "assessment.log".
        output_csv_file (str, optional): Output CSV file path. Defaults to "assessment_scores.csv".
    """
    logging.basicConfig(
        filename=output_log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="w"
    )
    console_handler = logging.StreamHandler(sys.stdout)
    logging.getLogger().addHandler(console_handler)

    # 🔹 Handle "all" keyword
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

        metric_function = METRIC_DISPATCHER[metric_name]
        logging.info(f"--- Running Metric: {metric_name} ---")

        try:
            score = metric_function(ttl_file)
            logging.info(f"Metric '{metric_name}' completed successfully.")
            results.append({"Metric": metric_name, "Score": score, "Status": "Success"})
        except Exception as e:
            logging.error(f"Metric '{metric_name}' failed with an error: {e}", exc_info=True)
            results.append({"Metric": metric_name, "Score": "N/A", "Status": f"Error: {e}"})

    try:
        with open(output_csv_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["Metric", "Score", "Status"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        logging.info(f"--- Successfully wrote results to {output_csv_file} ---")
    except IOError as e:
        logging.error(f"Failed to write to CSV file {output_csv_file}: {e}")

    logging.info("--- Assessment Complete ---")
    logging.getLogger().removeHandler(console_handler)
