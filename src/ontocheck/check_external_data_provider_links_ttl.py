from rdflib import OWL, RDFS, SKOS
import rdflib
import requests

def check_external_data_provider_links_ttl(ttl_file, base_namespace=None):
    """
    I2 - Detection of existence and usage of external URIs
    
    Evaluates the degree to which a dataset links to external data providers
    through properties like owl:sameAs, rdfs:seeAlso, and SKOS mapping properties.
    This metric assesses the dataset's integration with the broader Linked Data cloud.
    
    External links enhance data discoverability and enable cross-dataset queries,
    representing a key principle of Linked Data publishing.
    
    Author: Redad Mehdi
    Version: 0.0.1
    
    Parameters:
    -----------
    ttl_file : str
        Path to the Turtle (.ttl) file to analyze
    base_namespace : str, optional
        Base namespace of the ontology. If not provided, the function attempts
        to infer it from the graph's namespace declarations.
        
    Returns:
    --------
    float
        Ratio of entities with external links (0.0 to 1.0)
        - 0.0: No entities have external links
        - 1.0: All entities have at least one external link
        
    Notes:
    ------
    The function examines the following linking predicates:
    - owl:sameAs, rdfs:seeAlso
    - SKOS mapping properties (exactMatch, closeMatch, etc.)
    - owl:equivalentClass, owl:equivalentProperty
    - dc:source, foaf:isPrimaryTopicOf
    
    If no base namespace is provided, the function recognizes links to known
    external data providers like DBpedia, Wikidata, GeoNames, etc.
    
    Example:
    --------
    >>> score = check_external_data_provider_links_ttl('dataset.ttl', 
    ...                                                 'http://example.org/')
    >>> print(f"External linking score: {score:.2f}")
    
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
    
    # If no base namespace provided, try to infer it from the graph
    if not base_namespace:
        # Get the most common namespace prefix
        namespaces = list(g.namespaces())
        if namespaces:
            for prefix, namespace in namespaces:
                if prefix in ['', 'base']:
                    base_namespace = str(namespace)
                    break
            if not base_namespace and namespaces:
                base_namespace = str(namespaces[0][1])
    
    # Predicates commonly used to link to external data providers
    external_linking_predicates = [
        OWL.sameAs,  # owl:sameAs
        RDFS.seeAlso,  # rdfs:seeAlso
        SKOS.exactMatch,  # skos:exactMatch
        SKOS.closeMatch,  # skos:closeMatch
        SKOS.relatedMatch,  # skos:relatedMatch
        SKOS.broadMatch,  # skos:broadMatch
        SKOS.narrowMatch,  # skos:narrowMatch
        rdflib.URIRef("http://www.w3.org/2002/07/owl#equivalentClass"),
        rdflib.URIRef("http://www.w3.org/2002/07/owl#equivalentProperty"),
        rdflib.URIRef("http://purl.org/dc/terms/source"),
        rdflib.URIRef("http://xmlns.com/foaf/0.1/isPrimaryTopicOf")
    ]
    
    total_entities = 0
    entities_with_external_links = 0
    external_links_count = 0
    
    # Get all subjects (entities) in the ontology
    subjects = set()
    for s, p, o in g:
        if isinstance(s, rdflib.URIRef):
            subjects.add(s)
    
    total_entities = len(subjects)
    
    # Check each entity for external links
    for subject in subjects:
        has_external_link = False
        
        for pred in external_linking_predicates:
            for s, p, o in g.triples((subject, pred, None)):
                if isinstance(o, rdflib.URIRef):
                    # Check if the object URI is external (different domain/namespace)
                    obj_str = str(o)
                    if base_namespace and not obj_str.startswith(base_namespace):
                        external_links_count += 1
                        has_external_link = True
                    elif not base_namespace:
                        # If no base namespace, consider known external data providers
                        external_providers = [
                            'dbpedia.org', 'wikidata.org', 'geonames.org',
                            'freebase.com', 'yago-knowledge.org', 'schema.org',
                            'getty.edu', 'loc.gov', 'bnf.fr', 'viaf.org'
                        ]
                        if any(provider in obj_str.lower() for provider in external_providers):
                            external_links_count += 1
                            has_external_link = True
        
        if has_external_link:
            entities_with_external_links += 1
    
    # Return a score based on the ratio of entities with external links
    if total_entities == 0:
        return 0
    
    # Score based on ratio of entities with external links
    entity_ratio = entities_with_external_links / total_entities
    
    return entity_ratio
