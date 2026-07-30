"""
mainLeafNodeCheck_v_0_0_1 metric implementation.
"""

from .helpers.helpers import _find_leaf_nodes
from rdflib import Graph, RDFS, RDF, OWL, SKOS
import logging

logger = logging.getLogger(__name__)

def mainLeafNodeCheck_v_0_0_1(ttl_file):
    """
    Ontology Leaf Node Analysis

    Analyze an OWL ontology in Turtle (ttl) format and identify all leaf nodes in the class hierarchy. Leaf nodes are classes that have no subclasses, representing the most specific classes in the ontology

    This main function loads an ontology file, identifies all declared classes, and determines which classes are leaf nodes by finding classes that are never used as superclasses

    Definitions
    -----------
    - Leaf nodes: Classes that have no subclasses, meaning they do not appear as objects in rdfs:subClassOf relationships (or skos:broader)
    
    - Declared classes: Classes explicitly declared with rdf:type owl:Class or rdfs:Class

    - Hierarchy detection: Uses rdfs:subClassOf relationships to determine class hierarchy (also skos:broader)

    Author: Rishabh Kundu
    Version: 0.0.1

    Parameters
    ----------
    ttl_file : str
        Path to the ontology Turtle (.ttl) file to analyze

    Returns
    -------
    None
        This function does not (directly) return values. It prints analysis results to terminal/CLI
        The function may exit early on errors (file not found, parsing errors, or no leaf nodes found)

    Output Information
    -----------------
    When executed successfully, the analysis provides:
    - Total number of leaf nodes found
    - Complete list of leaf nodes with their prefixed names (sorted alphabetically)

    Error Handling
    -------------
    The function handles several error conditions:
    - FileNotFoundError: When the specified TTL file cannot be found
    - Parsing errors: When the TTL file cannot be parsed as valid Turtle
    - Empty results: When no leaf nodes are found in the ontology

    Notes
    -----
    - Only considers explicitly declared classes (rdf:type owl:Class or rdfs:Class)
    - Uses namespace manager for clean URI representation in output
    - Leaf nodes are sorted alphabetically for consistent display
    - Coverage statistics may be implemented in future versions

    .. note::

       Claude AI (Sonnet 4) was employed chiefly to support documentation efforts.

    References
    ----------

    - Mc Gurk, S., Abela, C., & Debattista, J. (2017). Towards ontology quality assessment. 4th Workshop on Linked Data Quality (LDQ2017), co-located with the 14th Extended Semantic Web Conference (ESWC), Portorož, 94-106.

    Examples
    --------
    Basic usage:
        python script.py ontology.ttl

    """

    g = Graph()
    try:
        logger.info(f"Parsing file: {ttl_file}...")
        g.parse(ttl_file, format="turtle")
    except FileNotFoundError:
        logger.error(f"The file '{ttl_file}' was not found.")
        return
    except Exception as e:
        logger.error(f"An error occurred while parsing the TTL file: {e}")
        return

    leaf_nodes = _find_leaf_nodes(g)

    if not leaf_nodes:
        logger.info("No leaf nodes were found in the provided ontology.")
        return

    logger.info("--- Leaf Node Analysis Complete ---")
    logger.info("Leaf Nodes:")
    for leaf in sorted(leaf_nodes):

        logger.info(f"{leaf.n3(g.namespace_manager)}")
