from rdflib import OWL, RDFS, SKOS
import rdflib
import requests

def check_sparql_accessibility_ttl(ttl_file):
    """
    A1 - Accessibility of the SPARQL endpoint and the server
    
    Evaluates the accessibility of SPARQL endpoints referenced in a TTL file
    by attempting to execute a simple query against each discovered endpoint.
    
    This metric is based on Flemming (2011) quality criteria for Linked Data
    sources, specifically addressing the availability and accessibility of
    query interfaces.
    
    Author: Redad Mehdi
    Version: 0.0.1
    
    Parameters:
    -----------
    ttl_file : str
        Path to the Turtle (.ttl) file to analyze
        
    Returns:
    --------
    float
        Ratio of accessible SPARQL endpoints (0.0 to 1.0)
        - 0.0: No accessible endpoints found
        - 1.0: All discovered endpoints are accessible
        
    Example:
    --------
    >>> score = check_sparql_accessibility_ttl('dataset.ttl')
    >>> print(f"SPARQL accessibility score: {score}")
    
    References:
    -----------
    Zaveri, A., Rula, A., Maurino, A., Pietrobon, R., Lehmann, J., & Auer, S. 
    (2015). Quality assessment for Linked Data: A Survey: A systematic literature 
    review and conceptual framework. Semantic Web, 7(1), 63-93.
    
    Flemming, A. (2011). Qualitätsmerkmale von Linked Data-veröffentlichenden 
    Datenquellen. Diplomarbeit (Quality Criteria for Linked Data Sources).
    """
    g = rdflib.Graph()
    g.parse(ttl_file, format='turtle')
    
    # Common predicates that might point to SPARQL endpoints
    sparql_predicates = [
        rdflib.URIRef("http://rdfs.org/ns/void#sparqlEndpoint"),
        rdflib.URIRef("http://www.w3.org/ns/dcat#accessURL"),
        rdflib.URIRef("http://www.w3.org/ns/sparql-service-description#endpoint")
    ]
    
    endpoints = []
    for pred in sparql_predicates:
        for s, p, o in g.triples((None, pred, None)):
            if isinstance(o, rdflib.URIRef):
                endpoints.append(str(o))
    
    if not endpoints:
        return 0
    
    # Test accessibility of found endpoints
    accessible_endpoints = 0
    for endpoint in endpoints:
        try:
            # Simple SPARQL query
            params = {'query': 'SELECT * WHERE {?s ?p ?o} LIMIT 1'}
            response = requests.get(endpoint, params=params, timeout=10)
            if response.status_code == 200:
                accessible_endpoints += 1
        except:
            continue
    
    return accessible_endpoints / len(endpoints)
