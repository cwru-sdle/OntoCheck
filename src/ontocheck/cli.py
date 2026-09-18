"""
OntoCheck Command-Line Interface

Provides a unified CLI for running ontology assessments.  Users select
which metrics to run and, optionally, provide competency questions for
task-based Relevance/Accuracy evaluation.
"""

import argparse
import logging
import sys

from .benchmark import run_suite, write_result
from .run_assessment import METRIC_DISPATCHER, run_assessment

logger = logging.getLogger(__name__)


def _build_parser():
    parser = argparse.ArgumentParser(
        description="OntoCheck: Query-Driven Ontology Assessment.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "ttl_files",
        nargs="+",
        help="Path(s) to input Turtle (.ttl) ontology file(s).\n"
             "Multiple files are merged for assessment.",
    )

    parser.add_argument(
        "--metrics",
        nargs="+",
        help="Task-agnostic metric names to run, or 'all'.\n"
             "Available metrics:\n" + "\n".join(f"  {k}" for k in METRIC_DISPATCHER),
    )

    parser.add_argument(
        "--questions",
        help="Path to a competency-question file (.json or .md)\n"
             "containing SPARQL queries.  When provided, task-based\n"
             "Relevance and Accuracy are computed automatically.",
    )

    parser.add_argument(
        "--domain-prefixes",
        nargs="+",
        help="Namespace prefixes used in the SPARQL queries\n"
             '(e.g., --domain-prefixes mds).  Required with --questions.',
    )

    parser.add_argument(
        "--domain-ns-fragments",
        nargs="+",
        default=None,
        help="Namespace URI fragments to restrict domain-term filtering\n"
             "(e.g., --domain-ns-fragments cwrusdle.bitbucket.io/mds).",
    )

    parser.add_argument(
        "--search-term",
        default=None,
        help="Search string for the 'searchClass' metric.\n"
             "Required when --metrics includes 'searchClass' or 'all'.\n"
             "If omitted, 'searchClass' is skipped with a warning.",
    )

    parser.add_argument(
        "--mds-ontodesigncheck",
        action="store_true",
        default=False,
        help="Run the MDS ontology design check suite:\n"
             "  checkLabel, definitionCheck, semanticConnection,\n"
             "  classCapitalCheck, classSpaceCheck, duplicateLabels.\n"
             "Prepends a summary to the log file.",
    )

    parser.add_argument(
        "--benchmark",
        help="Path to a versioned executable benchmark suite (.json).\n"
             "May be combined with existing assessment options.",
    )

    parser.add_argument(
        "--benchmark-output",
        default="benchmark_results.json",
        help="Path to save benchmark JSON results\n"
             "(default: benchmark_results.json).",
    )

    parser.add_argument(
        "--log-file",
        default="assessment.log",
        help="Path to save the log file (default: assessment.log).",
    )

    parser.add_argument(
        "--csv-file",
        default="assessment_scores.csv",
        help="Path to save the CSV results file\n"
             "(default: assessment_scores.csv).",
    )

    return parser


def _validate_args(args):
    """Validate argument combinations."""
    errors = []

    if (
        not args.metrics
        and not args.questions
        and not args.mds_ontodesigncheck
        and not args.benchmark
    ):
        errors.append(
            "At least one of --metrics, --questions, "
            "--mds-ontodesigncheck, or --benchmark is required."
        )

    if args.questions and not args.domain_prefixes:
        errors.append("--domain-prefixes is required when --questions is provided.")

    if errors:
        print("Error:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)


def _run_benchmark(args):
    """Run a benchmark suite, write its report, and return an exit code."""

    try:
        result = run_suite(args.benchmark, args.ttl_files)
        write_result(result, args.benchmark_output)
    except Exception as error:
        print("Benchmark failed: {}".format(error), file=sys.stderr)
        return 1

    print(
        "Benchmark {!r}: {:.4f}".format(result.suite_id, result.score)
    )
    for case in result.results:
        print(
            "  {}: {} ({:.4f})".format(
                case.case_id, case.status, case.score
            )
        )
    print("Results: {}".format(args.benchmark_output))
    return 1 if any(case.status == "error" for case in result.results) else 0


def main():
    """Entry point for the ``ontocheck`` command."""
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(args)

    metrics = args.metrics
    if metrics and "all" in metrics:
        metrics = list(METRIC_DISPATCHER.keys())

    if metrics or args.questions or args.mds_ontodesigncheck:
        logger.info("--- OntoCheck Assessment ---")
        run_assessment(
            ttl_files=args.ttl_files,
            metrics=metrics,
            questions=args.questions,
            domain_prefixes=args.domain_prefixes,
            domain_ns_fragments=args.domain_ns_fragments,
            search_term=args.search_term,
            mds_design_check=args.mds_ontodesigncheck,
            output_log_file=args.log_file,
            output_csv_file=args.csv_file,
        )

    return _run_benchmark(args) if args.benchmark else 0


if __name__ == "__main__":
    sys.exit(main())
