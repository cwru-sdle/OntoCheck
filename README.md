# OntoCheck

**Query-Driven Ontology Assessment for Scientific Domain Applications**

[![Project Page](https://img.shields.io/badge/Project-Page-blue)](https://cwru-sdle.github.io/OntoCheck/)
[![PyPI](https://img.shields.io/pypi/v/OntoCheck)](https://pypi.org/project/OntoCheck/)
[![Documentation](https://readthedocs.org/projects/ontocheck/badge/?version=latest)](https://ontocheck.readthedocs.io/en/latest/)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

---

## Overview

As scientific fields increasingly adopt FAIR data principles, ontologies have become essential for encoding the semantics of scientific investigations. Yet evaluating ontology quality remains a manual, technically demanding bottleneck. Current frameworks emphasize structural correctness but fail to assess practical utility against the real-world queries posed by domain scientists.

OntoCheck is an open-source Python tool that unifies domain-agnostic structural metrics with a novel, query-driven assessment methodology. By analyzing SPARQL queries derived from natural-language competency questions, OntoCheck compares the required query terms against an ontology's full vocabulary to yield complementary metrics for vocabulary coverage and utilization density. This empowers domain scientists and data engineers to make evidence-based decisions about ontology selection without requiring deep expertise in formal knowledge representation.

OntoCheck is actively developed and maintained by the **SDLE Research Center at Case Western Reserve University**.

---

## Installation

OntoCheck is available as a PyPI package: [https://pypi.org/project/OntoCheck/](https://pypi.org/project/OntoCheck/)

```bash
pip install OntoCheck
```

**Requirements:** Python 3.8 or later.

### Optional OWL reasoning

```bash
git clone https://github.com/lamng3/hermitpy.git ../hermitpy
pip install -e ../hermitpy
```

```json
"inference": { "profile": "hermit" }
```

Owlready2 runs the Java HermiT reasoner. `java -version` must work. A `JAVA_EXE` path is not required when Java is on `PATH`.

```bash
pip install owlready2
```

```json
"inference": { "profile": "owlready" }
```

---

## How It Works

OntoCheck takes a declarative configuration `C = (O, Q, M)`, where:

- **O** — Ontology: one or more ontology files under evaluation (`.ttl`).  Multiple files are merged automatically for cross-domain assessment.
- **Q** — Questions: competency questions encoded as SPARQL queries (`.json` or `.md`).  When provided, task-based Recall and Precision are computed automatically.
- **M** — Metrics: the task-agnostic evaluation metrics to compute (structural, labeling, accessibility, naming).

Users select which metrics to run and, optionally, provide competency questions — there is no need to choose a "mode."

---

## Quick Start

### Command-Line Interface

```bash
# Display available options
ontocheck -h

# Run specific task-agnostic metrics
ontocheck path/to/ontology.ttl --metrics altLabelCheck classConnections

# Run all task-agnostic metrics
ontocheck path/to/ontology.ttl --metrics all

# Run an executable benchmark suite
ontocheck path/to/ontology.ttl \
    --benchmark path/to/benchmark.json \
    --benchmark-output benchmark_results.json

# Task-based assessment (Recall / Precision)
ontocheck path/to/ontology.ttl \
    --questions competency_questions.json \
    --domain-prefixes mds

# Combined: task-based + all agnostic metrics
ontocheck path/to/ontology.ttl \
    --metrics all \
    --questions competency_questions.json \
    --domain-prefixes mds

# Cross-domain: merge multiple ontologies
ontocheck xrd.ttl capacitors.ttl \
    --questions cross_domain_questions.json \
    --domain-prefixes mds

# Custom output paths
ontocheck path/to/ontology.ttl --metrics all --log-file results.log --csv-file results.csv
```

### Python API

```python
from ontocheck import run_assessment

# Run specific task-agnostic metrics
run_assessment(
    ttl_files="path/to/ontology.ttl",
    metrics=["altLabelCheck", "classConnections", "semanticConnection"],
)

# Task-based assessment (Recall / Precision)
result = run_assessment(
    ttl_files="path/to/ontology.ttl",
    questions="competency_questions.json",
    domain_prefixes=["mds"],
    domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
)
print(f"Recall: {result['recall']:.2%}")
print(f"Precision:  {result['precision']:.2%}")

# Combined: task-based + all agnostic metrics
result = run_assessment(
    ttl_files="path/to/ontology.ttl",
    metrics="all",
    questions="competency_questions.json",
    domain_prefixes=["mds"],
)

# Cross-domain: merge multiple ontologies
result = run_assessment(
    ttl_files=["xrd.ttl", "capacitors.ttl"],
    questions="cross_domain_questions.json",
    domain_prefixes=["mds"],
)
```

---

## Available Task-Agnostic Metrics

OntoCheck provides **11 task-agnostic metrics** organized into four categories, along with a **task-based assessment methodology**.  Label and definition coverage, isolated elements, missing domains and ranges, licensing and duplicate labels are covered by the OOPS! and FOOPS! metrics (`--oops`, `--foops`; see `--list-metrics`), so OntoCheck does not duplicate them.

### Labeling

| Metric | Function | Description |
|---|---|---|
| `altLabelCheck` | `mainAltLabelCheck_v_0_0_1` | Proportion of named classes carrying synonyms |

### Structural

| Metric | Function | Description |
|---|---|---|
| `classConnections` | `count_class_connected_components` | Identifies disconnected subgraphs |
| `leafNodeCheck` | `mainLeafNodeCheck_v_0_0_1` | Identifies all leaf nodes in the ontology hierarchy |
| `semanticConnection` | `mainSemanticConnection_v_0_0_1` | Verifies grounding in upper-level ontologies (e.g., CCO, BFO) |

### Accessibility

| Metric | Function | Description |
|---|---|---|
| `sparqlEndpoint` | `check_sparql_accessibility_ttl` | Verifies reachability of the SPARQL endpoint |
| `rdfDump` | `check_rdf_dump_accessibility_ttl` | Verifies availability of the RDF data dump |
| `externalLinks` | `check_external_data_provider_links_ttl` | Checks validity of external links within the ontology |

### Naming Convention

| Metric | Function | Description |
|---|---|---|
| `classCapitalCheck` | `mainClassNameCapitalCheck_v_0_0_1` | Flags departures from standard capitalization |
| `classSpaceCheck` | `mainClassNameSpaceCheck_v_0_0_1` | Flags use of spaces in class identifiers |
| `spellCheck` | `spell_check_v_0_0_1` | Spell checking on labels and definitions |
| `searchClass` | `mainClassSearch_v_0_0_1` | Identifies classes matching a user-specified string |

### Task-Based Assessment

The task-based methodology measures how well an ontology supports analytical queries by computing two complementary metrics from SPARQL competency questions:

- **Recall** = |T_a intersection T_o| / |T_a| -- the fraction of task-required terms that the ontology defines
- **Precision** = |T_a intersection T_o| / |T_o| -- the fraction of ontology terms utilized by the task queries

where T_a is the set of domain terms extracted from the SPARQL queries and T_o is the set of domain terms defined in the ontology.

### Query Fitness

Three further metrics run alongside Recall and Precision whenever competency questions are given.  They read each question's concepts and edges from the `graph_query` of the question file, or from the triple patterns of its SPARQL.

- **Conceptual fitness** `f_c = Σ w_c · m(c, O) / Σ w_c` -- how well the questions' concepts match the ontology.  `m` is 1 for an exact match, the label similarity for a near match, 0 otherwise; `w_c` sums `|C_q| / |C_lm|` over the queries using concept `c`, where `C_lm` is the largest query.
- **Structural fitness** `f_s = Σ w_e · s(e, O) / Σ w_e` -- the weighted share of the questions' edges `A --p--> B` that belong to the ontology, through domain and range, an OWL restriction, or instance data.  `w_e` is defined like `w_c` over edges.
- **Counterfactual importance** `CI(x) = F(O) − F(O \ x)`, with `F = (f_c + f_s) / 2` -- the fitness lost if element `x` were removed.  It ranks the classes and properties the questions rely on, including ones no question names directly, such as a domain class.

### Context-Weighted Scores

Framework metrics normally count every term equally.  When competency questions are supplied, or the input is a knowledge graph with instance data, OntoCheck also reports each OOPS!, FOOPS! and OQuaRE score weighted by context, next to the unweighted score:

- **Questions** -- query terms are matched to ontology entities (exact IRIs in SPARQL, label similarity in natural language), and weight then spreads to what the answers depend on: subclasses, the domain and range classes of the properties used, and, with decay, superclasses.  Siblings and unrelated terms get no weight.
- **Instances** -- a class weighs `1 + log(1 + n)` for `n` instances (counting instances of its subclasses), so defects on well-populated classes count more.  Individuals take the weight of their classes.
- **Both** -- the weights multiply: the questions decide *what* matters, the data decides *how much*.

A defect count becomes a weighted defect rate, and an OQuaRE metric becomes a weighted mean over classes.  Metrics about the ontology document itself (metadata, licensing, accessibility) are the same for every question, so their weighted and unweighted values are equal.

```python
from ontocheck.framework_metrics import framework_report

tables = framework_report("xrd.ttl", questions="competency_questions.json",
                          domain_prefixes=["mds"])
tables["OOPS!"][["score", "unweighted", "weighted"]]
```

From the command line, `--questions` together with `--oops`, `--foops` or `--oquare` adds `Unweighted` and `Weighted` columns to the framework CSV.

---

## OntoCheck is Built for the Community

OntoCheck is conceived as a community resource: we actively encourage collaboration, contribution of new metrics, and submission of domain competency question sets, in the shared interest of building robust, reusable semantic infrastructure for FAIR scientific data.

---

## Documentation

Full documentation is available at [ontocheck.readthedocs.io](https://ontocheck.readthedocs.io/en/latest/).

---

## Authors

- Rishabh Kundu\*
- Redad Mehdi\*
- Van D. Tran\*
- Ethan Frakes
- Abhishek Daundkar
- Maliesha Sumudumalie
- Vibha S. Mandayam
- Jacob A. Lample
- Mengjie Li
- Laura S. Bruckman
- Erika I. Barcelos
- Alp Sehirlioglu
- Roger H. French
- Yinghui Wu

\* These authors contributed equally to this project.

## Affiliation

Materials Data Science for Stockpile Stewardship Center of Excellence (MDS3 COE), Case Western Reserve University, Cleveland, OH 44106, USA

---

## Acknowledgments

We are grateful to the MDS-Onto user community, who are also early users of OntoCheck, across several universities and organizations whose feedback and real-world use cases have directly shaped the tool's development. This material is based upon research in the Materials Data Science for Stockpile Stewardship Center of Excellence (MDS3 COE), and supported by the Department of Energy's National Nuclear Security Administration under Award Number DE-NA0004104. All authors thank the CWRU University Technology Center and the UCF Advanced Research Computing Center for their High Performance Computing (HPC) resources, which were utilized in this work.

---

## How to Cite

If you use OntoCheck in your work, please cite:

> Rishabh Kundu, Redad Mehdi, Van D. Tran, Ethan Frakes, Abhishek Daundkar, Maliesha Sumudumalie, Vibha S. Mandayam, Jacob A. Lample, Mengjie Li, Laura S. Bruckman, Erika I. Barcelos, Alp Sehirlioglu, Roger H. French, Yinghui Wu (2025). OntoCheck: Query-Driven Ontology Assessments for Scientific Domain Applications. [Python]. https://pypi.org/project/OntoCheck/

---

## License

OntoCheck is released under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
