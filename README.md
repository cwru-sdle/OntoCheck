# OntoCheck

**Query-Driven Ontology Assessment for Scientific Domain Applications**

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

```bash
pip install OntoCheck
```

**Requirements:** Python 3.8 or later.

---

## Assessment Modes

OntoCheck supports four assessment modes controlled by a declarative configuration `C = (O, Q, M, G)`:

| Mode | Name | Configuration | Description |
|------|------|---------------|-------------|
| 1 | Task-agnostic | `(O, -, M, -)` | Structural, labeling, accessibility, and naming metrics |
| 2 | Task-specific Web | `(O, Q, M, G)` | Validation against KGQA benchmarks (e.g., LC-QuAD / DBpedia) |
| 3 | Task-based Scientific | `(O, Q, M, -)` | Domain ontology vs. competency questions |
| 4 | Cross-Domain | `(O[], Q, M, -)` | Merged ontologies vs. cross-domain questions |

---

## Quick Start

### Command-Line Interface

```bash
# Display available options and assessment modes
ontocheck -h

# Mode 1: Run task-agnostic metrics
ontocheck path/to/ontology.ttl --metrics altLabelCheck definitionCheck
ontocheck path/to/ontology.ttl --metrics all

# Mode 3: Task-based scientific assessment
ontocheck path/to/ontology.ttl \
    --mode 3 \
    --questions competency_questions.json \
    --domain-prefixes mds

# Mode 4: Cross-domain assessment (multiple ontologies)
ontocheck xrd.ttl capacitors.ttl \
    --mode 4 \
    --questions cross_domain_questions.json \
    --domain-prefixes mds

# Custom output paths
ontocheck path/to/ontology.ttl --metrics all --log-file results.log --csv-file results.csv
```

### Python API

```python
from ontocheck import run_ontology_assessment

# Mode 1: Run task-agnostic metrics
run_ontology_assessment(
    ttl_file="path/to/ontology.ttl",
    metrics=["altLabelCheck", "definitionCheck", "isolatedElements"],
)

# Run all task-agnostic metrics
run_ontology_assessment(
    ttl_file="path/to/ontology.ttl",
    metrics="all",
)
```

### Task-Based Assessment (Modes 3 and 4)

```python
from ontocheck import run_task_based_assessment

# Mode 3: Single ontology vs. competency questions
result = run_task_based_assessment(
    ttl_files="path/to/ontology.ttl",
    questions="competency_questions.json",
    domain_prefixes=["mds"],
    domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
)

print(f"Relevance: {result['relevance']:.2%}")
print(f"Accuracy:  {result['accuracy']:.2%}")

# Mode 4: Cross-domain -- merge multiple ontologies
result = run_task_based_assessment(
    ttl_files=["xrd.ttl", "capacitors.ttl"],
    questions="cross_domain_questions.json",
    domain_prefixes=["mds"],
)
```

### Web Ontology Assessment (Mode 2)

```python
from ontocheck import run_web_ontology_assessment

result = run_web_ontology_assessment(
    ttl_file="dbpedia_ontology.ttl",
    questions="lcquad_queries.json",
    domain_prefixes=["dbo"],
    knowledge_graph="dbpedia_kg.ttl",
)
```

### Direct Metric Access

```python
from ontocheck import task_based_metric_v_0_0_1

result = task_based_metric_v_0_0_1(
    ttl_file="path/to/ontology.ttl",
    questions="competency_questions.json",
    domain_prefixes=["mds"],
    domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
)

print(f"Relevance: {result['relevance']:.2%}")
print(f"Accuracy:  {result['accuracy']:.2%}")
```

---

## Available Metrics

OntoCheck provides **17 task-agnostic metrics** organized into four categories, along with a **task-based assessment methodology**.

### Labeling

| Metric | Function | Description |
|---|---|---|
| `checkLabel` | `mainLabelCheck_v_0_0_1` | Proportion of named classes carrying human-readable identifiers |
| `altLabelCheck` | `mainAltLabelCheck_v_0_0_1` | Proportion of named classes carrying synonyms |
| `definitionCheck` | `mainDefCheck_v_0_0_1` | Proportion of named classes carrying formal definitions |

### Structural

| Metric | Function | Description |
|---|---|---|
| `isolatedElements` | `check_for_isolated_elements` | Identifies orphaned classes within the ontology |
| `classConnections` | `count_class_connected_components` | Identifies disconnected subgraphs |
| `missingDomainRange` | `get_properties_missing_domain_and_range` | Identifies undeclared domain and range restrictions |
| `leafNodeCheck` | `mainLeafNodeCheck_v_0_0_1` | Identifies all leaf nodes in the ontology hierarchy |
| `semanticConnection` | `mainSemanticConnection_v_0_0_1` | Verifies grounding in upper-level ontologies (e.g., CCO, BFO) |

### Accessibility

| Metric | Function | Description |
|---|---|---|
| `sparqlEndpoint` | `check_sparql_accessibility_ttl` | Verifies reachability of the SPARQL endpoint |
| `rdfDump` | `check_rdf_dump_accessibility_ttl` | Verifies availability of the RDF data dump |
| `humanLicense` | `check_human_readable_license_ttl` | Verifies presence and fitness of licensing information |
| `externalLinks` | `check_external_data_provider_links_ttl` | Checks validity of external links within the ontology |

### Naming Convention

| Metric | Function | Description |
|---|---|---|
| `classCapitalCheck` | `mainClassNameCapitalCheck_v_0_0_1` | Flags departures from standard capitalization |
| `classSpaceCheck` | `mainClassNameSpaceCheck_v_0_0_1` | Flags use of spaces in class identifiers |
| `spellCheck` | `spell_check_v_0_0_1` | Spell checking on labels and definitions |
| `duplicateLabels` | `find_duplicate_labels_from_graph` | Identifies duplicate labels across entities |
| `searchClass` | `mainClassSearch_v_0_0_1` | Identifies classes matching a user-specified string |

### Task-Based Assessment

The task-based methodology measures how well an ontology supports analytical queries by computing two complementary metrics from SPARQL competency questions:

- **Relevance** = |T_a intersection T_o| / |T_a| -- the fraction of task-required terms that the ontology defines
- **Accuracy** = |T_a intersection T_o| / |T_o| -- the fraction of ontology terms utilized by the task queries

where T_a is the set of domain terms extracted from the SPARQL queries and T_o is the set of domain terms defined in the ontology.

---

## Documentation

Full documentation is available at [ontocheck.readthedocs.io](https://ontocheck.readthedocs.io/en/latest/).

---

## Authors

- Rishabh Kundu
- Redad Mehdi
- Van D. Tran
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

## Affiliation

Materials Data Science for Stockpile Stewardship Center of Excellence (MDS3 COE), Case Western Reserve University, Cleveland, OH 44106, USA

---

## Acknowledgments

- Materials Data Science for Stockpile Stewardship Center of Excellence (MDS3 COE), Case Western Reserve University
- University of Central Florida Advanced Research Computing Center
- Case Western Reserve University High Performance Computing (HPC) resources

---

## How to Cite

If you use OntoCheck in your work, please cite:

> Rishabh Kundu, Redad Mehdi, Van D. Tran, Ethan Frakes, Abhishek Daundkar, Maliesha Sumudumalie, Vibha S. Mandayam, Jacob A. Lample, Mengjie Li, Laura S. Bruckman, Erika I. Barcelos, Alp Sehirlioglu, Roger H. French, Yinghui Wu (2025). OntoCheck: Query-Driven Ontology Assessments for Scientific Domain Applications. [Python]. https://pypi.org/project/OntoCheck/

---

## License

OntoCheck is released under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
