from rdflib import OWL, RDFS, SKOS
import rdflib
import requests

def check_human_readable_license_ttl(ttl_file):
    """
    L2 - Human-readable license detection
    
    Detects the presence of human-readable licensing information within a TTL file.
    This metric evaluates whether the dataset provides clear licensing terms that
    users can understand without legal expertise.
    
    The function searches for common license-related keywords in both RDF literals
    and TTL file comments, including references to popular licenses like Creative
    Commons, GPL, MIT, Apache, and BSD.
    
    Author: Redad Mehdi
    Version: 0.0.1
    
    Parameters:
    -----------
    ttl_file : str
        Path to the Turtle (.ttl) file to analyze
        
    Returns:
    --------
    int
        Binary score (0 or 1)
        - 0: No human-readable license information found
        - 1: License-related keywords detected
        
    Notes:
    ------
    Keywords searched include: 'license', 'licence', 'copyright', 'terms of use',
    'creative commons', 'GPL', 'MIT', 'Apache', 'BSD'
    
    Example:
    --------
    >>> score = check_human_readable_license_ttl('dataset.ttl')
    >>> if score:
    ...     print("Human-readable license information found")
    ... else:
    ...     print("No license information detected")
    
    References:
    -----------
    Zaveri, A., Rula, A., Maurino, A., Pietrobon, R., Lehmann, J., & Auer, S. 
    (2015). Quality assessment for Linked Data: A Survey: A systematic literature 
    review and conceptual framework. Semantic Web, 7(1), 63-93.
    
    Hogan, A., Umbrich, J., Harth, A., Cyganiak, R., Polleres, A., & Decker, S. 
    (2012). An empirical survey of Linked Data conformance. Journal of Web 
    Semantics, 14, 14-44.
    """
    g = rdflib.Graph()
    g.parse(ttl_file, format='turtle')
    
    license_keywords = ['license', 'licence', 'copyright', 'terms of use', 
                       'creative commons', 'GPL', 'MIT', 'Apache', 'BSD']
    
    # Check all literal values in the graph
    for s, p, o in g:
        if isinstance(o, rdflib.Literal):
            text_lower = str(o).lower()
            for keyword in license_keywords:
                if keyword in text_lower:
                    return 1
    
    # Also check comments in the TTL file directly
    with open(ttl_file, 'r', encoding='utf-8') as f:
        content = f.read().lower()
        for keyword in license_keywords:
            if keyword in content:
                return 1
    
    return 0
