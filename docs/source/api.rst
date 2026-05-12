API Reference
=============

This section documents the public API of OntoCheck, organized by assessment
category. Each metric function takes a Turtle file path as input and returns
a score or diagnostic report.

Assessment Runners
------------------

Functions for running each of the four assessment modes.

.. automodule:: ontocheck.run_assessment
   :members: run_ontology_assessment, run_task_based_assessment, run_web_ontology_assessment
   :show-inheritance:

Task-Based Metric
-----------------

The underlying Relevance/Accuracy computation used by Modes 2, 3, and 4.

.. automodule:: ontocheck.task_based_metric
   :members: task_based_metric_v_0_0_1
   :show-inheritance:

Labeling Metrics
----------------

Metrics that quantify the proportion of named classes carrying human-readable
identifiers, synonyms, and formal definitions.

ontocheck.check\_label
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_label
   :members:
   :show-inheritance:

ontocheck.altLabelCheck
^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.altLabelCheck
   :members:
   :show-inheritance:

ontocheck.defCheck
^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.defCheck
   :members:
   :show-inheritance:

Structural Metrics
------------------

Metrics that expose orphaned classes, disconnected subgraphs, undeclared
domain and range restrictions, and hierarchy chains lacking grounding in
upper-level ontologies.

ontocheck.check\_for\_isolated\_elements
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_for_isolated_elements
   :members:
   :show-inheritance:

ontocheck.count\_class\_connected\_components
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.count_class_connected_components
   :members:
   :show-inheritance:

ontocheck.get\_properties\_missing\_domain\_and\_range
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.get_properties_missing_domain_and_range
   :members:
   :show-inheritance:

ontocheck.leafNodeCheck
^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.leafNodeCheck
   :members:
   :show-inheritance:

ontocheck.semanticConnection
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.semanticConnection
   :members:
   :show-inheritance:

Accessibility Metrics
---------------------

Metrics that verify endpoint reachability, data dump availability, licensing
fitness, and external link validity.

ontocheck.check\_sparql\_accessibility\_ttl
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_sparql_accessibility_ttl
   :members:
   :show-inheritance:

ontocheck.check\_rdf\_dump\_accessibility\_ttl
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_rdf_dump_accessibility_ttl
   :members:
   :show-inheritance:

ontocheck.check\_human\_readable\_license\_ttl
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_human_readable_license_ttl
   :members:
   :show-inheritance:

ontocheck.check\_external\_data\_provider\_links\_ttl
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_external_data_provider_links_ttl
   :members:
   :show-inheritance:

Naming Convention Metrics
-------------------------

Metrics that detect and flag naming of ontological entities that depart from
standard authoring practices.

ontocheck.check\_class\_name\_capital
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_class_name_capital
   :members:
   :show-inheritance:

ontocheck.check\_class\_name\_space
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.check_class_name_space
   :members:
   :show-inheritance:

ontocheck.spell\_check
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.spell_check
   :members:
   :show-inheritance:

ontocheck.find\_duplicate\_labels\_from\_graph
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.find_duplicate_labels_from_graph
   :members:
   :show-inheritance:

ontocheck.class\_search
^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.class_search
   :members:
   :show-inheritance:

Other Modules
-------------

ontocheck.cli
^^^^^^^^^^^^^

.. automodule:: ontocheck.cli
   :members:
   :show-inheritance:

ontocheck.mds\_design\_check
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.mds_design_check
   :members:
   :show-inheritance:

Module Contents
---------------

.. automodule:: ontocheck
   :members:
   :no-index:
   :show-inheritance:
