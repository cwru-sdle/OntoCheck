Usage Guide
===========

OntoCheck provides two interfaces: a command-line tool for quick assessments
and a Python API for programmatic use and integration into data pipelines.

All assessments require an ontology serialized in Turtle (``.ttl``) format.
The input file must be free of syntax errors. Some assessments also require a
set of SPARQL queries derived from competency questions.

How It Works
------------

OntoCheck uses a unified interface: users select **task-agnostic metrics**
with ``--metrics`` and/or supply **competency questions** with
``--questions`` for task-based assessment. At least one of ``--metrics`` or
``--questions`` is required. When multiple ``.ttl`` files are provided, they
are automatically merged into a single graph before assessment.

Command-Line Interface
----------------------

.. code-block:: text

   ontocheck <ttl_files...> --metrics <names...> [options]
   ontocheck <ttl_files...> --questions <file> --domain-prefixes <prefixes...> [options]

Task-Agnostic Metrics
^^^^^^^^^^^^^^^^^^^^^^

Run one or more task-agnostic metrics on an ontology.

.. code-block:: bash

   # Run two specific metrics
   ontocheck my_ontology.ttl --metrics altLabelCheck definitionCheck

   # Run all available metrics with custom output paths
   ontocheck my_ontology.ttl --metrics all --log-file results.log --csv-file results.csv

Task-Based Assessment
^^^^^^^^^^^^^^^^^^^^^^

Assess a domain ontology against competency questions encoded as SPARQL
queries.

.. code-block:: bash

   ontocheck my_ontology.ttl \
       --questions competency_questions.json \
       --domain-prefixes mds \
       --domain-ns-fragments cwrusdle.bitbucket.io/mds

Combined
^^^^^^^^^

Run task-agnostic metrics alongside a task-based assessment in a single
invocation.

.. code-block:: bash

   ontocheck my_ontology.ttl \
       --questions competency_questions.json \
       --domain-prefixes mds \
       --metrics checkLabel definitionCheck

Cross-Domain
^^^^^^^^^^^^^

Merge multiple ontologies and evaluate against cross-domain queries.
Multiple ``.ttl`` files are merged automatically.

.. code-block:: bash

   ontocheck xrd_ontology.ttl capacitors_ontology.ttl \
       --questions cross_domain_questions.json \
       --domain-prefixes mds

MDS Design Check
^^^^^^^^^^^^^^^^^

Run the MDS ontology design conformance check.

.. code-block:: bash

   ontocheck my_ontology.ttl --mds-ontodesigncheck

CLI Arguments
^^^^^^^^^^^^^

``ttl_files``
   One or more paths to Turtle ontology files. When multiple files are
   provided, they are merged into a single graph.

``--metrics``
   Task-agnostic metric names, or ``all``. At least one of ``--metrics`` or
   ``--questions`` is required.

``--questions``
   Path to a JSON or Markdown file containing SPARQL queries for task-based
   assessment. Requires ``--domain-prefixes``.

``--domain-prefixes``
   Namespace prefixes used in the SPARQL queries (e.g., ``mds``, ``dbo``).
   Required when ``--questions`` is provided.

``--domain-ns-fragments``
   Namespace URI fragments for filtering domain terms. Optional.

``--mds-ontodesigncheck``
   Run the MDS ontology design conformance check.

``--log-file``
   Path for the output log file (default: ``assessment.log``).

``--csv-file``
   Path for the output CSV results file (default: ``assessment_scores.csv``).

Python API
----------

Task-Agnostic Assessment
^^^^^^^^^^^^^^^^^^^^^^^^^^

The :func:`~ontocheck.run_assessment.run_assessment` function runs one or
more task-agnostic metrics on a Turtle file.

.. code-block:: python

   from ontocheck import run_assessment

   # Run selected metrics
   run_assessment(
       ttl_file="my_ontology.ttl",
       metrics=["altLabelCheck", "isolatedElements", "semanticConnection"],
       output_log_file="assessment.log",
       output_csv_file="scores.csv",
   )

   # Run all metrics
   run_assessment(
       ttl_file="my_ontology.ttl",
       metrics="all",
   )

Task-Based Assessment
^^^^^^^^^^^^^^^^^^^^^^

Supply competency questions to evaluate a domain ontology against SPARQL
queries.

.. code-block:: python

   from ontocheck import run_assessment

   result = run_assessment(
       ttl_files="my_ontology.ttl",
       questions="competency_questions.json",
       domain_prefixes=["mds"],
       domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
   )

   print(f"Relevance: {result['relevance']:.2%}")
   print(f"Accuracy:  {result['accuracy']:.2%}")
   print(f"Ontology terms (T_o): {result['T_o_count']}")
   print(f"Task terms (T_a):     {result['T_a_count']}")

Combined Assessment
^^^^^^^^^^^^^^^^^^^^

Run task-agnostic metrics alongside the task-based assessment.

.. code-block:: python

   from ontocheck import run_assessment

   result = run_assessment(
       ttl_files="my_ontology.ttl",
       questions="competency_questions.json",
       domain_prefixes=["mds"],
       metrics=["checkLabel", "definitionCheck"],
   )

Cross-Domain Assessment
^^^^^^^^^^^^^^^^^^^^^^^^

Pass multiple ontology files to merge them and evaluate cross-domain
competency questions.

.. code-block:: python

   from ontocheck import run_assessment

   result = run_assessment(
       ttl_files=["xrd_ontology.ttl", "capacitors_ontology.ttl"],
       questions="cross_domain_questions.json",
       domain_prefixes=["mds"],
   )

   print(f"Relevance: {result['relevance']:.2%}")
   print(f"Accuracy:  {result['accuracy']:.2%}")

Underlying Task-Based Metric
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For direct access to the task-based Relevance/Accuracy computation without
logging or CSV output, use
:func:`~ontocheck.task_based_metric.task_based_metric_v_0_0_1`:

.. code-block:: python

   from ontocheck import task_based_metric_v_0_0_1

   result = task_based_metric_v_0_0_1(
       ttl_file="my_ontology.ttl",
       questions="competency_questions.json",
       domain_prefixes=["mds"],
       domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
   )

   print(f"Relevance: {result['relevance']:.2%}")
   print(f"Accuracy:  {result['accuracy']:.2%}")

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

   result = task_based_metric_v_0_0_1(
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
or the ``metrics`` parameter of ``run_assessment``:

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

OntoCheck is Built for the Community
-------------------------------------

OntoCheck is conceived as a community resource: we actively encourage
collaboration, contribution of new metrics, and submission of domain
competency question sets, in the shared interest of building robust,
reusable semantic infrastructure for FAIR scientific data.
