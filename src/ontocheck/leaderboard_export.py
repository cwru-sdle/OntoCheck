"""
Export OntoCheck results for the benchmark leaderboard.

Runs every metric on a set of domains and writes one JSON file with four
tables per domain:

* ``oops``, ``foops`` and ``oquare`` -- each framework metric with its
  original score and its unweighted and context-weighted values (see
  :mod:`ontocheck.context_weighting`);
* ``ontocheck`` -- OntoCheck's own metrics, task-based Recall and Precision,
  conceptual fitness, structural fitness and counterfactual concept
  importance (see :mod:`ontocheck.query_fitness`), and the benchmark suite's
  RAG score and answer scores.

Every row carries a ``level`` of the fitness profile: ``0`` for metrics of
the ontology alone, ``I`` conceptual, ``II-A`` structural, ``II-B`` logical
and ``IV`` RAG.  Level III (retrieval and reasoning) comes from the
leaderboard's planner, not from this export.  Each domain also lists the
queries and benchmark cases behind its Level I, II and IV values, with each
query's own scores.

A domain is one or more Turtle files, merged before scoring, with optional
competency questions (enabling Recall/Precision, the fitness metrics and
query weighting) and an optional benchmark suite (enabling counterfactual
importance).

Domains come from a manifest::

    {"domains": [
        {"name": "XRD", "files": ["Ontologies/XRD.ttl"],
         "questions": "SPARQL_Queries/XRD.json",
         "benchmark": "Benchmarks/XRD-graph-path.json",
         "domain_prefixes": ["mds"]}
    ]}

Paths are relative to the manifest.  Or one domain is given on the command
line::

    ontocheck-leaderboard --manifest SupplementaryMaterials/leaderboard-domains.json \\
        --out ontocheck-results.json
    ontocheck-leaderboard --name XRD --ontology XRD.ttl --questions XRD.json \\
        --domain-prefixes mds --out ontocheck-results.json --update

With ``--update`` the named domains replace their entries in an existing
output file and every other entry is kept.

Version: 0.0.4
"""

import argparse
import contextlib
import io
import json
import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from rdflib import Graph

logger = logging.getLogger(__name__)

SCHEMA = "ontocheck-leaderboard/1"

_FRAMEWORK_TABLES = (("oops", "OOPS!"), ("foops", "FOOPS!"), ("oquare", "OQuaRE"))

# Native metrics that need the network, and one that needs a search term.
_NETWORK_METRICS = {"externalLinks", "rdfDump", "sparqlEndpoint"}
_NATIVE_SKIP = {"searchClass"}

_NATIVE_NAMES = {
    "altLabelCheck": "Synonym (altLabel) coverage",
    "externalLinks": "External link validity",
    "rdfDump": "RDF dump availability",
    "sparqlEndpoint": "SPARQL endpoint availability",
    "classConnections": "Disconnected class subgraphs",
    "leafNodeCheck": "Leaf classes",
    "semanticConnection": "Upper-ontology grounding",
    "mdsDesignCheck": "MDS design predicates (share of classes)",
    "spellCheck": "Spelling (error rate)",
    "classCapitalCheck": "Class names capitalised",
    "classSpaceCheck": "Class names with spaces",
}


def _number(value):
    """A JSON-safe scalar: floats rounded, other non-scalars as strings."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    return str(value)


@contextlib.contextmanager
def _quiet():
    """Silence logging and stdout from metrics that print their analysis."""
    root = logging.getLogger()
    previous = root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        logging.disable(previous)


def _merge(files, directory):
    """Merge Turtle files into one, keeping their prefix bindings."""
    files = [Path(f) for f in files]
    if len(files) == 1:
        return files[0]
    g = Graph()
    for f in files:
        part = Graph().parse(str(f), format="turtle")
        for prefix, ns in part.namespaces():
            g.bind(prefix, ns, override=False)
        g += part
    merged = Path(directory) / "merged.ttl"
    g.serialize(str(merged), format="turtle")
    return merged


def _framework_tables(ttl, questions, domain_prefixes, allow_network, has_abox):
    from .context_weighting import build_context, normalize_results
    from .framework_metrics import SEVERITY_WEIGHTS, run_framework_metrics
    from .metric_registry import METRIC_REGISTRY

    results = run_framework_metrics(
        str(ttl), frameworks=[fw for _, fw in _FRAMEWORK_TABLES],
        allow_network=allow_network, has_abox=has_abox, questions=questions,
        domain_prefixes=domain_prefixes,
    )
    weighted = None
    if questions is not None or has_abox:
        ctx = build_context(str(ttl), questions, use_instances="auto")
        weighted = {n.metric_id: n for n in normalize_results(results, ctx)}

    tables = {key: {"rows": []} for key, _ in _FRAMEWORK_TABLES}
    framework_of = {fw: key for key, fw in _FRAMEWORK_TABLES}
    for r in results:
        d = METRIC_REGISTRY[r.metric_id]
        key = framework_of.get(d.source_framework.value)
        if key is None:
            continue
        n = weighted.get(r.metric_id) if weighted else None
        row = {
            "id": r.metric_id,
            "level": "0",
            "source_id": d.source_id.replace("-T", ""),
            "name": d.name,
            "description": d.description,
            "severity": d.severity.value,
            "fair_principle": d.fair_principle,
            "status": r.status,
            "original": _number(r.score),
            "passed": r.passed,
            "unweighted": _number(n.unweighted_score) if n else None,
            "weighted": _number(n.display_weighted) if n else None,
            "weighting": None if n is None else (
                "weighted" if n.normalizable else
                "not applicable" if n.scope in ("ontology", "query") else
                "not run" if n.scope == "not run" else "not decomposable"),
            "passed_in_context": n.passed_in_context if n else None,
            "message": r.message,
        }
        if key == "oquare":
            row["grade"] = (r.detail or {}).get("static_scale")
            row["weighted_grade"] = (n.detail or {}).get(
                "weighted_static_scale") if n else None
        tables[key]["rows"].append(row)

    for key, table in tables.items():
        rows = [x for x in table["rows"] if x["status"] == "Success"]
        if key == "oquare":
            grades = [x["grade"] for x in rows if x.get("grade") is not None]
            wgrades = [x["weighted_grade"] for x in rows
                       if x.get("weighted_grade") is not None]
            table["summary"] = {
                "metrics_run": len(rows),
                "mean_grade": _number(sum(grades) / len(grades)) if grades else None,
                "mean_weighted_grade": _number(sum(wgrades) / len(wgrades))
                if wgrades else None,
            }
            continue
        failed = [x for x in rows if x["passed"] is False]
        failed_ctx = [x for x in failed if x["passed_in_context"] is not True]
        penalty = lambda xs: sum(  # noqa: E731
            SEVERITY_WEIGHTS[METRIC_REGISTRY[x["id"]].severity] for x in xs)
        table["summary"] = {
            "run": len(rows),
            "passed": sum(1 for x in rows if x["passed"] is True),
            "failed": len(failed),
            "skipped": len(table["rows"]) - len(rows),
            "weighted_penalty": _number(penalty(failed)),
            "failed_in_context": len(failed_ctx) if weighted else None,
            "weighted_penalty_in_context": _number(penalty(failed_ctx))
            if weighted else None,
        }
    return tables


def _ontocheck_table(ttl, questions, benchmark, domain_prefixes, allow_network):
    from .query_fitness import (
        conceptual_fitness,
        counterfactual_importance,
        structural_fitness,
    )
    from .run_assessment import CORE_METRIC_NAMES, METRIC_DISPATCHER, _scalarize
    from .task_based_metric import task_based_metric_v_0_0_1

    rows, queries, cases = [], {}, []

    def add(metric_id, name, kind, value=None, status="Success", detail=None,
            level="0"):
        rows.append({"id": metric_id, "name": name, "kind": kind,
                     "level": level, "value": _number(value),
                     "status": status, "detail": detail or {}})

    for m in CORE_METRIC_NAMES:
        if m in _NATIVE_SKIP:
            continue
        if m in _NETWORK_METRICS and not allow_network:
            add(m, _NATIVE_NAMES.get(m, m), "native",
                status="Skipped (requires network access)")
            continue
        try:
            raw = METRIC_DISPATCHER[m](str(ttl))
            add(m, _NATIVE_NAMES.get(m, m), "native", _scalarize(m, raw))
        except Exception as e:                   # noqa: BLE001
            add(m, _NATIVE_NAMES.get(m, m), "native", status=f"Error: {e}")

    if questions is None:
        for m, name, level in (("recall", "Recall", "I"),
                               ("precision", "Precision", "I"),
                               ("conceptualFitness", "Conceptual fitness", "I"),
                               ("structuralFitness", "Structural fitness",
                                "II-A")):
            add(m, name, "task", status="Skipped (no competency questions)",
                level=level)
    else:
        try:
            t = task_based_metric_v_0_0_1(str(ttl), questions,
                                          domain_prefixes or [])
            add("recall", "Recall", "task", t["recall"],
                detail={"T_a": t["T_a_count"], "T_o": t["T_o_count"],
                        "intersection": t["intersection"]}, level="I")
            add("precision", "Precision", "task", t["precision"], level="I")
        except Exception as e:                   # noqa: BLE001
            add("recall", "Recall", "task", status=f"Error: {e}", level="I")
            add("precision", "Precision", "task", status=f"Error: {e}",
                level="I")
        for metric_id, name, fn, keys, level in (
            ("conceptualFitness", "Conceptual fitness", conceptual_fitness,
             ("aligned_score", "ambiguity"), "I"),
            ("structuralFitness", "Structural fitness", structural_fitness,
             ("path_coverage", "path_stretch"), "II-A"),
        ):
            try:
                r = fn(str(ttl), questions)
                add(metric_id, name, "fitness", r.score, r.status,
                    {k: _number(r.detail.get(k)) for k in keys}, level)
                for q in r.detail.get("per_query", []):
                    entry = queries.setdefault(
                        q["qid"], {"qid": q["qid"], "question": q["question"]})
                    entry.update({k: _number(v) if not isinstance(v, list)
                                  else v for k, v in q.items()
                                  if k not in ("qid", "question")})
            except Exception as e:               # noqa: BLE001
                add(metric_id, name, "fitness", status=f"Error: {e}",
                    level=level)

    add("logicalFitness", "Logical fitness", "fitness",
        status="Not run (no logical requirements)", level="II-B")
    downstream = (("benchmarkScore", "RAG score"),
                  ("answerAccuracy", "Answer accuracy"),
                  ("reasoningPath", "Reasoning-path match"))
    if benchmark is None:
        add("counterfactualImportance", "Counterfactual concept importance",
            "fitness", status="Not available (no benchmark suite)", level="I")
        for m, name in downstream:
            add(m, name, "benchmark", status="Not available (no benchmark "
                "suite)", level="IV")
    else:
        try:
            r = counterfactual_importance(str(ttl), benchmark=str(benchmark))
            top = [{"concept": k, **v} for k, v in sorted(
                (r.detail.get("weights") or {}).items(),
                key=lambda kv: -(kv[1]["w_impact"] or 0))[:5]]
            add("counterfactualImportance", "Counterfactual concept importance",
                "fitness", r.score, r.status,
                {"Z_baseline": _number(r.detail.get("Z_baseline")),
                 "top": top}, "I")
        except Exception as e:                   # noqa: BLE001
            add("counterfactualImportance", "Counterfactual concept importance",
                "fitness", status=f"Error: {e}", level="I")
        try:
            cases, values = _benchmark_cases(ttl, benchmark)
            for m, name in downstream:
                add(m, name, "benchmark", values[m], level="IV",
                    status="Success" if values[m] is not None else
                    "Not available (no such cases)")
        except Exception as e:                   # noqa: BLE001
            for m, name in downstream:
                add(m, name, "benchmark", status=f"Error: {e}", level="IV")
    return {"rows": rows}, list(queries.values()), cases


def _benchmark_cases(ttl, benchmark):
    """Run the benchmark suite: its cases and the Level IV summary values."""
    from .benchmark import load_suite, run_suite

    suite = load_suite(str(benchmark))
    result = run_suite(suite, [str(ttl)])
    prompts = {c.id: c.prompt for c in suite.cases}
    cases = [{"id": c.case_id, "question": prompts.get(c.case_id, ""),
              "level": c.level, "task_type": c.task_type,
              "score": _number(c.score),
              "answer_score": _number(c.answer_score),
              "evidence_score": _number(c.evidence_score),
              "constraint_score": _number(c.constraint_score),
              "status": c.status}
             for c in result.results]
    mean = lambda xs: _number(sum(xs) / len(xs)) if xs else None  # noqa: E731
    answered = [c.answer_score for c in result.results
                if c.constraint_score is None and c.status == "success"]
    paths = [c.evidence_score for c in result.results
             if c.evidence_score is not None]
    return cases, {"benchmarkScore": _number(result.score),
                   "answerAccuracy": mean(answered),
                   "reasoningPath": mean(paths)}


def score_domain(name, files, questions=None, benchmark=None,
                 domain_prefixes=None, allow_network=False):
    """
    Run every metric on one domain.

    Parameters
    ----------
    name : str
    files : list of str or pathlib.Path
        Turtle files, merged before scoring.
    questions : str or pathlib.Path, optional
        Competency questions.
    benchmark : str or pathlib.Path, optional
        Benchmark suite with expected answers.
    domain_prefixes : list of str, optional
        Prefixes of the domain terms in *questions*, for Recall/Precision.
    allow_network : bool, optional
        Run metrics that make HTTP requests.  Default ``False``, so results
        are reproducible offline.

    Returns
    -------
    dict
        ``name``, ``files``, ``questions``, ``benchmark``, ``has_abox``,
        ``queries`` (each query's id, text and scores), ``benchmark_cases``
        (each case's id, prompt and scores) and ``tables`` (``oops``,
        ``foops``, ``oquare``, ``ontocheck``), or
        ``error`` when the domain could not be scored.
    """
    from .helpers.semantic_helpers import _individuals

    entry = {"name": name, "files": [Path(f).name for f in files],
             "questions": Path(questions).name if questions else None,
             "benchmark": Path(benchmark).name if benchmark else None}
    missing = [str(f) for f in list(files) + [questions, benchmark]
               if f and not Path(f).is_file()]
    if missing:
        entry["error"] = "Missing " + ", ".join(missing)
        return entry
    with tempfile.TemporaryDirectory() as tmp, _quiet():
        try:
            ttl = _merge(files, tmp)
            has_abox = bool(_individuals(Graph().parse(str(ttl), format="turtle")))
            tables = _framework_tables(ttl, questions, domain_prefixes,
                                       allow_network, has_abox)
            tables["ontocheck"], queries, cases = _ontocheck_table(
                ttl, questions, benchmark, domain_prefixes, allow_network)
        except Exception as e:                   # noqa: BLE001
            entry["error"] = f"{type(e).__name__}: {e}"
            return entry
    entry["has_abox"] = has_abox
    entry["weighted_by"] = (
        ["competency questions"] if questions else []) + (
        ["instance data"] if has_abox else [])
    entry["queries"] = queries
    entry["benchmark_cases"] = cases
    entry["tables"] = tables
    return entry


def load_manifest(path):
    """Read a manifest, resolving its paths relative to the manifest."""
    path = Path(path)
    base = path.parent
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for d in data.get("domains", []):
        resolve = lambda p: str(base / p) if p else None  # noqa: E731
        out.append({
            "name": d["name"],
            "files": [resolve(f) for f in d["files"]],
            "questions": resolve(d.get("questions")),
            "benchmark": resolve(d.get("benchmark")),
            "domain_prefixes": d.get("domain_prefixes") or [],
        })
    return out


def export(domains, out, allow_network=False, update=False, progress=print):
    """
    Score *domains* and write the leaderboard JSON to *out*.

    Parameters
    ----------
    domains : list of dict
        As returned by :func:`load_manifest`.
    out : str or pathlib.Path
    allow_network : bool, optional
    update : bool, optional
        Keep the entries of an existing *out* file for domains not scored in
        this run.

    Returns
    -------
    dict
        The payload written.
    """
    from importlib.metadata import PackageNotFoundError, version

    out = Path(out)
    existing = []
    if update and out.is_file():
        existing = json.loads(out.read_text(encoding="utf-8")).get("domains", [])
    scored = {}
    for d in domains:
        progress(f"Scoring {d['name']}…")
        scored[d["name"]] = score_domain(
            d["name"], d["files"], d.get("questions"), d.get("benchmark"),
            d.get("domain_prefixes"), allow_network)
    names = [e["name"] for e in existing] + [n for n in scored
                                             if n not in {e["name"] for e in existing}]
    by_name = {e["name"]: e for e in existing}
    by_name.update(scored)
    try:
        package_version = version("OntoCheck")
    except PackageNotFoundError:
        package_version = None
    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ontocheck_version": package_version,
        "settings": {"allow_network": allow_network},
        "domains": [by_name[n] for n in names],
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    progress(f"Wrote {out}")
    return payload


def main(argv=None):
    """Entry point for the ``ontocheck-leaderboard`` command."""
    p = argparse.ArgumentParser(
        prog="ontocheck-leaderboard",
        description="Score ontologies and write the leaderboard results JSON.")
    p.add_argument("--manifest", help="JSON manifest of domains to score.")
    p.add_argument("--only", nargs="+", metavar="NAME",
                   help="Score only these domains from the manifest.")
    p.add_argument("--name", help="Name of a single domain given on the "
                                  "command line.")
    p.add_argument("--ontology", nargs="+", metavar="TTL",
                   help="Turtle file(s) of that domain, merged.")
    p.add_argument("--questions", help="Competency questions for that domain.")
    p.add_argument("--benchmark", help="Benchmark suite for that domain.")
    p.add_argument("--domain-prefixes", nargs="+", default=[],
                   help="Prefixes of the domain terms in the questions.")
    p.add_argument("--out", default="ontocheck-results.json",
                   help="Output file (default: ontocheck-results.json).")
    p.add_argument("--update", action="store_true",
                   help="Keep other domains already in --out.")
    p.add_argument("--network", action="store_true",
                   help="Also run metrics that make HTTP requests.")
    args = p.parse_args(argv)

    if args.manifest:
        domains = load_manifest(args.manifest)
        if args.only:
            domains = [d for d in domains if d["name"] in set(args.only)]
    elif args.name and args.ontology:
        domains = [{"name": args.name, "files": args.ontology,
                    "questions": args.questions, "benchmark": args.benchmark,
                    "domain_prefixes": args.domain_prefixes}]
    else:
        p.error("give --manifest, or --name with --ontology")
    if not domains:
        p.error("no domains to score")
    payload = export(domains, args.out, allow_network=args.network,
                     update=args.update)
    failed = [d["name"] for d in payload["domains"] if "error" in d]
    for d in payload["domains"]:
        if "error" in d:
            print(f"  {d['name']}: {d['error']}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
