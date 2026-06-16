"""
OntoCheck Command-Line Interface

Provides a unified CLI for all four OntoCheck assessment modes:

    Mode 1 -- Task-agnostic (default)
    Mode 2 -- Task-specific Web ontology
    Mode 3 -- Task-based Scientific ontology
    Mode 4 -- Cross-Domain ontology
"""

import sys
import argparse

from .run_assessment import (
    METRIC_DISPATCHER,
    run_ontology_assessment,
    run_task_based_assessment,
    run_web_ontology_assessment,
)


_MODE_HELP = """\
Assessment mode (default: 1).

  1  Task-agnostic     -- Run structural/labeling/accessibility metrics.
                          Requires: --metrics
  2  Task-specific Web -- Validate against KGQA benchmark queries over a
                          knowledge graph (e.g., LC-QuAD / DBpedia).
                          Requires: --questions, --domain-prefixes,
                                    --knowledge-graph
  3  Task-based        -- Assess a domain ontology against competency
                          questions encoded as SPARQL queries.
                          Requires: --questions, --domain-prefixes
  4  Cross-Domain      -- Merge multiple ontologies and assess against
                          cross-domain competency questions.
                          Requires: multiple ttl_files, --questions,
                                    --domain-prefixes
"""


def _build_parser():
    parser = argparse.ArgumentParser(
        description="OntoCheck: Query-Driven Ontology Assessment.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "ttl_files",
        nargs="+",
        help="Path(s) to input Turtle (.ttl) ontology file(s).\n"
             "Mode 4 requires two or more files.",
    )

    parser.add_argument(
        "--mode",
        choices=["1", "2", "3", "4"],
        default="1",
        help=_MODE_HELP,
    )

    parser.add_argument(
        "--metrics",
        nargs="+",
        help="Task-agnostic metric names to run, or 'all'.\n"
             "Required for Mode 1. Optional for Modes 2-4.\n"
             "Available metrics:\n" + "\n".join(f"  {k}" for k in METRIC_DISPATCHER),
    )

    parser.add_argument(
        "--questions",
        help="Path to a competency-question file (.json or .md)\n"
             "containing SPARQL queries. Required for Modes 2, 3, 4.",
    )

    parser.add_argument(
        "--domain-prefixes",
        nargs="+",
        help="Namespace prefixes used in the SPARQL queries\n"
             '(e.g., --domain-prefixes mds). Required for Modes 2, 3, 4.',
    )

    parser.add_argument(
        "--domain-ns-fragments",
        nargs="+",
        default=None,
        help="Namespace URI fragments to restrict domain-term filtering\n"
             "(e.g., --domain-ns-fragments cwrusdle.bitbucket.io/mds).\n"
             "Optional for Modes 2, 3, 4.",
    )

    parser.add_argument(
        "--search-term",
        default=None,
        help="Search string for the 'searchClass' metric.\n"
             "Required when --metrics includes 'searchClass' or 'all'.\n"
             "If omitted, 'searchClass' is skipped with a warning.",
    )

    parser.add_argument(
        "--knowledge-graph",
        default=None,
        help="Path to a knowledge-graph file (Turtle/RDF).\n"
             "Required for Mode 2.",
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
    """Validate that required arguments are present for the selected mode."""
    mode = args.mode
    errors = []

    if mode == "1":
        if not args.metrics:
            errors.append("Mode 1 requires --metrics (metric names or 'all').")

    elif mode == "2":
        if not args.questions:
            errors.append("Mode 2 requires --questions.")
        if not args.domain_prefixes:
            errors.append("Mode 2 requires --domain-prefixes.")
        if not args.knowledge_graph:
            errors.append("Mode 2 requires --knowledge-graph.")

    elif mode == "3":
        if not args.questions:
            errors.append("Mode 3 requires --questions.")
        if not args.domain_prefixes:
            errors.append("Mode 3 requires --domain-prefixes.")

    elif mode == "4":
        if len(args.ttl_files) < 2:
            errors.append("Mode 4 requires two or more ontology files.")
        if not args.questions:
            errors.append("Mode 4 requires --questions.")
        if not args.domain_prefixes:
            errors.append("Mode 4 requires --domain-prefixes.")

    if errors:
        print("Error:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Entry point for the ``ontocheck`` command."""
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(args)

    mode = args.mode

    if mode == "1":
        metrics_to_run = args.metrics
        if "all" in metrics_to_run:
            metrics_to_run = list(METRIC_DISPATCHER.keys())

        print(f"--- Mode 1: Task-agnostic Assessment ---")
        run_ontology_assessment(
            ttl_file=args.ttl_files[0],
            metrics=metrics_to_run,
            search_term=args.search_term,
            output_log_file=args.log_file,
            output_csv_file=args.csv_file,
        )

    elif mode == "2":
        print(f"--- Mode 2: Task-specific Web Ontology Assessment ---")
        run_web_ontology_assessment(
            ttl_file=args.ttl_files[0],
            questions=args.questions,
            domain_prefixes=args.domain_prefixes,
            knowledge_graph=args.knowledge_graph,
            domain_ns_fragments=args.domain_ns_fragments,
            metrics=args.metrics,
            search_term=args.search_term,
            output_log_file=args.log_file,
            output_csv_file=args.csv_file,
        )

    elif mode == "3":
        print(f"--- Mode 3: Task-based Scientific Ontology Assessment ---")
        run_task_based_assessment(
            ttl_files=args.ttl_files[0],
            questions=args.questions,
            domain_prefixes=args.domain_prefixes,
            domain_ns_fragments=args.domain_ns_fragments,
            metrics=args.metrics,
            search_term=args.search_term,
            output_log_file=args.log_file,
            output_csv_file=args.csv_file,
        )

    elif mode == "4":
        print(f"--- Mode 4: Cross-Domain Ontology Assessment ---")
        run_task_based_assessment(
            ttl_files=args.ttl_files,
            questions=args.questions,
            domain_prefixes=args.domain_prefixes,
            domain_ns_fragments=args.domain_ns_fragments,
            metrics=args.metrics,
            search_term=args.search_term,
            output_log_file=args.log_file,
            output_csv_file=args.csv_file,
        )


if __name__ == "__main__":
    main()
