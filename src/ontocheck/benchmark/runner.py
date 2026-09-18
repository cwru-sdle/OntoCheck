"""Orchestration for executable competency benchmark suites."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Dict, Iterable, List, Optional, Union

from rdflib import Graph, Namespace

from .evaluators import (
    EvaluationContext,
    EvaluatorRegistry,
    default_registry,
)
from .io import load_suite
from .models import BenchmarkSuite, CaseResult, SuiteResult
from .reasoners import ReasonerRegistry, default_reasoners

PathInput = Union[str, Path]


def _averages(results: Iterable[CaseResult], attribute: str) -> Dict[str, float]:
    grouped: Dict[str, List[float]] = {}
    for result in results:
        grouped.setdefault(getattr(result, attribute), []).append(result.score)
    return {
        key: sum(values) / len(values)
        for key, values in sorted(grouped.items())
    }


class BenchmarkRunner:
    """Load ontology data and dispatch benchmark cases to evaluators."""

    def __init__(
        self,
        registry: Optional[EvaluatorRegistry] = None,
        reasoners: Optional[ReasonerRegistry] = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.reasoners = reasoners or default_reasoners()

    def run(
        self,
        suite: BenchmarkSuite,
        ontology_files: Union[PathInput, Iterable[PathInput]],
    ) -> SuiteResult:
        """Execute a validated suite against one or more Turtle files."""

        files = (
            [ontology_files]
            if isinstance(ontology_files, (str, Path))
            else list(ontology_files)
        )
        if not files:
            raise ValueError("At least one ontology file is required")

        graph = Graph()
        for prefix, uri in suite.namespaces.items():
            graph.bind(prefix, Namespace(uri))
        for ontology_file in files:
            graph.parse(str(ontology_file), format="turtle")

        context = EvaluationContext(
            graph=graph,
            inference_profile=suite.inference_profile,
            reasoners=self.reasoners,
        )
        results = []
        for case in suite.cases:
            started = perf_counter()
            try:
                evaluator = self.registry.get(case.task_type)
                result = evaluator.evaluate(case, context)
            except Exception as error:
                result = CaseResult(
                    case_id=case.id,
                    level=case.level.value,
                    task_type=case.task_type,
                    status="error",
                    score=0.0,
                    answer_score=0.0,
                    diagnostics=[str(error)],
                )
            result.inference_profile = suite.inference_profile
            result.runtime_ms = (perf_counter() - started) * 1000
            results.append(result)

        score = sum(result.score for result in results) / len(results)
        return SuiteResult(
            suite_id=suite.suite_id,
            score=score,
            results=results,
            scores_by_level=_averages(results, "level"),
            scores_by_task_type=_averages(results, "task_type"),
        )


def run_suite(
    suite: Union[BenchmarkSuite, PathInput],
    ontology_files: Union[PathInput, Iterable[PathInput]],
    registry: Optional[EvaluatorRegistry] = None,
    reasoners: Optional[ReasonerRegistry] = None,
) -> SuiteResult:
    """Load a suite when needed and run it against ontology files."""

    benchmark_suite = (
        suite if isinstance(suite, BenchmarkSuite) else load_suite(suite)
    )
    return BenchmarkRunner(registry=registry, reasoners=reasoners).run(
        benchmark_suite, ontology_files
    )
