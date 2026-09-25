"""Data models shared by the competency benchmark components."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class BenchmarkLevel(str, Enum):
    """Supported competency-question complexity levels."""

    FACT_RETRIEVAL = "fact_retrieval"
    COMPLEX_REASONING = "complex_reasoning"
    CONTEXTUAL_SUMMARIZATION = "contextual_summarization"
    CONSTRAINED_GENERATION = "constrained_generation"


@dataclass(frozen=True)
class QuerySpec:
    """A machine-executable query attached to a benchmark case."""

    language: str
    text: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpectedResult:
    """The normalized result expected from an evaluator."""

    kind: str
    values: Any


@dataclass(frozen=True)
class BenchmarkContext:
    """Version pins that make a benchmark run scientifically reproducible."""

    ontology_version: str = ""
    ontology_commit: str = ""
    data_version: str = ""
    data_commit: str = ""
    metric_version: str = ""


@dataclass(frozen=True)
class ProvenanceSpec:
    """Sources and reviewers responsible for one benchmark case."""

    sources: Tuple[str, ...] = ()
    curator: Optional[str] = None
    reviewers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceSpec:
    """Evidence paths, claims, and source records supporting an answer."""

    required_paths: Tuple[Tuple[str, ...], ...] = ()
    required_claims: Tuple[str, ...] = ()
    source_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoringSpec:
    """Weights used to combine evaluator score components."""

    answer_weight: float = 1.0
    evidence_weight: float = 0.0
    constraint_weight: float = 0.0


@dataclass(frozen=True)
class BenchmarkCase:
    """One independently executable competency benchmark case."""

    id: str
    level: BenchmarkLevel
    task_type: str
    prompt: str
    query: QuerySpec
    expected: ExpectedResult
    evidence: EvidenceSpec = field(default_factory=EvidenceSpec)
    scoring: ScoringSpec = field(default_factory=ScoringSpec)
    tags: Tuple[str, ...] = ()
    family_id: Optional[str] = None
    provenance: ProvenanceSpec = field(default_factory=ProvenanceSpec)
    assumptions: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    split: str = "unspecified"
    leakage_group: Optional[str] = None


@dataclass(frozen=True)
class BenchmarkSuite:
    """A versioned collection of benchmark cases and namespace settings."""

    schema_version: str
    suite_id: str
    domain: str
    namespaces: Dict[str, str]
    inference_profile: str
    cases: Tuple[BenchmarkCase, ...]
    context: BenchmarkContext = field(default_factory=BenchmarkContext)


@dataclass
class CaseResult:
    """Normalized output produced by every evaluator."""

    case_id: str
    level: str
    task_type: str
    status: str
    score: float
    answer_score: float
    evidence_score: Optional[float] = None
    constraint_score: Optional[float] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    actual: Any = None
    diagnostics: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)
    evaluator: str = ""
    inference_profile: str = "none"
    runtime_ms: float = 0.0


@dataclass
class SuiteResult:
    """Case-level results and aggregate scores for one suite run."""

    suite_id: str
    score: float
    results: List[CaseResult]
    scores_by_level: Dict[str, float]
    scores_by_task_type: Dict[str, float]
    context: BenchmarkContext = field(default_factory=BenchmarkContext)
