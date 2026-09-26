"""
OntoCheck Command-Line Interface

Provides a unified CLI for running ontology assessments.  Users select
which metrics to run and, optionally, provide competency questions for
task-based Recall/Precision evaluation.

Changelog (v0.0.2)
------------------
- FIXED: the module docstring and the ``--questions`` help text described the
  task-based metrics as "Relevance and Accuracy", while ``README.md`` and
  ``task_based_metric.py`` call them "Recall and Precision". Three spellings
  for two quantities. Standardised on Recall/Precision throughout, matching
  the README.
- FIXED: ``--metrics all`` now expands from ``CORE_METRIC_NAMES`` rather than
  from the live dispatcher, so it keeps its original meaning after the
  framework metrics have been registered.
- ADDED: ``--oops``, ``--foops``, ``--oquare``, ``--framework-metrics``,
  ``--no-network``, ``--has-abox``, ``--framework-csv`` and
  ``--list-metrics``.
- ADDED: ``--domain-ns-fragments`` now documents that it is derived
  automatically when omitted.
- CHANGED: the "nothing selected" validation accepts an invocation that asks
  only for framework metrics.
"""

import argparse
import logging
import sys

from .framework_metrics import (
    add_cli_arguments,
    print_metric_catalogue,
    resolve_cli_frameworks,
)
from .run_assessment import CORE_METRIC_NAMES, METRIC_DISPATCHER, run_assessment

logger = logging.getLogger(__name__)


def _build_parser():
    parser = argparse.ArgumentParser(
        description="OntoCheck: Query-Driven Ontology Assessment.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "ttl_files",
        nargs="*",
        help="Path(s) to input Turtle (.ttl) ontology file(s).\n"
             "Multiple files are merged for assessment.",
    )

    parser.add_argument(
        "--metrics",
        nargs="+",
        help="Task-agnostic metric names to run, or 'all'.\n"
             "'all' expands to the metrics listed below. The OQuaRE,\n"
             "OOPS! and FOOPS! metrics are selected with their own flags,\n"
             "or by name; run --list-metrics to see them.\n"
             "Available metrics:\n" + "\n".join(f"  {k}" for k in CORE_METRIC_NAMES),
    )

    parser.add_argument(
        "--questions",
        help="Path to a competency-question file (.json or .md)\n"
             "containing SPARQL queries.  When provided, task-based\n"
             "Recall and Precision are computed automatically.",
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
             "(e.g., --domain-ns-fragments cwrusdle.bitbucket.io/mds).\n"
             "When omitted, these are derived from the ontology's own\n"
             "@prefix bindings for --domain-prefixes.  Without a filter,\n"
             "T_o includes stub declarations of imported CCO/BFO terms,\n"
             "which inflates |T_o| and understates Precision.",
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
        help="Add the MDS ontology design check suite:\n"
             "  checkLabel, definitionCheck, semanticConnection,\n"
             "  classCapitalCheck, classSpaceCheck, duplicateLabels.\n"
             "These are added to any --metrics already requested, not\n"
             "substituted for them.  Prepends a summary to the log file.",
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

    add_cli_arguments(parser)

    return parser


def _validate_args(args):
    """Validate argument combinations."""
    errors = []

    framework_requested = any([
        getattr(args, "oops", False),
        getattr(args, "foops", False),
        getattr(args, "oquare", False),
        getattr(args, "framework_metrics", False),
    ])

    if not args.ttl_files:
        errors.append("At least one .ttl file is required.")

    if not any([args.metrics, args.questions, args.mds_ontodesigncheck,
                framework_requested]):
        errors.append(
            "At least one of --metrics, --questions, --mds-ontodesigncheck, "
            "--oops, --foops, --oquare or --framework-metrics is required."
        )

    if args.questions and not args.domain_prefixes:
        errors.append("--domain-prefixes is required when --questions is provided.")

    if errors:
        print("Error:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Entry point for the ``ontocheck`` command."""
    parser = _build_parser()
    args = parser.parse_args()

    # --list-metrics prints the catalogue and exits before any ontology is
    # loaded, so it works without a .ttl argument.
    if getattr(args, "list_metrics", False):
        print_metric_catalogue()
        return

    _validate_args(args)

    metrics = args.metrics
    if metrics and "all" in metrics:
        # Expand from the original metric set, not the extended dispatcher.
        metrics = list(CORE_METRIC_NAMES)

    frameworks = resolve_cli_frameworks(args)

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
        frameworks=frameworks,
        allow_network=not getattr(args, "no_network", False),
        has_abox=getattr(args, "has_abox", False),
        framework_csv_file=getattr(args, "framework_csv", "framework_scores.csv"),
    )


if __name__ == "__main__":
    main()
