"""Load, validate, and serialize competency benchmark data."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .models import (
    BenchmarkCase,
    BenchmarkContext,
    BenchmarkLevel,
    BenchmarkSuite,
    EvidenceSpec,
    ExpectedResult,
    ProvenanceSpec,
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


def _optional_string(value: Any, location: str) -> Any:
    if value is None:
        return None
    return _string(value, location)


def _strings(value: Any, location: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BenchmarkValidationError("{} must be an array".format(location))
    return tuple(
        _string(item, "{}[{}]".format(location, index))
        for index, item in enumerate(value)
    )


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


def _parse_context(root: Mapping[str, Any], schema_version: str) -> BenchmarkContext:
    if schema_version == "1.0":
        return BenchmarkContext()

    context_data = _mapping(root.get("context", {}), "context")
    return BenchmarkContext(
        ontology_version=_string(
            context_data.get("ontology_version"), "context.ontology_version"
        ),
        ontology_commit=_string(
            context_data.get("ontology_commit"), "context.ontology_commit"
        ),
        data_version=_string(
            context_data.get("data_version"), "context.data_version"
        ),
        data_commit=_string(
            context_data.get("data_commit"), "context.data_commit"
        ),
        metric_version=_string(
            context_data.get("metric_version"), "context.metric_version"
        ),
    )


def _parse_case(
    data: Any, index: int, schema_version: str
) -> BenchmarkCase:
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
    task_type = _string(
        item.get("task_type"), "{}.task_type".format(case_id)
    )

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
        ),
        required_claims=(
            _strings(
                evidence_data.get("required_claims", ()),
                "{}.evidence.required_claims".format(case_id),
            )
            if schema_version == "2.0"
            else ()
        ),
        source_ids=(
            _strings(
                evidence_data.get("source_ids", ()),
                "{}.evidence.source_ids".format(case_id),
            )
            if schema_version == "2.0"
            else ()
        ),
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

    provenance = ProvenanceSpec()
    family_id = None
    split = "unspecified"
    leakage_group = None
    assumptions = ()
    constraints = ()
    if schema_version == "2.0":
        provenance_data = _mapping(
            item.get("provenance", {}), "{}.provenance".format(case_id)
        )
        provenance = ProvenanceSpec(
            sources=_strings(
                provenance_data.get("sources", ()),
                "{}.provenance.sources".format(case_id),
            ),
            curator=_optional_string(
                provenance_data.get("curator"),
                "{}.provenance.curator".format(case_id),
            ),
            reviewers=_strings(
                provenance_data.get("reviewers", ()),
                "{}.provenance.reviewers".format(case_id),
            ),
        )
        family_id = _optional_string(
            item.get("family_id"), "{}.family_id".format(case_id)
        )
        split = _string(
            item.get("split", "unspecified"), "{}.split".format(case_id)
        )
        leakage_group = _optional_string(
            item.get("leakage_group"), "{}.leakage_group".format(case_id)
        )
        assumptions = _strings(
            item.get("assumptions", ()), "{}.assumptions".format(case_id)
        )
        constraints = _strings(
            item.get("constraints", ()), "{}.constraints".format(case_id)
        )
        if family_id is None:
            raise BenchmarkValidationError(
                "{}.family_id is required for schema 2.0".format(case_id)
            )
        if not provenance.sources:
            raise BenchmarkValidationError(
                "{}.provenance.sources must not be empty for schema 2.0".format(
                    case_id
                )
            )
        if split == "unspecified":
            raise BenchmarkValidationError(
                "{}.split is required for schema 2.0".format(case_id)
            )
        if leakage_group is None:
            raise BenchmarkValidationError(
                "{}.leakage_group is required for schema 2.0".format(case_id)
            )
        if level == BenchmarkLevel.CONSTRAINED_GENERATION:
            if not assumptions:
                raise BenchmarkValidationError(
                    "{}.assumptions must not be empty for constrained "
                    "generation".format(case_id)
                )
            if not constraints:
                raise BenchmarkValidationError(
                    "{}.constraints must not be empty for constrained "
                    "generation".format(case_id)
                )
        if task_type == "constrained_plan":
            if level != BenchmarkLevel.CONSTRAINED_GENERATION:
                raise BenchmarkValidationError(
                    "{}.task_type constrained_plan requires level "
                    "constrained_generation".format(case_id)
                )
            if query.language != "sparql_constraints":
                raise BenchmarkValidationError(
                    "{}.query.language must be sparql_constraints".format(
                        case_id
                    )
                )
            if expected.kind != "constraint_checks":
                raise BenchmarkValidationError(
                    "{}.expected.kind must be constraint_checks".format(case_id)
                )
            expected_values = _mapping(
                expected.values, "{}.expected.values".format(case_id)
            )
            checks = query.parameters.get("checks")
            if not isinstance(checks, list) or not checks:
                raise BenchmarkValidationError(
                    "{}.query.checks must be a non-empty array".format(case_id)
                )
            check_ids = []
            for check_index, raw_check in enumerate(checks):
                check = _mapping(
                    raw_check,
                    "{}.query.checks[{}]".format(case_id, check_index),
                )
                check_id = _string(
                    check.get("id"),
                    "{}.query.checks[{}].id".format(case_id, check_index),
                )
                _string(
                    check.get("query"),
                    "{}.query.checks[{}].query".format(case_id, check_index),
                )
                check_ids.append(check_id)
            if len(check_ids) != len(set(check_ids)):
                raise BenchmarkValidationError(
                    "{}.query.checks contains duplicate IDs".format(case_id)
                )
            if set(check_ids) != set(expected_values):
                raise BenchmarkValidationError(
                    "{}.expected.values keys must exactly match check IDs".format(
                        case_id
                    )
                )
            allowed_states = {"entailed", "not_entailed"}
            if any(
                state not in allowed_states for state in expected_values.values()
            ):
                raise BenchmarkValidationError(
                    "{}.expected.values states must be entailed or "
                    "not_entailed".format(case_id)
                )
            if (
                scoring.answer_weight
                or scoring.evidence_weight
                or scoring.constraint_weight <= 0
            ):
                raise BenchmarkValidationError(
                    "{}.scoring for constrained_plan must use only a positive "
                    "constraint_weight".format(case_id)
                )

    return BenchmarkCase(
        id=case_id,
        level=level,
        task_type=task_type,
        prompt=_string(item.get("prompt"), "{}.prompt".format(case_id)),
        query=query,
        expected=expected,
        evidence=evidence,
        scoring=scoring,
        tags=_strings(item.get("tags", ()), "{}.tags".format(case_id)),
        family_id=family_id,
        provenance=provenance,
        assumptions=assumptions,
        constraints=constraints,
        split=split,
        leakage_group=leakage_group,
    )


def parse_suite(data: Any) -> BenchmarkSuite:
    """Validate a decoded JSON value and return a benchmark suite."""

    root = _mapping(data, "suite")
    schema_version = _string(root.get("schema_version"), "schema_version")
    supported_versions = {"1.0", "2.0"}
    if schema_version not in supported_versions:
        raise BenchmarkValidationError(
            "Unsupported schema_version {!r}; expected one of: {}".format(
                schema_version, ", ".join(sorted(supported_versions))
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
    cases = tuple(
        _parse_case(item, index, schema_version)
        for index, item in enumerate(raw_cases)
    )

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
        context=_parse_context(root, schema_version),
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
