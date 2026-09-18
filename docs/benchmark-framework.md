# Competency Benchmark Framework

## Status

This document is the implementation plan for extending OntoCheck beyond
vocabulary coverage. The existing `task_based_metric.py` remains supported
while the benchmark runner is introduced as a separate API.

Implemented baseline:

- versioned suite models and JSON validation;
- extensible task-type evaluator and inference-profile reasoner registries;
- SPARQL `SELECT` and `ASK` fact-retrieval scoring;
- explicit transitive graph-path deduction with machine-checkable proofs;
- structured contextual summaries assembled from grounded SPARQL sections;
- case-level and grouped suite results with JSON output;
- deterministic loader and end-to-end tests.

The CLI accepts `--benchmark` and `--benchmark-output`. Production external
reasoner adapters are not implemented yet.

Validation includes unit tests for schema parsing, duplicate IDs, invalid
weights, retrieval, expected-answer mismatches, malformed summary sections,
non-transitive graph paths, proof scoring, result serialization, and reasoner
replacement. A separate regression test runs the real XRD pilot and asserts
its expected deduction, proof, summary sections, and scores.

## Goals

- Run the same benchmark model against ontologies from any domain.
- Separate fact retrieval, reasoning, summarization, and hypothetical tasks.
- Cover deduction, multiple choice, proof generation, and consistency checks.
- Evaluate answers, evidence, and logical behavior—not only referenced terms.
- Produce deterministic case-level and aggregate machine-readable results.

Natural-language fluency is not evidence of ontology quality. Summary and
generation tasks therefore require grounded claims and explicit constraints.

## Benchmark Levels

| Level | Name | Required behavior | Primary scoring |
|---|---|---|---|
| 1 | Fact retrieval | Retrieve explicitly asserted facts | exact/set match |
| 2 | Complex reasoning | Chain facts or apply a declared inference regime | answer + proof |
| 3 | Contextual summarization | Organize distributed facts into a grounded structured answer | fact coverage + faithfulness |
| 4 | Constrained generation | Solve a hypothetical scenario without violating ontology constraints | constraint satisfaction + grounding |

Level 4 is deliberately constrained rather than scored for subjective
"creativity." Generated statements must be labeled as entailed, assumed, or
hypothetical.

## Package Layout

```text
src/ontocheck/benchmark/
├── __init__.py
├── models.py      # Suite, case, expectation, evidence, and result models
├── io.py          # JSON loading, validation, and result serialization
├── evaluators.py  # Task evaluator protocol, registry, and scoring
├── reasoners.py   # Reasoner protocol, registry, and graph-path adapter
└── runner.py      # Graph loading, case dispatch, and suite aggregation

tests/benchmark/
├── fixtures/      # Small synthetic ontologies and suites
├── test_io.py
└── test_runner.py
```

Evaluators receive a validated case and graph context and return a common
`CaseResult`. This registry design allows new task types without adding
domain-specific branches to the runner.

Reasoning is intentionally isolated from task scoring. This fifth module is
justified because external reasoners have independent runtime, serialization,
configuration, and failure-handling concerns. Split further only when a
concrete adapter requires it; do not create empty modules in anticipation of
future features.

## Suite Schema

Use versioned JSON for executable benchmarks. Existing question files can be
adapted incrementally; they do not need an immediate destructive migration.

```json
{
  "schema_version": "1.0",
  "suite_id": "materials-xrd-v1",
  "domain": "materials-science",
  "namespaces": {
    "mds": "https://cwrusdle.bitbucket.io/mds/"
  },
  "inference": {
    "profile": "graph_path"
  },
  "cases": [
    {
      "id": "xrd-reason-001",
      "level": "complex_reasoning",
      "task_type": "deduction",
      "prompt": "Which class is two subclass levels above LPBF?",
      "query": {
        "language": "graph_path",
        "source": "mds:LaserPowderBedFusion",
        "predicate": "rdfs:subClassOf",
        "min_hops": 2,
        "max_hops": 2
      },
      "expected": {
        "kind": "result_set",
        "values": ["mds:ProcessingMethod"]
      },
      "evidence": {
        "required_paths": [
          [
            "mds:LaserPowderBedFusion",
            "rdfs:subClassOf",
            "mds:AdditiveManufacturingProcess",
            "rdfs:subClassOf",
            "mds:ProcessingMethod"
          ]
        ]
      },
      "scoring": {
        "answer_weight": 0.7,
        "evidence_weight": 0.3
      },
      "tags": ["multi-hop", "two-hop"]
    }
  ]
}
```

Validation rejects duplicate IDs, unknown levels, missing expectations, and
invalid weights. The runner reports an unregistered task type as an explicit
case failure, allowing separately registered future task types.

## Evaluation Semantics

### Retrieval

- Execute deterministic SPARQL `SELECT` or `ASK`.
- Normalize RDF terms before exact, ordered, or set comparison.
- Record precision, recall, and F1 for result sets where partial credit applies.

### Reasoning and proof

- Every case declares its inference profile; never infer silently.
- Initial profiles are `none` and `graph_path`.
- `graph_path` performs bounded traversal only for `rdfs:subClassOf`,
  `rdfs:subPropertyOf`, or properties explicitly declared transitive.
- Current limitation: graph-path deduction follows the same predicate at every
  hop; arbitrary mixed-relation deductions and property chains are not yet
  supported.
- Add HermiT later as an optional OWL 2 DL reasoner adapter for entailment and
  ontology consistency. Keep the baseline runner usable without Java.
- Proof cases compare required supporting triples or accepted alternative paths.
- Multiple-choice cases score the selected option and retain its evidence.
- HermiT does not execute arbitrary mined Horn rules. If AMIE-style rule
  execution is added, expose it through a separate inference adapter while
  preserving the same runner interface.

Reasoners are selected by inference-profile name through `ReasonerRegistry`.
An external adapter implements `reason(case, graph)` and returns RDF answers
with proof steps; the evaluator normalizes them for scoring. The runner and
deduction evaluator do not depend on a specific backend.

## Graph-Path Reasoning

Status: implemented as the first reasoner adapter.

`GraphPathReasoner` performs deterministic breadth-first traversal from a
source RDF resource through one transitive predicate. A benchmark case controls
the minimum and maximum hop count. Only named resources are returned, so OWL
restriction blank nodes do not become accidental answers.

The adapter accepts:

- `rdfs:subClassOf`;
- `rdfs:subPropertyOf`; or
- a custom predicate explicitly typed as `owl:TransitiveProperty`.

It intentionally rejects arbitrary predicates because chaining an undeclared
relation does not establish a logically entailed conclusion.

For every answer, the result records:

- normalized answer IRI;
- shortest hop count;
- whether the source-to-answer conclusion was inferred;
- the ordered proof path; and
- whether each proof step was explicitly asserted in the input graph.

The XRD pilot in
`SupplementaryMaterials/Benchmarks/XRD-graph-path.json` verifies:

```text
LaserPowderBedFusion
  --rdfs:subClassOf--> AdditiveManufacturingProcess
  --rdfs:subClassOf--> ProcessingMethod
```

The two asserted edges support the inferred transitive conclusion that
`LaserPowderBedFusion` is a subclass of `ProcessingMethod`. The benchmark
scores both the answer and the expected proof path.

Run the pilot through the Python API:

```python
from ontocheck.benchmark import run_suite, write_result

result = run_suite(
    "SupplementaryMaterials/Benchmarks/XRD-graph-path.json",
    "SupplementaryMaterials/Ontologies/XRD.ttl",
)
write_result(result, "xrd-graph-path-result.json")
```

### Reasoner extension point

`ReasonerRegistry` maps the suite's inference profile to a reasoner object.
Each adapter implements:

```python
reason(case, graph) -> list[ReasonerAnswer]
```

This keeps graph traversal, HermiT, and future reasoners behind the same
boundary. A future HermiT adapter may translate the RDF graph to its Java/API
representation, execute OWL 2 DL entailment or consistency checks, and convert
its output to `ReasonerAnswer` objects. No HermiT-specific branch belongs in
the runner or benchmark schema.

The dependency direction is:

```text
runner -> evaluators -> reasoner protocol
   |                       ^
   +---- reasoner registry-+
                           |
                    graph path / HermiT / other adapters
```

Evaluators score benchmark tasks; reasoners derive candidate answers and
evidence. A reasoner must not know scoring weights or report formats.

Current graph-path limitations:

- one predicate per traversal—mixed-relation deduction is not supported;
- shortest proof path only;
- no arbitrary property chains;
- no OWL class-expression reasoning;
- no contradiction or global consistency checking.

### Logical consistency

Keep these checks distinct:

- **Entailment:** a conclusion follows under the declared profile.
- **Non-entailment:** a conclusion cannot be derived; this is not automatically
  proof of its negation under the open-world assumption.
- **Explicit negation/disjointness:** contradictory assertions or class axioms
  are present.
- **Constraints:** data violates declared SHACL-like closed-world requirements.
- **Transitivity:** a declared transitive relation supports a multi-hop result.

OWL consistency and data constraint validation are different tasks and must
not share a single ambiguous "consistent" score.

### Contextual summarization

Status: initial structured baseline implemented.

A `contextual_summary` case uses the `sparql_summary` query language. Its
`sections` array contains independently executable, named SPARQL `SELECT`
queries. The evaluator combines their results into one structured summary and
compares each section with its expected claims.

The executable target is a structured collection of claims, groups, and
relationships. Current scoring reports:

1. macro-average required-claim coverage;
2. macro-average relevance against the reference claims;
3. answer F1 across sections;
4. faithfulness and unsupported-claim rate.

All current claims come directly from successful graph queries, so they are
grounded by construction: faithfulness is `1.0` and unsupported-claim rate is
`0.0`. Relevance still penalizes graph-derived claims that are not part of the
reference summary.

The XRD pilot summarizes Laser Powder Bed Fusion across four fragments:
identity, aliases, direct classification, and promoted process behavior. This
demonstrates synthesis across separate ontology structures rather than a
single fact lookup.

Current limitations:

- output is structured JSON, not generated prose;
- cross-section contradiction and coherence checks are not implemented;
- summary claims do not yet retain proof paths;
- external text-generation quality is not scored.

Natural-language generation can later be an adapter, but the baseline runner
must continue to work without an external model or network access.

### Constrained generation

A case supplies a scenario, assumptions, required goals, and forbidden
constraints. The evaluator checks whether the proposed RDF changes or
structured plan are grounded and constraint-satisfying. Novelty is reported
only as an optional descriptive measure.

## Result Model

Each case result records:

- case ID, level, task type, status, and evaluator version;
- answer score, evidence score, constraint score, and weighted total;
- actual normalized answer and evidence;
- violations, unsupported claims, and diagnostics;
- runtime and declared inference profile.

Suite reports aggregate by level and task type before computing an overall
score. A strong fact-retrieval score must not hide weak reasoning performance.

## Implementation Phases

1. **Foundation:** four-module package, models, JSON validation, evaluator
   registry, result serialization, and synthetic fixtures.
2. **Executable baseline:** retrieval, exact/set scoring, CLI integration, and
   conversion of a small existing XRD subset.
3. **Reasoning:** multi-hop deduction, transitivity, multiple choice, and proof
   evidence using explicit SPARQL semantics.
4. **Consistency:** entailment/non-entailment cases followed by the optional
   HermiT adapter when its runtime is available.
5. **Summarization:** structured claim targets, coverage, faithfulness, and
   evidence scoring.
6. **Constrained generation:** hypothetical graph/plan outputs and constraint
   satisfaction.
7. **Domain expansion:** balanced benchmark suites for materials, geospatial,
   outage, EBSD, capacitors, and cross-domain cases.

The first implementation slice should complete phases 1 and 2 with one small
fixture for each supported result kind. It should not add an LLM dependency.

## Open Design Decisions

- HermiT process boundary and interchange format when the reasoner is supplied.
- Execution semantics for any future AMIE-style Horn-rule engine.
- Whether closed-world constraints use SHACL and which implementation.
- Canonical proof representation when several valid paths exist.
- Weighting policy across answer, evidence, and constraints.
- How benchmark ontology data is separated from expected answers to prevent
  leakage.

These decisions should be resolved with small fixtures and measured behavior
before converting all existing competency questions.
