from rdflib import OWL, RDFS, SKOS
import rdflib
import requests

def check_rdf_dump_accessibility_ttl(ttl_file):
    """
    A2 - RDF dump accessibility
    
    Evaluates the accessibility of RDF data dumps referenced in a TTL file
    by attempting to access each discovered dump URL via HTTP HEAD requests.
    
    This metric assesses whether the raw RDF data is available for download,
    which is important for data consumers who need offline access or bulk
    processing capabilities.
    
    Author: Redad Mehdi
    Version: 0.0.1
    
    Parameters:
    -----------
    ttl_file : str
        Path to the Turtle (.ttl) file to analyze
        
    Returns:
    --------
    float
        Ratio of accessible RDF dumps (0.0 to 1.0)
        - 0.0: No accessible dumps found
        - 1.0: All discovered dumps are accessible
        
    Notes:
    ------
    The function identifies potential dump URLs by looking for common RDF
    file extensions (.rdf, .ttl, .nt, .n3, .owl, .jsonld) in referenced URLs.
    
    Example:
    --------
    >>> score = check_rdf_dump_accessibility_ttl('dataset.ttl')
    >>> print(f"RDF dump accessibility score: {score}")
    
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
    
    # Common predicates that might point to data dumps
    dump_predicates = [
        rdflib.URIRef("http://rdfs.org/ns/void#dataDump"),
        rdflib.URIRef("http://www.w3.org/ns/dcat#downloadURL"),
        rdflib.URIRef("http://www.w3.org/ns/dcat#accessURL"),
        rdflib.URIRef("http://xmlns.com/foaf/0.1/homepage")  # Sometimes dumps linked from homepage
    ]
    
    dump_urls = []
    for pred in dump_predicates:
        for s, p, o in g.triples((None, pred, None)):
            if isinstance(o, rdflib.URIRef):
                url_str = str(o)
                # Filter for likely dump files (common RDF formats)
                if any(ext in url_str.lower() for ext in ['.rdf', '.ttl', '.nt', '.n3', '.owl', '.jsonld']):
                    dump_urls.append(url_str)
    
    if not dump_urls:
        return 0
    
    # Test accessibility of found dump URLs
    accessible_dumps = 0
    for url in dump_urls:
        try:
            response = requests.head(url, timeout=10)
            if response.status_code == 200:
                accessible_dumps += 1
        except:
            continue
    
    return accessible_dumps / len(dump_urls)
