Usage Guide
===========

OntoCheck provides two interfaces: a command-line tool for quick assessments
and a Python API for programmatic use and integration into data pipelines.

All assessments require an ontology serialized in Turtle (``.ttl``) format.
The input file must be free of syntax errors.

Assessment Modes
----------------

OntoCheck supports four assessment modes, controlled by a declarative
configuration ``C = (O, Q, M, G)`` where *O* specifies ontologies, *Q* is a
set of competency queries, *M* refers to the metrics, and *G* is a knowledge
graph.

**Mode 1 -- Task-agnostic** ``(O, empty, M, empty)``
   Run structural, labeling, accessibility, and naming-convention metrics on a
   single ontology.

**Mode 2 -- Task-specific Web ontology** ``(O, Q, M, G)``
   Validate an ontology against KGQA benchmark queries over a knowledge graph
   (e.g., LC-QuAD / DBpedia).

**Mode 3 -- Task-based Scientific** ``(O, Q, M, empty)``
   Assess a domain ontology against competency questions encoded as SPARQL
   queries.

**Mode 4 -- Cross-Domain** ``(O[], Q, M, empty)``
   Merge multiple ontologies and assess the combined vocabulary against
   cross-domain competency questions.

Command-Line Interface
----------------------

The ``ontocheck`` command accepts a ``--mode`` flag (default: ``1``) that
selects which assessment to run.

.. code-block:: text

   ontocheck <ttl_files...> --mode {1,2,3,4} [options]

Mode 1: Task-Agnostic (default)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Run one or more task-agnostic metrics on a single ontology.

.. code-block:: bash

   # Run two specific metrics
   ontocheck my_ontology.ttl --metrics altLabelCheck definitionCheck

   # Run all available metrics with custom output paths
   ontocheck my_ontology.ttl --metrics all --log-file results.log --csv-file results.csv

Mode 2: Task-Specific Web Ontology
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Validate against a KGQA benchmark over a knowledge graph.

.. code-block:: bash

   ontocheck dbpedia_ontology.ttl \
       --mode 2 \
       --questions lcquad_queries.json \
       --domain-prefixes dbo \
       --knowledge-graph dbpedia_kg.ttl

Mode 3: Task-Based Scientific
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Assess a domain ontology against competency questions.

.. code-block:: bash

   ontocheck my_ontology.ttl \
       --mode 3 \
       --questions competency_questions.json \
       --domain-prefixes mds \
       --domain-ns-fragments cwrusdle.bitbucket.io/mds

Optionally run task-agnostic metrics alongside the task-based assessment:

.. code-block:: bash

   ontocheck my_ontology.ttl \
       --mode 3 \
       --questions competency_questions.json \
       --domain-prefixes mds \
       --metrics checkLabel definitionCheck

Mode 4: Cross-Domain
^^^^^^^^^^^^^^^^^^^^^^

Merge multiple ontologies and evaluate against cross-domain queries.

.. code-block:: bash

   ontocheck xrd_ontology.ttl capacitors_ontology.ttl \
       --mode 4 \
       --questions cross_domain_questions.json \
       --domain-prefixes mds

CLI Arguments
^^^^^^^^^^^^^

``ttl_files``
   One or more paths to Turtle ontology files. Mode 4 requires at least two.

``--mode``
   Assessment mode: ``1`` (default), ``2``, ``3``, or ``4``.

``--metrics``
   Task-agnostic metric names, or ``all``. Required for Mode 1; optional for
   Modes 2--4.

``--questions``
   Path to a JSON or Markdown file containing SPARQL queries. Required for
   Modes 2, 3, and 4.

``--domain-prefixes``
   Namespace prefixes used in the SPARQL queries (e.g., ``mds``, ``dbo``).
   Required for Modes 2, 3, and 4.

``--domain-ns-fragments``
   Namespace URI fragments for filtering domain terms. Optional.

``--knowledge-graph``
   Path to a knowledge-graph file. Required for Mode 2.

``--log-file``
   Path for the output log file (default: ``assessment.log``).

``--csv-file``
   Path for the output CSV results file (default: ``assessment_scores.csv``).

Python API
----------

Mode 1: Task-Agnostic Assessment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Mode 2: Task-Specific Web Ontology Assessment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :func:`~ontocheck.run_assessment.run_web_ontology_assessment` function validates
an ontology against KGQA benchmark queries over a knowledge graph.

.. code-block:: python

   from ontocheck import run_web_ontology_assessment

   result = run_web_ontology_assessment(
       ttl_file="dbpedia_ontology.ttl",
       questions="lcquad_queries.json",
       domain_prefixes=["dbo"],
       knowledge_graph="dbpedia_kg.ttl",
   )

   print(f"Relevance: {result['relevance']:.2%}")
   print(f"Accuracy:  {result['accuracy']:.2%}")

Mode 3: Task-Based Scientific Assessment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :func:`~ontocheck.run_assessment.run_task_based_assessment` function evaluates a
domain ontology against competency questions encoded as SPARQL queries.

.. code-block:: python

   from ontocheck import run_task_based_assessment

   result = run_task_based_assessment(
       ttl_files="my_ontology.ttl",
       questions="competency_questions.json",
       domain_prefixes=["mds"],
       domain_ns_fragments=["cwrusdle.bitbucket.io/mds"],
   )

   print(f"Relevance: {result['relevance']:.2%}")
   print(f"Accuracy:  {result['accuracy']:.2%}")
   print(f"Ontology terms (T_o): {result['T_o_count']}")
   print(f"Task terms (T_a):     {result['T_a_count']}")

To also run task-agnostic metrics alongside the task-based assessment:

.. code-block:: python

   result = run_task_based_assessment(
       ttl_files="my_ontology.ttl",
       questions="competency_questions.json",
       domain_prefixes=["mds"],
       metrics=["checkLabel", "definitionCheck"],
   )

Mode 4: Cross-Domain Assessment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pass multiple ontology files to
:func:`~ontocheck.run_assessment.run_task_based_assessment` to merge them and
evaluate cross-domain competency questions.

.. code-block:: python

   from ontocheck import run_task_based_assessment

   result = run_task_based_assessment(
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
