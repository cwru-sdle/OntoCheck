API Reference
=============

This section documents the public API of OntoCheck, organized by assessment
category. Each metric function takes a Turtle file path as input and returns
a score or diagnostic report.

Assessment Runners
------------------

Unified assessment runner.

.. automodule:: ontocheck.run_assessment
   :members: run_assessment
   :show-inheritance:

Task-Based Metric
-----------------

The underlying Relevance/Accuracy computation used by the task-based assessment.

.. automodule:: ontocheck.task_based_metric
   :members: task_based_metric_v_0_0_1
   :show-inheritance:

Labeling Metrics
----------------

Metrics that quantify the proportion of named classes carrying synonyms.
Label and definition coverage are measured by FOOPS! VOC3-T and VOC4-T.

ontocheck.altLabelCheck
^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.altLabelCheck
   :members:
   :show-inheritance:

Structural Metrics
------------------

Metrics that expose disconnected subgraphs, leaf nodes, and hierarchy chains
lacking grounding in upper-level ontologies.  Isolated elements and missing
domains and ranges are measured by OOPS! P04 and P11.

ontocheck.count\_class\_connected\_components
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.count_class_connected_components
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

Metrics that verify endpoint reachability, data dump availability, and
external link validity.  Licensing is checked by FOOPS! OM4.1-T and OOPS! P41.

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

ontocheck.query\_fitness
^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.query_fitness
   :members:
   :show-inheritance:

ontocheck.context\_weighting
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ontocheck.context_weighting
   :members:
   :show-inheritance:

Module Contents
---------------

.. automodule:: ontocheck
   :members:
   :no-index:
   :show-inheritance:
