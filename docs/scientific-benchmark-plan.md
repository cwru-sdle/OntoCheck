# Scientific Ontology Benchmark Plan

## Purpose

OntoCheck should evaluate whether a scientific ontology is useful in a
specific, evolving context:

```text
(ontology version, data snapshot, scientific task, measure, inference profile)
```

It must not reduce ontology quality to a static, domain-independent score.
The benchmark is intended to provide evidence and design guardrails for
scientific knowledge representation, hypothesis work, AI science agents,
validation, explanation, and discovery.

## Relationship to Existing Work

The design is informed by, but does not copy or vendor code from:

- [GraphRAG-Bench](https://arxiv.org/abs/2506.05690), for evidence-structured
  competency levels and stage-specific evaluation;
- [BRINK](https://aclanthology.org/2026.eacl-long.114/), for paired complete
  and incomplete graphs that distinguish retrieval from reasoning; and
- [KGrEaT](https://arxiv.org/abs/2308.10537), for controlled downstream-task
  comparisons where the knowledge graph is the experimental variable.

OntoCheck's deterministic runner remains the core. Optional third-party
packages must be pinned and documented with their licenses. GraphRAG and LLM
systems may later integrate through adapters, but are not required by the
offline benchmark and may not replace its deterministic scores.

## Competency Levels

Each scientific scenario should form a question family linked by a stable
`family_id`.

1. **Fact retrieval:** retrieve an explicitly asserted entity, value, unit, or
   relation.
2. **Complex reasoning:** derive an answer through declared hierarchy,
   inversion, symmetry, composition, or another validated rule and return its
   proof.
3. **Contextual summarization:** assemble a structured, claim-level account
   from multiple ontology fragments while retaining evidence.
4. **Constrained scientific generation:** construct or evaluate a hypothesis,
   experiment, or process plan without violating ontology and data
   constraints. Claims must be labeled `entailed`, `assumed`, or
   `hypothetical`.

The first pilot covers XRD and Materials Processing. It should include paired
complete/incomplete cases, multi-answer gold sets, and opaque-identifier
variants where they test memorization rather than scientific accessibility.

## Evidence and Guardrails

Every benchmark case should identify:

- ontology and data versions or commit hashes;
- source records, publications, or fixture identifiers;
- gold answer entities, triples, claims, and accepted proof paths;
- inference profile and metric version;
- assumptions, constraints, and forbidden inferences;
- split and leakage group; and
- curator and reviewer information.

The runner must keep these outcomes distinct:

- entailed;
- contradicted by explicit negation or disjointness;
- unknown under the open-world assumption; and
- invalid under a closed-world constraint such as SHACL.

Statistically mined rules are candidates for expert review, not logical
axioms. A high-confidence association must never be reported as an entailment
without a declared formal or expert-approved rule.

## Ontology-Aware Scoring

Strict IRI, literal, answer-set, and proof matching is authoritative.
Ontology-aware closeness is a secondary diagnostic and must report the path or
matching witness that produced partial credit.

The planned closeness service combines:

- exact identity and declared equivalence;
- lowest-common-subsumer and information-content similarity for classes;
- weighted shortest paths over an allowlist of relation types; and
- maximum-weight bipartite matching for predicted and reference claim sets.

All relation weights, information-content corpora, thresholds, and
normalization rules must be versioned. Learned ontology embeddings may be
reported as an ablation, not used as the sole quality measure.

## Downstream Tasks

### Evidence retrieval

Rank entities, triples, and proof paths for a competency question. Report
strict precision/recall/F1, MRR, nDCG, path recall, ontology-aware soft
precision/recall/F1, latency, and unmapped-entity rate.

### Hierarchical scientific classification

Classify samples, processes, measurements, or claims into ontology classes.
Report exact and hierarchical macro-F1, balanced accuracy, MCC, abstention
coverage-risk, and distance to the correct class.

### Claim and hypothesis validation

Classify claims as entailed, contradicted, or unknown and return evidence.
Report per-class and macro-F1, MCC, calibration, proof precision/recall,
unsupported-claim rate, and constraint violations.

## Isolating Ontology Contribution

Use identical data, splits, models, mappings, random seeds, and resource
budgets while varying only:

1. no ontology;
2. labels and synonyms only;
3. class inventory without hierarchy;
4. full asserted ontology;
5. ontology plus declared inference;
6. previous ontology version; and
7. a degree-preserving edge-shuffled negative control.

Report paired score deltas with confidence intervals. Report mapped-known and
all-entity results separately so that poor coverage cannot be hidden by
discarding unmapped examples.

## Delivery Phases

1. Integrate the current executable benchmark foundation without breaking the
   existing task-based API.
2. Add versioned context, provenance, evidence, leakage, and guardrail fields
   to the suite schema.
3. Build and review linked XRD and Materials Processing pilot families.
4. Add deterministic reasoning, summary, and constrained-plan evaluators.
5. Add ontology-aware scoring and the three downstream-task adapters.
6. Run ontology ablations, incomplete-graph tests, and version regressions.
7. Publish multidimensional result artifacts to the leaderboard.
8. Expand to Capacitors, EBSD, Geospatial, GeoOutage, and cross-domain agent
   scenarios after domain review.

## Testing and Pull Requests

The executable foundation and first pilot belong in the existing benchmark
pull request. Larger downstream-task adapters should follow in smaller pull
requests.

Each pull request must include:

- schema validation tests for accepted and rejected inputs;
- deterministic evaluator unit tests, including empty and malformed cases;
- proof, provenance, open-world, and constraint edge cases;
- complete/incomplete and label-masking regressions;
- end-to-end XRD and Materials Processing fixture tests;
- CLI success and failure tests;
- compatibility coverage for the minimum and current Python versions; and
- recorded commands and result summaries in the pull request description.

No benchmark result is release-ready until its prompts, answers, evidence,
assumptions, and forbidden inferences have been reviewed by a domain expert.
