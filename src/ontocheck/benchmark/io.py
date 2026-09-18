"""Load, validate, and serialize competency benchmark data."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .models import (
    BenchmarkCase,
    BenchmarkLevel,
    BenchmarkSuite,
    EvidenceSpec,
    ExpectedResult,
    QuerySpec,
    ScoringSpec,
    SuiteResult,
)


class BenchmarkValidationError(ValueError):
    """Raised when a benchmark suite does not conform to the schema."""


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BenchmarkValidationError("{} must be an object".format(location))
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkValidationError(
            "{} must be a non-empty string".format(location)
        )
    return value


def _paths(value: Any, location: str) -> Tuple[Tuple[str, ...], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BenchmarkValidationError("{} must be an array".format(location))

    paths = []
    for index, path in enumerate(value):
        if not isinstance(path, Sequence) or isinstance(path, (str, bytes)):
            raise BenchmarkValidationError(
                "{}[{}] must be an array".format(location, index)
            )
        normalized = tuple(
            _string(item, "{}[{}]".format(location, index)) for item in path
        )
        if not normalized:
            raise BenchmarkValidationError(
                "{}[{}] must not be empty".format(location, index)
            )
        paths.append(normalized)
    return tuple(paths)


def _weight(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkValidationError("{} must be a number".format(location))
    if value < 0:
        raise BenchmarkValidationError("{} must not be negative".format(location))
    return float(value)


def _parse_case(data: Any, index: int) -> BenchmarkCase:
    location = "cases[{}]".format(index)
    item = _mapping(data, location)
    case_id = _string(item.get("id"), "{}.id".format(location))

    try:
        level = BenchmarkLevel(
            _string(item.get("level"), "{}.level".format(case_id))
        )
    except ValueError as error:
        values = ", ".join(level.value for level in BenchmarkLevel)
        raise BenchmarkValidationError(
            "{}.level must be one of: {}".format(case_id, values)
        ) from error

    query_data = _mapping(item.get("query"), "{}.query".format(case_id))
    query_language = _string(
        query_data.get("language"), "{}.query.language".format(case_id)
    ).lower()
    query_text = query_data.get("text")
    if query_text is not None:
        query_text = _string(query_text, "{}.query.text".format(case_id))
    if query_language == "sparql" and query_text is None:
        raise BenchmarkValidationError(
            "{}.query.text is required for SPARQL".format(case_id)
        )
    query = QuerySpec(
        language=query_language,
        text=query_text,
        parameters={
            key: value
            for key, value in query_data.items()
            if key not in {"language", "text"}
        },
    )

    expected_data = _mapping(item.get("expected"), "{}.expected".format(case_id))
    if "values" not in expected_data:
        raise BenchmarkValidationError(
            "{}.expected.values is required".format(case_id)
        )
    expected = ExpectedResult(
        kind=_string(
            expected_data.get("kind"), "{}.expected.kind".format(case_id)
        ),
        values=expected_data["values"],
    )

    evidence_data = _mapping(
        item.get("evidence", {}), "{}.evidence".format(case_id)
    )
    evidence = EvidenceSpec(
        required_paths=_paths(
            evidence_data.get("required_paths", ()),
            "{}.evidence.required_paths".format(case_id),
        )
    )

    scoring_data = _mapping(
        item.get("scoring", {}), "{}.scoring".format(case_id)
    )
    scoring = ScoringSpec(
        answer_weight=_weight(
            scoring_data.get("answer_weight", 1.0),
            "{}.scoring.answer_weight".format(case_id),
        ),
        evidence_weight=_weight(
            scoring_data.get("evidence_weight", 0.0),
            "{}.scoring.evidence_weight".format(case_id),
        ),
        constraint_weight=_weight(
            scoring_data.get("constraint_weight", 0.0),
            "{}.scoring.constraint_weight".format(case_id),
        ),
    )
    if (
        scoring.answer_weight
        + scoring.evidence_weight
        + scoring.constraint_weight
        == 0
    ):
        raise BenchmarkValidationError(
            "{}.scoring must have at least one positive weight".format(case_id)
        )

    tags = item.get("tags", ())
    if not isinstance(tags, Sequence) or isinstance(tags, (str, bytes)):
        raise BenchmarkValidationError("{}.tags must be an array".format(case_id))

    return BenchmarkCase(
        id=case_id,
        level=level,
        task_type=_string(
            item.get("task_type"), "{}.task_type".format(case_id)
        ),
        prompt=_string(item.get("prompt"), "{}.prompt".format(case_id)),
        query=query,
        expected=expected,
        evidence=evidence,
        scoring=scoring,
        tags=tuple(
            _string(tag, "{}.tags".format(case_id)) for tag in tags
        ),
    )


def parse_suite(data: Any) -> BenchmarkSuite:
    """Validate a decoded JSON value and return a benchmark suite."""

    root = _mapping(data, "suite")
    schema_version = _string(root.get("schema_version"), "schema_version")
    if schema_version != "1.0":
        raise BenchmarkValidationError(
            "Unsupported schema_version {!r}; expected '1.0'".format(
                schema_version
            )
        )

    namespace_data = _mapping(root.get("namespaces", {}), "namespaces")
    namespaces: Dict[str, str] = {}
    for prefix, uri in namespace_data.items():
        namespaces[_string(prefix, "namespace prefix")] = _string(
            uri, "namespace {!r}".format(prefix)
        )

    inference = _mapping(root.get("inference", {}), "inference")
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkValidationError("cases must be a non-empty array")
    cases = tuple(_parse_case(item, index) for index, item in enumerate(raw_cases))

    case_ids = [case.id for case in cases]
    duplicates = sorted(
        case_id for case_id in set(case_ids) if case_ids.count(case_id) > 1
    )
    if duplicates:
        raise BenchmarkValidationError(
            "Duplicate case IDs: {}".format(", ".join(duplicates))
        )

    return BenchmarkSuite(
        schema_version=schema_version,
        suite_id=_string(root.get("suite_id"), "suite_id"),
        domain=_string(root.get("domain"), "domain"),
        namespaces=namespaces,
        inference_profile=_string(inference.get("profile", "none"), "inference.profile"),
        cases=cases,
    )


def load_suite(path: Any) -> BenchmarkSuite:
    """Load and validate a benchmark suite from a UTF-8 JSON file."""

    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            return parse_suite(json.load(stream))
    except json.JSONDecodeError as error:
        raise BenchmarkValidationError(
            "{}:{}: invalid JSON: {}".format(source, error.lineno, error.msg)
        ) from error


def write_result(result: SuiteResult, path: Any) -> None:
    """Write a suite result as deterministic, human-readable JSON."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        json.dump(asdict(result), stream, indent=2, sort_keys=True)
        stream.write("\n")
