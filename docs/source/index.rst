OntoCheck
=========

**Query-Driven Ontology Assessment for Scientific Domain Applications**

OntoCheck is an open-source Python tool that unifies domain-agnostic structural
metrics with a novel, query-driven assessment methodology. By analyzing SPARQL
queries derived from natural-language competency questions, OntoCheck compares
the required query terms against an ontology's full vocabulary to yield
complementary metrics for vocabulary coverage and utilization density.

This empowers domain scientists and data engineers to make evidence-based
decisions about ontology selection without requiring deep expertise in formal
knowledge representation.

Key Capabilities
----------------

- **17 task-agnostic metrics** spanning labeling quality, structural integrity,
  accessibility compliance, and naming conventions.
- **Task-based assessment** that measures vocabulary coverage (Relevance) and
  utilization density (Accuracy) against SPARQL competency questions.
- **Command-line and Python interfaces** for integration into automated
  workflows.
- **Extensible architecture** that supports user-defined metrics and
  domain-specific question sets.

Quick Install
-------------

.. code-block:: bash

   pip install OntoCheck

Getting Started
---------------

.. code-block:: bash

   # Run all task-agnostic metrics on an ontology
   ontocheck path/to/ontology.ttl --metrics all

.. code-block:: python

   from ontocheck import run_ontology_assessment, task_based_metric_v_0_0_1

   # Task-agnostic assessment
   run_ontology_assessment("ontology.ttl", metrics="all")

   # Task-based assessment against competency questions
   result = task_based_metric_v_0_0_1(
       ttl_file="ontology.ttl",
       questions="competency_questions.json",
       domain_prefixes=["mds"],
   )

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   installation
   usage

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api

.. toctree::
   :maxdepth: 1
   :caption: Additional Information

   helpers

Indices and Tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
