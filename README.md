# Introduction

OntoCheck is a Py package that provides a suite of metrics for evaluating ontology quality, usability, and compliance. It aims to support both developers by revealing potential quality gaps and users by assessing an ontology’s fitness for use across different domains.

-> Motivation

While there are established approaches for assessing linked-data quality and FAIR data compliance, there are no widely accepted standards dedicated specifically to ontology assessment. Many existing frameworks lack maintenance, and comprehensive semantic data management metrics remain underdeveloped.

-> What OntoCheck Does

OntoCheck builds on existing concepts rather than reinventing them. It brings together:

    - Linked-data assessment principles

    - FAIR-data compliance indicators

    - Semantic data management metrics

All implemented within a maintainable and user-friendly Py environment.

-> Key Features

    – combines adapted metrics from literature with new, experience-based measures

    – users can select which metrics to apply

    – generates structured evaluation summaries for easy review

    – ongoing development of feedback mechanisms to refine and expand metrics

-> Our Goal

OntoCheck strives to promote transparency and quality in ontology development. By integrating principles from linked-data and FAIR-data assessments, we aim to foster a foundation for future standardization in ontology evaluation.

We welcome feedback and contributions from the community as we continue to expand the metrics and tools offered in OntoCheck.

This tool is actively developed and maintained by the **SDLE Research Center at Case Western Reserve University**.

---

## ✍️ Authors

* Rishabh Kundu
* Redad Mehdi
* Van D. Tran
* Erika I. Barcelos
* Alp Sehirlioglu
* Yinghui Wu
* Roger H. French

---

## 🏢 Affiliation

Materials Data Science for Stockpile Stewardship Center of Excellence, Case Western Reserve University, Cleveland, OH 44106, USA

---

## 🐍 Installation

```bash
pip install OntoCheck
```

---

## ⏰ Quick Start

```bash
ontocheck -h
```

---

## 🛠️ Available Metrics in v0.0.1


For more detail visit our [Read The Docs website](https://ontology-assessment.readthedocs.io)

    "altLabelCheck": mainAltLabelCheck_v_0_0_1,
    "externalLinks": check_external_data_provider_links_ttl_v_0_0_1,
    "isolatedElements": check_for_isolated_elements_v_0_0_1,
    "humanLicense": check_human_readable_license_ttl_v_0_0_1,
    "rdfDump": check_rdf_dump_accessibility_ttl_v_0_0_1,
    "sparqlEndpoint": check_sparql_accessibility_ttl_v_0_0_1,
    "classConnections": count_class_connected_components_v_0_0_1,
    "definitionCheck": mainDefCheck_v_0_0_1,
    "duplicateLabels": find_duplicate_labels_from_graph_v_0_0_1,
    "missingDomainRange": get_properties_missing_domain_and_range_v_0_0_1,
    "leafNodeCheck": mainLeafNodeCheck_v_0_0_1,
    "semanticConnection": mainSemanticConnection_v_0_0_1,


## Example runs in command


Running metrics: altLabelCheck and humanLicense

``bash
ontocheck path/to/ontology.ttl --metrics altLabelCheck humanLicense -log-file path/to/log/file.log --csv-file path/to/file.csv
``

Results of run:

``text
--- SKOS Definition Coverage Summary ---
Total classes analyzed: 1406
Classes with definitions: 360(25.6%)
Classes without definitions: 1046 (74.4%)
Assessment: Low definition coverage
``

``text
--- Classes WITH altLabel (360) ---
Class: afe:AFE_0002281
Preferred Label: Nuclear Magnetic Resonance Tube
Alternative Labels (1):
- "NMR Tube"
Class: cco: ont00000003
Preferred Label: Designative Name
Alternative Labels (1):
- "Name"
Class: cco: ont00000009
Preferred Label: Mass Density
Alternative Labels (1):
- "Density"
``

``text
--- Classes WITHOUT altLabel (1046) ---
<https://w3id.org/ODE_AM/AMAO#AdditiveManufacturingMachine>
afe:AFE_0000029 (Label: "well-plate") afe: AFE_0000052 (Label: "cuvette") afe:AFE_0000329 (Label: "Vial")
afe:AFE_0000409 (Label: "monochromator") afe:AFE_0000718 (Label: "Tube")
afe:AFE_0001691 (Label: "non-contactprobe") afe:AFE_0001703 (Label: "pressure regulator") afe:AFE_0001772 (Label: "deuteriumlamp") afe:AFE_0002248 (Label: "probe")
afe: AFR_0001856 (Label: "electric current") afm: AFM_0000059 (Label: "additive") afm:AFM_0000884 (Label: "electricalenergy")
afm: AFM_0001032 (Label: "foam") afm:AFM_0001097 afr: AFR_0000955
afr:AFR_0002641 (Label: "viscosity")
``

Run status:


| Metric | Score | Status |
|---|---|---|
| altLabelCheck | | Success |
| humanLicense | 1 | Success |


(all metrics)

| Metric | Score | Status |
|---|---|---|
| altLabelCheck | | Success |
| externalLinks | 0.08476821 | Success |
| isolatedElements | ['Number of i... | Success |
| humanLicense | 1 | Success |
| rdfDump | 0 | Success |
| sparqlEndpoint | 0 | Success |
| classConnections | 268 | Success |
| definitionCheck | | Success |
| duplicateLabels | 51 | Success |
| missingDomains | ['count_missi... | Success |
| leafNodeCheck | | Success |
| semanticConnection | | Success |



## Acknowledge

* U.S. Department of Energy’s Office of Energy Efficiency and Renewable Energy (EERE) under the Solar Energy Technologies Office (SETO) — Agreement Numbers **DE-EE0009353** and **DE-EE0009347**
* Department of Energy (National Nuclear Security Administration) — Award Number **DE-NA0004104** and Contract Number **B647887**
* U.S. National Science Foundation — Award Number **2133576**


## How to cite package

If you use ``OntoCheck`` in your work please cite   

Rishabh Kundu, Redad Mehdi, Van D. Tran, Erika I. Barcelos, Alp Sehirlioglu, Yinghui Wu, Roger H. French (2025). OntoCheck: A package for assessing the quality and structure of ontologies. [Python]. https://pypi.org/project/OntoCheck/



