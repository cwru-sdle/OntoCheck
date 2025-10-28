import argparse
from .run_assessment import run_ontology_assessment, METRIC_DISPATCHER

def main():
    """Defines and orchestrates the command-line interface for the assessment tool.

    This function serves as the main entry point when the script is executed
    from the command line. It uses `argparse` to define and parse command-line
    arguments, provides help text to the user, and handles the special 'all'

    keyword for running all available metrics. It then calls the primary
    `run_ontology_assessment` function with the user-provided arguments.

    Author = "Redad Mehdi"
    """

    parser = argparse.ArgumentParser(
        description="Run ontology assessment metrics on a TTL file.",
        formatter_class=argparse.RawTextHelpFormatter # For better help text formatting
    )

    parser.add_argument(
        "ttl_file",
        help="The full path to the input TTL ontology file."
    )

    parser.add_argument(
        "--metrics",
        nargs="+",
        required=True,
        help="One or more metric names to run, or 'all' to run every metric. \nAvailable metrics: \n" + "\n".join(METRIC_DISPATCHER.keys())
    )

    parser.add_argument(
        "--log-file",
        default="assessment.log",
        help="Path to save the log file (default: assessment.log)."
    )

    parser.add_argument(
        "--csv-file",
        default="assessment_scores.csv",
        help="Path to save the CSV results file (default: assessment_scores.csv)."
    )

    args = parser.parse_args()

    # Logic to handle the 'all' keyword
    metrics_to_run = args.metrics
    if "all" in metrics_to_run:
        metrics_to_run = list(METRIC_DISPATCHER.keys())

    print(f"--- Running assessment via command line ---")
    run_ontology_assessment(
        ttl_file=args.ttl_file,
        metrics=metrics_to_run,
        output_log_file=args.log_file,
        output_csv_file=args.csv_file
    )

if __name__ == "__main__":
    main()
