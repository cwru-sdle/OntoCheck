Installation
============

Requirements
------------

- Python 3.8 or later
- A working ``pip`` installation

Install from PyPI
-----------------

The recommended way to install OntoCheck is from the Python Package Index:

.. code-block:: bash

   pip install OntoCheck

This will install OntoCheck and its required dependencies:

- `rdflib <https://rdflib.readthedocs.io/>`_ -- RDF graph parsing and SPARQL query execution
- `networkx <https://networkx.org/>`_ -- Graph analysis for structural metrics
- `requests <https://requests.readthedocs.io/>`_ -- HTTP requests for accessibility checks

Install from Source
-------------------

To install the latest development version directly from the repository:

.. code-block:: bash

   git clone https://github.com/cwru-sdle/OntoCheck.git
   cd OntoCheck
   pip install .

Verify Installation
-------------------

After installation, verify that OntoCheck is accessible:

.. code-block:: bash

   ontocheck -h

Or from Python:

.. code-block:: python

   import ontocheck
   print(ontocheck.__all__)
