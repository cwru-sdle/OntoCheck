# OntoCheck Repository Guide

OntoCheck is a Python package and CLI for structural and competency-question
assessment of Turtle ontologies.

## Repository Map

- `src/ontocheck/`: package, CLI, assessment runner, and metrics.
- `src/ontocheck/benchmark/`: executable suites, evaluators, and reasoner adapters.
- `src/ontocheck/task_based_metric.py`: current SPARQL vocabulary-overlap metric.
- `SupplementaryMaterials/Ontologies/`: example ontology fixtures.
- `SupplementaryMaterials/SPARQL_Queries/`: domain question sets and queries.
- `SupplementaryMaterials/Benchmarks/`: executable benchmark suites.
- `docs/source/`: editable Sphinx documentation; `docs/build/` is generated.
- `docs/benchmark-framework.md`: benchmark architecture and implementation plan.
- `pyproject.toml`: package metadata, dependencies, and `ontocheck` entry point.

## Core Flow

`ontocheck.cli` parses arguments, `run_assessment` coordinates selected metrics,
and metric modules parse RDF with `rdflib` and write log/CSV results. Keep CLI,
orchestration, evaluation, and reporting concerns separate.

## Development

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/ontocheck SupplementaryMaterials/Ontologies/XRD.ttl \
  --metrics definitionCheck
```

- Support the minimum Python version declared in `pyproject.toml`.
- Follow PEP 8; type and document new public APIs.
- Use `pathlib`, UTF-8, and `logging`; avoid import-time side effects.
- Keep reusable assessment logic domain-neutral—never hardcode MDS vocabulary.
- Preserve public behavior unless a breaking change is explicitly requested.

## Verification

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover \
  -s tests/benchmark -p 'test_*.py' -v
```

- Add deterministic tests with small local ontology fixtures.
- Cover success, malformed/empty input, and logic-specific edge cases.
- Verify result contents and error statuses, not only process exit codes.
- Run focused tests plus one representative CLI assessment.
- Do not edit generated docs or commit environments, caches, reports, or secrets.

Update this guide when repository structure or standard workflows change; keep
detailed feature design in dedicated documentation.
