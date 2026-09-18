"""Evaluator registry and built-in competency benchmark scorers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Hashable, List, Mapping, Protocol

from rdflib import Graph
from rdflib.query import Result
from rdflib.term import Identifier

from .models import BenchmarkCase, CaseResult
from .reasoners import ReasonerAnswer, ReasonerRegistry


class UnsupportedTaskType(ValueError):
    """Raised when no evaluator is registered for a task type."""


@dataclass(frozen=True)
class EvaluationContext:
    """Shared graph and reasoner services supplied to evaluators."""

    graph: Graph
    inference_profile: str
    reasoners: ReasonerRegistry


class Evaluator(Protocol):
    """Interface implemented by benchmark case evaluators."""

    name: str

    def evaluate(
        self, case: BenchmarkCase, context: EvaluationContext
    ) -> CaseResult:
        """Evaluate one case against a loaded ontology graph."""


class EvaluatorRegistry:
    """Small task-type registry used by the benchmark runner."""

    def __init__(self) -> None:
        self._evaluators: Dict[str, Evaluator] = {}

    def register(
        self, task_type: str, evaluator: Evaluator, replace: bool = False
    ) -> None:
        """Register an evaluator, rejecting accidental replacement."""

        if task_type in self._evaluators and not replace:
            raise ValueError(
                "An evaluator is already registered for {!r}".format(task_type)
            )
        self._evaluators[task_type] = evaluator

    def get(self, task_type: str) -> Evaluator:
        """Return the evaluator for a task type."""

        try:
            return self._evaluators[task_type]
        except KeyError as error:
            raise UnsupportedTaskType(
                "No evaluator registered for task type {!r}".format(task_type)
            ) from error


def _normalize_term(term: Any, graph: Graph) -> Any:
    if term is None:
        return None
    if not isinstance(term, Identifier):
        raise TypeError("SPARQL result contains an unsupported RDF value")
    return term.n3(namespace_manager=graph.namespace_manager)


def _normalize_select(result: Result, graph: Graph) -> List[Any]:
    rows: List[Any] = []
    for row in result:
        values = [_normalize_term(value, graph) for value in row]
        rows.append(values[0] if len(values) == 1 else values)
    return rows


def _hashable(value: Any) -> Hashable:
    if isinstance(value, list):
        return tuple(_hashable(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            sorted((key, _hashable(item)) for key, item in value.items())
        )
    return value


def _result_set_metrics(expected: Any, actual: List[Any]) -> Dict[str, float]:
    if not isinstance(expected, list):
        raise ValueError("result_set expectations must contain an array")
    expected_set = {_hashable(item) for item in expected}
    actual_set = {_hashable(item) for item in actual}
    if not expected_set and not actual_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    overlap = len(expected_set & actual_set)
    precision = overlap / len(actual_set) if actual_set else 0.0
    recall = overlap / len(expected_set) if expected_set else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def _result_set_score(expected: Any, actual: List[Any]) -> float:
    return _result_set_metrics(expected, actual)["f1"]


class RetrievalEvaluator:
    """Execute SPARQL and compare boolean or result-set answers."""

    name = "retrieval-v1"

    def evaluate(
        self, case: BenchmarkCase, context: EvaluationContext
    ) -> CaseResult:
        graph = context.graph
        if case.query.language != "sparql":
            raise ValueError(
                "fact_retrieval requires query language 'sparql'"
            )
        if case.scoring.evidence_weight or case.scoring.constraint_weight:
            raise ValueError(
                "fact_retrieval currently supports answer scoring only"
            )

        query_result = graph.query(case.query.text)
        if case.expected.kind == "boolean":
            if not isinstance(case.expected.values, bool):
                raise ValueError("boolean expectations must be true or false")
            if query_result.type != "ASK":
                raise ValueError("boolean expectations require a SPARQL ASK query")
            actual: Any = bool(query_result.askAnswer)
            answer_score = float(actual == case.expected.values)
        elif case.expected.kind == "result_set":
            if query_result.type != "SELECT":
                raise ValueError(
                    "result_set expectations require a SPARQL SELECT query"
                )
            actual = _normalize_select(query_result, graph)
            answer_score = _result_set_score(case.expected.values, actual)
        else:
            raise ValueError(
                "Unsupported retrieval expectation kind {!r}".format(
                    case.expected.kind
                )
            )

        diagnostics = []
        if answer_score < 1.0:
            diagnostics.append("Actual answer did not exactly match expectation")
        return CaseResult(
            case_id=case.id,
            level=case.level.value,
            task_type=case.task_type,
            status="success",
            score=answer_score,
            answer_score=answer_score,
            actual=actual,
            diagnostics=diagnostics,
            evaluator=self.name,
        )


class ContextualSummaryEvaluator:
    """Build and score a structured summary from multiple SPARQL sections."""

    name = "contextual-summary-v1"

    def evaluate(
        self, case: BenchmarkCase, context: EvaluationContext
    ) -> CaseResult:
        if case.query.language != "sparql_summary":
            raise ValueError(
                "contextual_summary requires query language 'sparql_summary'"
            )
        if case.expected.kind != "structured_summary":
            raise ValueError(
                "contextual_summary requires a structured_summary expectation"
            )
        if not isinstance(case.expected.values, Mapping):
            raise ValueError("structured_summary values must be an object")
        if case.scoring.evidence_weight or case.scoring.constraint_weight:
            raise ValueError(
                "contextual_summary currently supports answer scoring only"
            )

        sections = case.query.parameters.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ValueError("sparql_summary sections must be a non-empty array")

        actual_sections: Dict[str, List[Any]] = {}
        section_metrics: Dict[str, Dict[str, float]] = {}
        for index, section in enumerate(sections):
            if not isinstance(section, Mapping):
                raise ValueError(
                    "summary section {} must be an object".format(index)
                )
            section_id = section.get("id")
            query_text = section.get("query")
            if not isinstance(section_id, str) or not section_id:
                raise ValueError(
                    "summary section {} requires a non-empty id".format(index)
                )
            if section_id in actual_sections:
                raise ValueError(
                    "duplicate summary section {!r}".format(section_id)
                )
            if not isinstance(query_text, str) or not query_text:
                raise ValueError(
                    "summary section {!r} requires a SPARQL query".format(
                        section_id
                    )
                )
            if section_id not in case.expected.values:
                raise ValueError(
                    "summary section {!r} has no expected values".format(
                        section_id
                    )
                )

            result = context.graph.query(query_text)
            if result.type != "SELECT":
                raise ValueError(
                    "summary section {!r} must use SELECT".format(section_id)
                )
            actual = _normalize_select(result, context.graph)
            actual_sections[section_id] = actual
            section_metrics[section_id] = _result_set_metrics(
                case.expected.values[section_id], actual
            )

        unexpected = sorted(set(case.expected.values) - set(actual_sections))
        if unexpected:
            raise ValueError(
                "expected summary sections were not queried: {}".format(
                    ", ".join(unexpected)
                )
            )

        count = len(section_metrics)
        coverage = (
            sum(metrics["recall"] for metrics in section_metrics.values())
            / count
        )
        relevance = (
            sum(metrics["precision"] for metrics in section_metrics.values())
            / count
        )
        answer_score = (
            sum(metrics["f1"] for metrics in section_metrics.values()) / count
        )
        metrics = {
            "coverage": coverage,
            "relevance": relevance,
            "faithfulness": 1.0,
            "unsupported_claim_rate": 0.0,
        }
        diagnostics = []
        if answer_score < 1.0:
            diagnostics.append(
                "Structured summary did not exactly match all expected claims"
            )

        return CaseResult(
            case_id=case.id,
            level=case.level.value,
            task_type=case.task_type,
            status="success",
            score=answer_score,
            answer_score=answer_score,
            metrics=metrics,
            actual={
                "sections": actual_sections,
                "section_metrics": section_metrics,
            },
            diagnostics=diagnostics,
            evaluator=self.name,
        )


def _normalize_proof(answer: ReasonerAnswer, graph: Graph) -> List[str]:
    proof = answer.proof
    if not proof:
        return []
    normalized = [_normalize_term(proof[0][0], graph)]
    for _, predicate, target in proof:
        normalized.extend(
            [
                _normalize_term(predicate, graph),
                _normalize_term(target, graph),
            ]
        )
    return normalized


class DeductionEvaluator:
    """Score transitive graph-path answers and their supporting proofs."""

    name = "deduction-v1"

    def evaluate(
        self, case: BenchmarkCase, context: EvaluationContext
    ) -> CaseResult:
        if case.expected.kind != "result_set":
            raise ValueError("deduction currently requires a result_set expectation")
        if case.scoring.constraint_weight:
            raise ValueError("deduction does not support constraint scoring")
        if case.scoring.evidence_weight and not case.evidence.required_paths:
            raise ValueError(
                "evidence_weight requires at least one required evidence path"
            )

        reasoner = context.reasoners.get(context.inference_profile)
        reasoned_answers = reasoner.reason(case, context.graph)
        answer_values = [
            _normalize_term(answer.value, context.graph)
            for answer in reasoned_answers
        ]
        proofs = [
            _normalize_proof(answer, context.graph)
            for answer in reasoned_answers
        ]
        answer_score = _result_set_score(case.expected.values, answer_values)

        evidence_score = None
        if case.evidence.required_paths:
            evidence_score = _result_set_score(
                [list(path) for path in case.evidence.required_paths],
                proofs,
            )

        answer_weight = case.scoring.answer_weight
        evidence_weight = case.scoring.evidence_weight
        weighted_score = answer_score * answer_weight
        if evidence_weight:
            weighted_score += (evidence_score or 0.0) * evidence_weight
        score = weighted_score / (answer_weight + evidence_weight)

        diagnostics = []
        if answer_score < 1.0:
            diagnostics.append("Reasoned answers did not exactly match expectation")
        if evidence_score is not None and evidence_score < 1.0:
            diagnostics.append("Proof paths did not exactly match expectation")

        actual = [
            {
                "value": _normalize_term(answer.value, context.graph),
                "hops": len(answer.proof),
                "inferred": bool(
                    len(answer.proof) > 1
                    and (
                        answer.proof[0][0],
                        answer.proof[0][1],
                        answer.value,
                    )
                    not in context.graph
                ),
                "proof": proof,
                "proof_steps": [
                    {
                        "subject": _normalize_term(subject, context.graph),
                        "predicate": _normalize_term(predicate, context.graph),
                        "object": _normalize_term(target, context.graph),
                        "asserted": (subject, predicate, target) in context.graph,
                    }
                    for subject, predicate, target in answer.proof
                ],
            }
            for answer, proof in zip(reasoned_answers, proofs)
        ]
        return CaseResult(
            case_id=case.id,
            level=case.level.value,
            task_type=case.task_type,
            status="success",
            score=score,
            answer_score=answer_score,
            evidence_score=evidence_score,
            actual=actual,
            diagnostics=diagnostics,
            evaluator="{}+{}".format(self.name, reasoner.name),
        )


def default_registry() -> EvaluatorRegistry:
    """Create a registry containing the dependency-free baseline evaluators."""

    registry = EvaluatorRegistry()
    registry.register("fact_retrieval", RetrievalEvaluator())
    registry.register("deduction", DeductionEvaluator())
    registry.register("contextual_summary", ContextualSummaryEvaluator())
    return registry


