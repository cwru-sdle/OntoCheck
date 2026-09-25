# Scientific Competency Benchmark Framework

## Status

This is the canonical architecture and research roadmap for extending
OntoCheck beyond vocabulary coverage. The existing `task_based_metric.py`
remains supported while the benchmark runner is provided as a separate API.

Implemented baseline:

- versioned suite models and JSON validation;
- extensible task-type evaluator and inference-profile reasoner registries;
- SPARQL `SELECT` and `ASK` fact-retrieval scoring;
- explicit transitive graph-path deduction with machine-checkable proofs;
- structured contextual summaries assembled from grounded SPARQL sections;
- explicit SPARQL constraint checks for ontology-grounded scientific plans;
- schema 2.0 context, provenance, leakage, assumption, and constraint fields;
- linked four-level XRD and Materials Processing pilot families;
- case-level and grouped suite results with JSON output;
- deterministic loader and end-to-end tests.

The CLI accepts `--benchmark` and `--benchmark-output`. Production external
reasoner adapters are not implemented yet.

Validation includes unit tests for schema parsing, duplicate IDs, invalid
weights, retrieval, expected-answer mismatches, malformed summary sections,
non-transitive graph paths, proof scoring, result serialization, and reasoner
replacement. Regression tests run the real XRD and Materials Processing
pilots and assert retrieval, deduction, proof, summary, constraint, and
context results.

## Scientific Motivation

OntoCheck evaluates whether a scientific ontology is useful in a specific,
evolving context:

```text
(ontology version, data snapshot, scientific task, measure, inference profile)
```

It does not reduce ontology quality to a static, purpose-independent score.
The benchmark provides evidence and design guardrails for scientific
knowledge representation, hypothesis work, AI science agents, validation,
explanation, and discovery.

The design is informed by, but does not copy or vendor code from:

- [GraphRAG-Bench](https://arxiv.org/abs/2506.05690), for evidence-structured
  competency levels and stage-specific evaluation;
- [BRINK](https://aclanthology.org/2026.eacl-long.114/), for paired complete
  and incomplete graphs that distinguish retrieval from reasoning; and
- [KGrEaT](https://arxiv.org/abs/2308.10537), for controlled downstream-task
  comparisons where the knowledge graph is the experimental variable.

The deterministic, offline runner remains authoritative. Future optional
third-party packages must be version-pinned and license-documented. GraphRAG
or LLM systems may integrate through adapters, but may not replace
deterministic benchmark scores.

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
  "schema_version": "2.0",
  "suite_id": "materials-xrd-v1",
  "domain": "materials-science",
  "context": {
    "ontology_version": "xrd-v1",
    "ontology_commit": "ontology-commit-sha",
    "data_version": "xrd-pilot-v1",
    "data_commit": "data-commit-sha",
    "metric_version": "ontocheck-benchmark-v2"
  },
  "namespaces": {
    "mds": "https://cwrusdle.bitbucket.io/mds/"
  },
  "inference": {
    "profile": "graph_path"
  },
  "cases": [
    {
      "id": "xrd-reason-001",
      "family_id": "xrd-lpbf-process",
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
      "provenance": {
        "sources": ["SupplementaryMaterials/Ontologies/XRD.ttl"],
        "curator": "benchmark-team",
        "reviewers": ["domain-reviewer"]
      },
      "split": "test",
      "leakage_group": "xrd-lpbf-process",
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
invalid weights. Schema 2.0 additionally requires version pins, a question
family, source provenance, an explicit split, and a leakage group. Constrained
generation cases must declare assumptions and constraints. Schema 1.0 remains
readable for compatibility. The runner reports an unregistered task type as
an explicit case failure, allowing separately registered future task types.

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

Adapters used by `constrained_plan` cases must also implement the
`MaterializingReasoner` capability:

```python
materialize(graph) -> Graph
```

This makes the graph used by ASK checks reflect the suite's declared
inference profile. Profiles used only for deduction do not need this optional
capability.

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

Status: deterministic constraint-check baseline implemented.

A `constrained_plan` case supplies explicit assumptions, scientific
constraints, and named SPARQL `ASK` checks. The evaluator reports each check
as `entailed` or `not_entailed`, a constraint-satisfaction score, violations,
and unsupported required claims. `not_entailed` is deliberately not called
false or contradicted under the open-world assumption.

Checks are restricted to positive basic-graph-pattern `ASK` queries;
aggregation, subqueries, filters, and closed-world constructs are rejected.
Under the `graph_path` profile, ASK queries run against a materialized closure
of `rdfs:subClassOf`,
`rdfs:subPropertyOf`, and explicitly declared transitive properties. The
`required_claims` and `source_ids` fields are provenance metadata for review;
the named executable checks, rather than the prose, determine the score.

The baseline evaluates whether an ontology supports a structured candidate
plan; it does not generate prose or claim empirical causality. Future agent
adapters may propose plans, but they must emit the same explicit checks and
may not replace deterministic scoring.

## Result Model

Each case result records:

- case ID, level, task type, status, and evaluator version;
- answer score, evidence score, constraint score, and weighted total;
- actual normalized answer and evidence;
- violations, unsupported claims, and diagnostics;
- runtime and declared inference profile.

Suite reports aggregate by level and task type before computing an overall
score. A strong fact-retrieval score must not hide weak reasoning performance.

## Ontology-Aware and Downstream Evaluation

Strict IRI, literal, answer-set, and proof matching remains authoritative.
Ontology-aware closeness is a planned secondary diagnostic and must report
the path or matching witness that produced partial credit. Candidate measures
include declared equivalence, lowest-common-subsumer and information-content
similarity, allowlisted weighted paths, and maximum-weight matching between
predicted and reference claim sets. Relation weights, corpora, thresholds,
and normalization rules must be versioned. Learned ontology embeddings may
be reported as an ablation, but not as the sole quality measure.

Three downstream task families are planned:

1. **Evidence retrieval:** rank entities, triples, and proof paths. Report
   strict precision/recall/F1, MRR, nDCG, path recall, ontology-aware soft
   precision/recall/F1, latency, and unmapped-entity rate.
2. **Hierarchical scientific classification:** classify samples, processes,
   measurements, or claims. Report exact and hierarchical macro-F1, balanced
   accuracy, MCC, abstention coverage-risk, and distance to the correct class.
3. **Claim and hypothesis validation:** classify claims as entailed,
   contradicted, or unknown and return evidence. Report per-class and
   macro-F1, MCC, calibration, proof precision/recall, unsupported-claim rate,
   and constraint violations.

To isolate ontology contribution, hold data, splits, models, mappings, random
seeds, and resource budgets constant while comparing:

1. no ontology;
2. labels and synonyms only;
3. class inventory without hierarchy;
4. the full asserted ontology;
5. the ontology plus declared inference;
6. the previous ontology version; and
7. a degree-preserving edge-shuffled negative control.

Report paired score deltas with confidence intervals. Report mapped-known and
all-entity results separately so poor coverage cannot be hidden by discarding
unmapped examples.

## Roadmap and Release Guardrails

Completed:

1. Versioned benchmark models, schema validation, registries, result
   serialization, and CLI integration.
2. Reproducibility context, provenance, evidence, leakage, assumption, and
   constraint fields.
3. Linked XRD and Materials Processing pilots covering retrieval, reasoning,
   structured summary, and constrained planning.
4. Deterministic graph-path proofs, summary scoring, materialized entailment,
   and positive constraint checks.

Next:

1. Add ontology-aware scoring and the three downstream task adapters.
2. Add complete/incomplete graph pairs, label masking, ontology ablations,
   and version regressions.
3. Add optional OWL consistency and SHACL constraint adapters with clearly
   separated semantics.
4. Publish multidimensional result artifacts to the leaderboard.
5. Expand to Capacitors, EBSD, Geospatial, GeoOutage, and cross-domain agent
   scenarios after domain review.

Each change must include accepted/rejected schema tests, deterministic
evaluator tests, malformed and empty cases, proof and open-world edge cases,
CLI coverage, and representative domain fixtures. Larger downstream adapters
should be delivered as reviewable follow-up changes.

No benchmark result is release-ready until its prompts, answers, evidence,
assumptions, constraints, and forbidden inferences have been reviewed by a
domain expert. The current pilot reviewer marker `domain-review-required`
therefore identifies executable research fixtures, not expert-approved gold
standards.

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
