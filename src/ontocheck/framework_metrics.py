"""
Integration layer for the OQuaRE, OOPS! and FOOPS! metric families.

Importing this module populates :data:`~ontocheck.metric_registry.
METRIC_REGISTRY` with every framework-derived metric and exposes them to the
existing ``run_assessment`` code path without changing how the original
eighteen OntoCheck metrics behave.

Integration contract
--------------------
``run_assessment._run_agnostic_metrics`` calls ``metric_function(ttl_file)``
and writes the return value straight into the ``Score`` column.  Framework
metrics return a :class:`~ontocheck.metric_registry.MetricResult` instead of a
bare score, so :func:`extend_dispatcher` wraps each one in a shim that returns
``MetricResult.score``.  Existing CSV consumers therefore see a scalar exactly
as before, while :func:`run_framework_metrics` gives access to the full
structured result.

Usage
-----
In ``run_assessment.py``, after the existing ``METRIC_DISPATCHER`` literal::

    from .framework_metrics import extend_dispatcher
    extend_dispatcher(METRIC_DISPATCHER)

That single call adds every framework metric to ``--metrics`` and to
``--metrics all``.  In ``cli.py``, add the family flags described by
:func:`add_cli_arguments`.

Version: 0.0.1

.. note::

   Claude AI (Opus 5) was employed chiefly to support documentation efforts.
"""

import csv
import logging

# Importing these modules is what registers their metrics.
from . import foops_metadata_checks  # noqa: F401
from . import foops_version_checks  # noqa: F401
from . import oops_structural_checks  # noqa: F401
from . import oops_lexical_checks  # noqa: F401
from . import oops_axiom_checks  # noqa: F401
from . import foops_access_checks  # noqa: F401
from . import oquare_metrics  # noqa: F401
from .metric_registry import (
    METRIC_REGISTRY,
    Category,
    MetricResult,
    Severity,
    SourceFramework,
    metrics_by_category,
    metrics_by_framework,
    skip_reason,
    summarise_registry,
)

logger = logging.getLogger(__name__)


# Weights used when aggregating OOPS! pitfalls into a single penalty score.
# Derived from the OOPS! importance levels, which the catalogue publishes but
# does not assign numeric weights to; these are OntoCheck's convention and are
# stated here so that any reported aggregate is reproducible.
SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 5.0,
    Severity.IMPORTANT: 3.0,
    Severity.MINOR: 1.0,
    Severity.INFO: 0.0,
}


def extend_dispatcher(dispatcher):
    """
    Add every registered framework metric to an existing flat dispatcher.

    Version: 0.0.1

    Parameters
    ----------
    dispatcher : dict
        The existing ``METRIC_DISPATCHER``, mapping metric name to callable.
        Modified in place.

    Returns
    -------
    dict
        The same dictionary, for chaining.

    Notes
    -----
    Each framework metric is wrapped so that it returns
    ``MetricResult.score`` rather than the result object, which preserves the
    three-column CSV schema written by ``run_assessment._write_csv``.  A
    metric that could not run returns its status string, so a skipped metric
    is distinguishable from one that scored zero.

    Existing dispatcher entries are never overwritten.  A name collision is
    logged and the original implementation is kept.

    Examples
    --------
    >>> from ontocheck.run_assessment import METRIC_DISPATCHER  # doctest: +SKIP
    >>> extend_dispatcher(METRIC_DISPATCHER)                    # doctest: +SKIP
    """
    for metric_id, descriptor in METRIC_REGISTRY.items():
        if metric_id in dispatcher:
            logger.warning(
                f"Metric '{metric_id}' already present in the dispatcher; "
                f"keeping the existing implementation."
            )
            continue
        dispatcher[metric_id] = _make_shim(descriptor)
    return dispatcher


def _make_shim(descriptor):
    """
    Wrap a framework metric so that it returns a scalar score.

    Parameters
    ----------
    descriptor : MetricDescriptor
        Metric to wrap.

    Returns
    -------
    callable
        A function of ``ttl_file`` returning the metric's scalar score, or its
        status string when the metric could not be computed.

    Notes
    -----
    The shim enforces the descriptor's execution requirements before calling
    the implementation.  The legacy dispatcher has no way to declare whether
    instance data is present, so ``has_abox=False`` is assumed, matching the
    TBox-only design of the original package.  Without this check a metric
    such as OQuaRE ``CROnto`` would run over a schema-only file and record a
    value of 0.0, which reads as "no instances per class" when the truth is
    "this metric is not applicable here".  Network access is assumed to be
    permitted, matching the existing ``sparqlEndpoint``, ``rdfDump`` and
    ``externalLinks`` metrics, which make HTTP requests unconditionally.

    Callers that do have instance data should use
    :func:`run_framework_metrics` with ``has_abox=True`` rather than the
    dispatcher.
    """
    def shim(ttl_file, *args, **kwargs):
        reason = skip_reason(descriptor, allow_network=True, has_abox=False,
                             has_reasoner=False)
        if reason:
            logger.info(f"Metric '{descriptor.metric_id}': {reason}")
            return reason
        result = descriptor.function(ttl_file, *args, **kwargs)
        if not isinstance(result, MetricResult):
            return result
        if result.status != "Success":
            return result.status
        return result.score

    shim.__name__ = descriptor.function.__name__
    shim.__doc__ = descriptor.function.__doc__
    return shim


def run_framework_metrics(ttl_file, frameworks=None, categories=None,
                          metrics=None, allow_network=True, has_abox=False,
                          has_reasoner=False, questions=None,
                          domain_prefixes=None, domain_ns_fragments=None):
    """
    Run framework metrics and return their structured results.

    Version: 0.0.2

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file to assess.
    frameworks : list of SourceFramework or str, or None, optional
        Restrict to these frameworks, e.g. ``["OOPS!"]``.  ``None`` runs all.
    categories : list of Category or str, or None, optional
        Restrict to these categories, e.g. ``["provenance"]``.
    metrics : list of str or None, optional
        Restrict to these metric identifiers.  Takes precedence over
        *frameworks* and *categories*.
    allow_network : bool, optional
        Whether outbound HTTP is permitted.  Default ``True``.
    has_abox : bool, optional
        Whether instance data is present.  Default ``False``.
    has_reasoner : bool, optional
        Whether a DL reasoner is available.  Default ``False``.
    questions : str, pathlib.Path, list of str, or None, optional
        Competency questions, in any form accepted by
        ``task_based_metric_v_0_0_1``.  Passed to metrics that declare
        ``requires_questions`` (OOPS! P09); those metrics are skipped when
        this is ``None``.
    domain_prefixes : list of str or None, optional
        SPARQL prefixes that mark domain terms in *questions*.
    domain_ns_fragments : list of str or None, optional
        Namespace fragments restricting the ontology's domain terms.

    Returns
    -------
    list of MetricResult
        One result per selected metric, in sorted identifier order.  Metrics
        whose requirements are unmet are included with an explanatory
        ``status`` rather than omitted, so that a run's coverage is visible.

    Examples
    --------
    >>> results = run_framework_metrics(                      # doctest: +SKIP
    ...     "ontology.ttl", frameworks=["OOPS!"], allow_network=False
    ... )
    >>> sum(1 for r in results if r.passed is False)          # doctest: +SKIP
    9
    """
    selected = _select_metrics(frameworks, categories, metrics)
    results = []

    for metric_id in selected:
        descriptor = METRIC_REGISTRY[metric_id]
        reason = skip_reason(descriptor, allow_network, has_abox, has_reasoner,
                             has_questions=bool(questions))
        if reason:
            results.append(MetricResult(
                metric_id=metric_id,
                status=reason,
                message=f"{descriptor.provenance}: {reason}",
            ))
            continue
        try:
            if descriptor.requires_questions:
                results.append(descriptor.function(
                    ttl_file,
                    questions=questions,
                    domain_prefixes=domain_prefixes,
                    domain_ns_fragments=domain_ns_fragments,
                ))
            else:
                results.append(descriptor.function(ttl_file))
        except Exception as e:
            logger.error(
                f"Metric '{metric_id}' failed with an error: {e}", exc_info=True
            )
            results.append(MetricResult(
                metric_id=metric_id,
                status=f"Error: {e}",
                message=f"{descriptor.provenance}: failed",
            ))

    return results


def _select_metrics(frameworks, categories, metrics):
    """
    Resolve a metric selection to a sorted list of identifiers.

    Parameters
    ----------
    frameworks : list or None
        Framework names or :class:`SourceFramework` members.
    categories : list or None
        Category names or :class:`Category` members.
    metrics : list or None
        Explicit metric identifiers.

    Returns
    -------
    list of str
        Sorted, de-duplicated metric identifiers.
    """
    if metrics:
        return sorted(m for m in metrics if m in METRIC_REGISTRY)

    selected = set()
    if frameworks:
        for f in frameworks:
            member = f if isinstance(f, SourceFramework) else _coerce(
                SourceFramework, f
            )
            if member:
                selected.update(metrics_by_framework(member))
    if categories:
        for c in categories:
            member = c if isinstance(c, Category) else _coerce(Category, c)
            if member:
                selected.update(metrics_by_category(member))

    return sorted(selected) if selected else sorted(METRIC_REGISTRY)


def _coerce(enum_cls, value):
    """
    Resolve a string to an enum member by value or by name, case-insensitively.

    Parameters
    ----------
    enum_cls : type
        The enum class.
    value : str
        Value or member name.

    Returns
    -------
    enum member or None
    """
    text = str(value).strip().lower()
    for member in enum_cls:
        if member.value.lower() == text or member.name.lower() == text:
            return member
    logger.warning(f"Unrecognised {enum_cls.__name__}: {value!r}")
    return None


def summarise_results(results):
    """
    Summarise a set of framework results by framework and severity.

    Version: 0.0.1

    Parameters
    ----------
    results : list of MetricResult
        Results as returned by :func:`run_framework_metrics`.

    Returns
    -------
    dict
        Keys: ``total``, ``run``, ``skipped``, ``errored``, ``passed``,
        ``failed``, ``by_framework``, ``by_severity``, and
        ``weighted_penalty``.

    Notes
    -----
    ``weighted_penalty`` sums :data:`SEVERITY_WEIGHTS` over failing pass/fail
    checks.  It is a convenience for ranking ontologies within one study, not
    a calibrated quality score.  OQuaRE measurement metrics carry severity
    ``INFO`` and weight 0, so they never contribute.

    Examples
    --------
    >>> summarise_results(results)["weighted_penalty"]   # doctest: +SKIP
    41.0
    """
    by_framework, by_severity = {}, {}
    run = skipped = errored = passed = failed = 0
    penalty = 0.0

    for result in results:
        descriptor = METRIC_REGISTRY.get(result.metric_id)
        framework = descriptor.source_framework.value if descriptor else "?"
        bucket = by_framework.setdefault(
            framework, {"passed": 0, "failed": 0, "skipped": 0, "errored": 0}
        )

        if result.status.startswith("Skipped"):
            skipped += 1
            bucket["skipped"] += 1
            continue
        if result.status.startswith("Error"):
            errored += 1
            bucket["errored"] += 1
            continue

        run += 1
        if result.passed is True:
            passed += 1
            bucket["passed"] += 1
        elif result.passed is False:
            failed += 1
            bucket["failed"] += 1
            if descriptor:
                severity = descriptor.severity
                by_severity[severity.value] = by_severity.get(
                    severity.value, 0
                ) + 1
                penalty += SEVERITY_WEIGHTS.get(severity, 0.0)

    return {
        "total": len(results),
        "run": run,
        "skipped": skipped,
        "errored": errored,
        "passed": passed,
        "failed": failed,
        "by_framework": by_framework,
        "by_severity": by_severity,
        "weighted_penalty": round(penalty, 2),
    }


def write_extended_csv(results, output_csv_file):
    """
    Write framework results to an extended CSV.

    Version: 0.0.1

    Parameters
    ----------
    results : list of MetricResult
        Results to write.
    output_csv_file : str or pathlib.Path
        Destination path.

    Returns
    -------
    bool
        ``True`` on success, ``False`` when the file could not be written.

    Notes
    -----
    The extended schema adds ``Framework``, ``SourceID``, ``Severity``,
    ``Passed``, ``Affected``, ``TotalExamined`` and ``Message`` alongside the
    original ``Metric``, ``Score`` and ``Status`` columns, so results can be
    reported against the source catalogue item.  The original
    ``assessment_scores.csv`` schema is unchanged and is still written by
    ``run_assessment``.
    """
    fieldnames = [
        "Metric", "Framework", "SourceID", "Severity", "Score", "Passed",
        "Affected", "TotalExamined", "Message", "Status",
    ]
    try:
        with open(output_csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                descriptor = METRIC_REGISTRY.get(result.metric_id)
                row = result.to_extended_row()
                row["Framework"] = (
                    descriptor.source_framework.value if descriptor else ""
                )
                row["SourceID"] = descriptor.source_id if descriptor else ""
                row["Severity"] = (
                    descriptor.severity.value if descriptor else ""
                )
                writer.writerow(row)
        logger.info(f"--- Wrote framework results to {output_csv_file} ---")
        return True
    except OSError as e:
        logger.error(f"Failed to write {output_csv_file}: {e}")
        return False


def add_cli_arguments(parser):
    """
    Add framework-selection flags to the OntoCheck argument parser.

    Version: 0.0.1

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The parser built by ``cli._build_parser``.

    Returns
    -------
    argparse.ArgumentParser
        The same parser, for chaining.

    Notes
    -----
    Adds ``--oops``, ``--foops``, ``--oquare``, ``--framework-metrics``,
    ``--no-network``, ``--has-abox``, ``--framework-csv`` and
    ``--list-metrics``.  All are additive; existing flags keep their meaning,
    and an invocation that uses none of them behaves exactly as before.
    """
    group = parser.add_argument_group("framework metrics")
    group.add_argument(
        "--oops", action="store_true", default=False,
        help="Run the OOPS! pitfall checks.",
    )
    group.add_argument(
        "--foops", action="store_true", default=False,
        help="Run the FOOPS! FAIR tests.",
    )
    group.add_argument(
        "--oquare", action="store_true", default=False,
        help="Run the OQuaRE structural quality metrics.",
    )
    group.add_argument(
        "--framework-metrics", action="store_true", default=False,
        help="Run every OOPS!, FOOPS! and OQuaRE metric.",
    )
    group.add_argument(
        "--no-network", action="store_true", default=False,
        help="Skip metrics that require outbound HTTP requests.",
    )
    group.add_argument(
        "--has-abox", action="store_true", default=False,
        help="Declare that the input contains instance data, enabling\n"
             "metrics such as OQuaRE CROnto that are undefined over a\n"
             "schema alone.",
    )
    group.add_argument(
        "--framework-csv", default="framework_scores.csv",
        help="Path for the extended framework results CSV\n"
             "(default: framework_scores.csv).",
    )
    group.add_argument(
        "--list-metrics", action="store_true", default=False,
        help="Print every registered metric with its source catalogue\n"
             "item, then exit.",
    )
    return parser


def resolve_cli_frameworks(args):
    """
    Translate parsed CLI flags into a framework selection.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    list of SourceFramework or None
        The selected frameworks, or ``None`` when no framework flag was given.
    """
    if getattr(args, "framework_metrics", False):
        return [SourceFramework.OOPS, SourceFramework.FOOPS,
                SourceFramework.OQUARE]
    selected = []
    if getattr(args, "oops", False):
        selected.append(SourceFramework.OOPS)
    if getattr(args, "foops", False):
        selected.append(SourceFramework.FOOPS)
    if getattr(args, "oquare", False):
        selected.append(SourceFramework.OQUARE)
    return selected or None


def print_metric_catalogue():
    """
    Print every registered metric with its provenance.

    Implements ``--list-metrics``.  Output is grouped by framework and gives
    each metric's identifier, source catalogue item, severity and execution
    requirements, so a user can see what a run will and will not cover.

    Returns
    -------
    None
    """
    summary = summarise_registry()
    print(f"OntoCheck registered metrics: {summary['total']}")
    for framework, count in sorted(summary["by_framework"].items()):
        print(f"  {framework}: {count}")
    print()

    for framework in SourceFramework:
        ids = metrics_by_framework(framework)
        if not ids:
            continue
        print(f"--- {framework.value} ({len(ids)}) ---")
        for metric_id in ids:
            d = METRIC_REGISTRY[metric_id]
            requirements = []
            if d.requires_network:
                requirements.append("network")
            if d.requires_abox:
                requirements.append("abox")
            if d.requires_reasoner:
                requirements.append("reasoner")
            if d.requires_questions:
                requirements.append("questions")
            suffix = f"  [{', '.join(requirements)}]" if requirements else ""
            fair = f" FAIR:{d.fair_principle}" if d.fair_principle else ""
            print(
                f"  {metric_id:<34} {d.source_id:<10} "
                f"{d.severity.value:<10}{fair}{suffix}"
            )
            print(f"  {'':<34} {d.description}")
        print()


# ---------------------------------------------------------------------------
# One-call report over all three frameworks
# ---------------------------------------------------------------------------

_FRAMEWORK_ORDER = ("OOPS!", "FOOPS!", "OQuaRE")
_FOOPS_ORDER = ("CN1", "DOC1", "FIND1", "FIND2", "FIND3", "FIND_3_BIS", "HTTP1",
                "OM1", "OM2", "OM3", "OM4.1", "OM4.2", "OM5.1", "OM5.2", "PURL1",
                "RDF1", "URI1", "URI2", "VER1", "VER2", "VOC1", "VOC2", "VOC3",
                "VOC4")


def _report_sort_key(metric_id):
    """
    Sort key placing metrics in catalogue order within each framework.

    Parameters
    ----------
    metric_id : str
        Registry identifier.

    Returns
    -------
    tuple
        ``(framework position, position within the framework's catalogue)``.
    """
    d = METRIC_REGISTRY[metric_id]
    fw = _FRAMEWORK_ORDER.index(d.source_framework.value) \
        if d.source_framework.value in _FRAMEWORK_ORDER else len(_FRAMEWORK_ORDER)
    sid = d.source_id.replace("-T", "")
    pos = _FOOPS_ORDER.index(sid) if sid in _FOOPS_ORDER else sid
    return (fw, f"{pos:03d}" if isinstance(pos, int) else pos)


def _short(term):
    """
    Return a compact form of an affected element for display.

    Parameters
    ----------
    term : object
        Usually an IRI string.

    Returns
    -------
    str
        The local name of an IRI (text after the last ``#`` or ``/``), or the
        string form of anything else.
    """
    s = str(term)
    for sep in ("#", "/"):
        if sep in s.rstrip(sep):
            s = s.rstrip(sep).rsplit(sep, 1)[-1]
    return s


def framework_report(ttl_file, frameworks=None, allow_network=True, has_abox=None,
                     has_reasoner=False, questions=None, domain_prefixes=None,
                     domain_ns_fragments=None, max_examples=3, output_csv=None,
                     split=True):
    """
    Run the OOPS!, FOOPS! and OQuaRE metrics and return a readable table.

    One row per metric, in catalogue order, with the metric's name, what it
    measures, its score, its outcome and -- when it did not pass -- the
    reason, including a few of the affected elements.  By default the rows
    are returned as three tables, one per framework.

    Definitions
    -----------
    - result: ``"pass"`` or ``"fail"`` for OOPS! and FOOPS! checks;
      ``"grade k/5"`` for OQuaRE metrics, using the static scale;
      ``"skipped"`` when a requirement (network, instance data, competency
      questions) is unmet; ``"error"`` when the metric raised.

    - reason: empty for passing checks.  Otherwise the metric's own message,
      followed by up to *max_examples* affected elements, or the skip/error
      status.  For OQuaRE metrics it states how the value was computed.

    Source
    ------
    OntoCheck (SDLE Research Center, Case Western Reserve University).
    Metric definitions: OOPS! (https://oops.linkeddata.es/catalogue.jsp),
    FOOPS! (https://w3id.org/foops/catalog), OQuaRE (Duque-Ramos et al.
    2011, 2016).

    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str or pathlib.Path
        Path to the ontology Turtle (.ttl) file.
    frameworks : list of str or None, optional
        Restrict to some of ``"OOPS!"``, ``"FOOPS!"``, ``"OQuaRE"``.
        ``None`` runs all three (83 metrics).
    allow_network : bool, optional
        Whether network tests may make HTTP requests.  Default ``True``.
    has_abox : bool or None, optional
        Whether the file contains instance data.  ``None`` (default) detects
        it: individuals that are not also declared as classes or properties.
    has_reasoner : bool, optional
        Passed through to the registry's requirement check.  No metric
        currently requires it; OOPS! P31 uses HermiT when available.
    questions : str, pathlib.Path, list of str, or None, optional
        Competency questions for OOPS! P09.  Skipped when ``None``.
    domain_prefixes : list of str or None, optional
        SPARQL prefixes marking domain terms in *questions*.
    domain_ns_fragments : list of str or None, optional
        Namespace fragments restricting the ontology's domain terms.
    max_examples : int, optional
        Number of affected elements quoted in ``reason``.  Default 3.
    output_csv : str or pathlib.Path or None, optional
        When given, the results are also written to CSV.  With
        ``split=True`` one file per framework is written, named
        ``<stem>_OOPS.csv``, ``<stem>_FOOPS.csv`` and ``<stem>_OQuaRE.csv``.
    split : bool, optional
        ``True`` (default) returns one table per framework; ``False``
        returns a single table with the framework in the ``metric`` column.

    Returns
    -------
    dict of str to pandas.DataFrame, or pandas.DataFrame
        With ``split=True``: ``{"OOPS!": df, "FOOPS!": df, "OQuaRE": df}``,
        containing only the frameworks that were run.  Each table has
        columns ``metric``, ``description``, ``score``, ``result`` and
        ``reason`` and is indexed by registry identifier.  With
        ``split=False``: one such table for all metrics.  In both cases the
        full :class:`~ontocheck.metric_registry.MetricResult` objects are
        available as ``df.attrs["results"]`` (a dict keyed by identifier)
        for drilling into ``affected`` and ``detail``.

    Output Information
    ------------------
    - One row per metric; nothing is printed.

    Error Handling
    --------------
    - A metric that raises is reported with ``result == "error"`` and the
      exception in ``reason``; the remaining metrics still run.
    - ``ImportError`` is raised if pandas is not installed.

    Examples
    --------
    >>> tables = framework_report("XRD.ttl", allow_network=False)  # doctest: +SKIP
    >>> tables["OOPS!"][tables["OOPS!"].result == "fail"]          # doctest: +SKIP
    >>> tables["OQuaRE"]                                           # doctest: +SKIP
    >>> r = tables["OOPS!"].attrs["results"]["oopsP08MissingAnnotations"]  # doctest: +SKIP
    >>> r.affected                                                 # doctest: +SKIP
    """
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError("framework_report requires pandas "
                          "(pip install pandas)") from e

    if has_abox is None:
        from rdflib import Graph
        from .helpers.semantic_helpers import _individuals
        g = Graph()
        g.parse(str(ttl_file), format="turtle")
        has_abox = bool(_individuals(g))

    results = run_framework_metrics(
        str(ttl_file), frameworks=frameworks, allow_network=allow_network,
        has_abox=has_abox, has_reasoner=has_reasoner, questions=questions,
        domain_prefixes=domain_prefixes if questions else None,
        domain_ns_fragments=domain_ns_fragments,
    )
    by_id = {r.metric_id: r for r in results}

    rows = []
    for mid in sorted(by_id, key=_report_sort_key):
        r, d = by_id[mid], METRIC_REGISTRY[mid]
        sid = d.source_id.replace("-T", "")
        grade = (r.detail or {}).get("static_scale")
        if r.status.startswith("Skipped"):
            result, reason = "skipped", r.status
        elif r.status.startswith("Error"):
            result, reason = "error", r.status
        elif d.source_framework == SourceFramework.OQUARE:
            result = f"grade {grade}/5" if grade is not None else "scored"
            reason = r.message
        elif r.passed:
            result, reason = "pass", ""
        else:
            result = "fail"
            named = [a for a in (r.affected or []) if not str(a).startswith("<")]
            examples = [_short(a) for a in named[:max_examples]]
            more = len(named) - len(examples)
            reason = r.message
            if examples and not any(e in reason for e in examples):
                reason += "; e.g. " + ", ".join(examples) + \
                    (f" (+{more} more)" if more > 0 else "")
        rows.append({
            "metric_id": mid,
            "framework": d.source_framework.value,
            "metric": (f"{sid} - {d.name}" if split
                       else f"{d.source_framework.value} {sid} - {d.name}"),
            "description": d.description,
            "score": r.score,
            "result": result,
            "reason": reason,
        })

    df = pd.DataFrame(rows).set_index("metric_id")

    if not split:
        df = df.drop(columns="framework")
        df.attrs["results"] = by_id
        df.attrs["ontology"] = str(ttl_file)
        if output_csv:
            df.to_csv(output_csv)
        return df

    from pathlib import Path
    tables = {}
    for fw in _FRAMEWORK_ORDER:
        part = df[df["framework"] == fw].drop(columns="framework")
        if part.empty:
            continue
        part.attrs["results"] = {k: by_id[k] for k in part.index}
        part.attrs["ontology"] = str(ttl_file)
        tables[fw] = part
        if output_csv:
            out = Path(output_csv)
            part.to_csv(out.with_name(f"{out.stem}_{fw.rstrip('!')}{out.suffix or '.csv'}"))
    return tables