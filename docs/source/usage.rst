Usage Guide
===========

OntoCheck provides two interfaces: a command-line tool for quick assessments
and a Python API for programmatic use and integration into data pipelines.

All assessments require an ontology serialized in Turtle (``.ttl``) format.
The input file must be free of syntax errors.

Command-Line Interface
----------------------

The ``ontocheck`` command runs one or more task-agnostic metrics on a Turtle
file and produces a log file and a CSV results summary.

.. code-block:: bash

   ontocheck <ttl_file> --metrics <metric1> [<metric2> ...] [options]

**Arguments:**

``ttl_file``
   Path to the input Turtle ontology file.

``--metrics``
   One or more metric names to run, or ``all`` to run every available metric.

``--log-file``
   Path for the output log file (default: ``assessment.log``).

``--csv-file``
   Path for the output CSV results file (default: ``assessment_scores.csv``).

Examples
^^^^^^^^

Run two specific metrics:

.. code-block:: bash

   ontocheck my_ontology.ttl --metrics altLabelCheck definitionCheck

Run all available metrics with custom output paths:

.. code-block:: bash

   ontocheck my_ontology.ttl --metrics all --log-file results.log --csv-file results.csv

Python API
----------

Task-Agnostic Assessment
^^^^^^^^^^^^^^^^^^^^^^^^

The :func:`~ontocheck.run_assessment.run_ontology_assessment` function runs one or
more task-agnostic metrics on a Turtle file.

.. code-block:: python

   from ontocheck import run_ontology_assessment

   # Run selected metrics
   run_ontology_assessment(
       ttl_file="my_ontology.ttl",
       metrics=["altLabelCheck", "isolatedElements", "semanticConnection"],
       output_log_file="assessment.log",
       output_csv_file="scores.csv",
   )

   # Run all metrics
   run_ontology_assessment(
       ttl_file="my_ontology.ttl",
       metrics="all",
   )

Each metric takes a Turtle file as input and returns a score or diagnostic
report. Results are written to the log file and aggregated in the CSV output.

Task-Based Assessment
^^^^^^^^^^^^^^^^^^^^^

The :func:`~ontocheck.task_based_metric.task_based_metric` function evaluates an
ontology against competency questions encoded as SPARQL queries. It computes
two complementary metrics:

- **Relevance** (Recall) = \|T_a intersection T_o\| / \|T_a\| -- the fraction
  of task-required terms that the ontology defines.
- **Accuracy** (Precision) = \|T_a intersection T_o\| / \|T_o\| -- the
  fraction of ontology terms utilized by the task queries.

.. code-block:: python

   from ontocheck import task_based_metric

   result = task_based_metric(
       ttl_file="my_ontology.ttl",
       questions="competency_questions.json",
       domain_prefixes=["mds"],
       domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
   )

   print(f"Relevance: {result['relevance']:.2%}")
   print(f"Accuracy:  {result['accuracy']:.2%}")
   print(f"Ontology terms (T_o): {result['T_o_count']}")
   print(f"Task terms (T_a):     {result['T_a_count']}")
   print(f"Intersection:         {result['intersection']}")

**Supplying questions.** The ``questions`` parameter accepts three formats:

1. **JSON file path** (ending in ``.json``): Each element of the JSON array
   should contain a ``sparql_query`` key with a SPARQL query string.

2. **Markdown file path** (ending in ``.md``): SPARQL queries are extracted from
   fenced code blocks marked with ``sparql``.

3. **List of strings**: Raw SPARQL query strings passed directly.

.. code-block:: python

   # From a list of SPARQL query strings
   queries = [
       "SELECT ?x WHERE { ?x a mds:Sample }",
       "SELECT ?x WHERE { ?x mds:hasMaterialComposition ?comp }",
   ]

   result = task_based_metric(
       ttl_file="my_ontology.ttl",
       questions=queries,
       domain_prefixes=["mds"],
   )

**Inspecting gaps.** The returned dictionary includes diagnostic sets for
identifying vocabulary gaps:

.. code-block:: python

   # Terms the tasks require but the ontology lacks
   for term in sorted(result['missing_from_onto']):
       print(f"  Missing: {term}")

   # Ontology terms not exercised by any task query
   print(f"Unused ontology terms: {len(result['unused_in_onto'])}")

Available Metric Names
----------------------

The following metric names can be passed to the ``--metrics`` CLI argument
or the ``metrics`` parameter of ``run_ontology_assessment``:

**Labeling:**
``checkLabel``, ``altLabelCheck``, ``definitionCheck``

**Structural:**
``isolatedElements``, ``classConnections``, ``missingDomainRange``,
``leafNodeCheck``, ``semanticConnection``

**Accessibility:**
``sparqlEndpoint``, ``rdfDump``, ``humanLicense``, ``externalLinks``

**Naming Convention:**
``classCapitalCheck``, ``classSpaceCheck``, ``spellCheck``,
``duplicateLabels``, ``searchClass``
