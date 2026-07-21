from rdflib import Graph, RDFS, SKOS
from .helpers.helpers import _spell_checker


# spell.word_frequency.load_words(['piezoelectric', 'synchrotron'])

def spell_check_v_0_0_1(ttl_file):
    """Evaluates spelling accuracy across natural language annotation properties in an RDF ontology.

    This function parses a Turtle (.ttl) file and extracts literal values attached to
    common human-readable annotation predicates (`rdfs:label`, `skos:definition`, 
    and `rdfs:comment`). It passes each literal to an internal helper `_spell_checker` 
    to tally total words evaluated and misspellings identified.

    Args:
        ttl_file (str): Path to the target Turtle (.ttl) file to parse.

    Returns:
        float: The overall spelling error rate across all checked literal fields,
            calculated as (total_errors / total_words_checked), ranging from 0.0 to 1.0.

    Prints:
        details (list[dict]): A list of error records containing the subject IRI, 
            word counts, and specific misspelled tokens for flagged annotations.
        total_checked (int): Aggregate count of words evaluated across targeted literals.
        total_errors (int): Aggregate count of spelling errors detected.
        error_rate (float): Raw error ratio.
        error_percentage (str): Formatted error percentage (e.g., "2.35%").

    Author: Van Tran
    Version: 0.0.1

    """
    g = Graph()
    g.parse(ttl_file, format="turtle")
    
    details = []
    targets = {RDFS.label, SKOS.definition, RDFS.comment}
    
    total_checked = 0
    total_errors = 0

    for s, p, o in g:
        if p in targets:
            res = _spell_checker(str(o))
            
            total_checked += res['checked_count']
            total_errors += res['error_count']
            
            # Only add to details if there were actually errors
            if res['error_count'] > 0:
                res['subject'] = str(s)
                details.append(res)
    
    # Calculate error rate
    error_rate = (total_errors / total_checked) if total_checked > 0 else 0
    
    # Construct the final result dictionary
    # results = {
    #     "summary": {
    #         "total_words_checked": total_checked,
    #         "total_errors_found": total_errors,
    #         "error_rate": error_rate,
    #         "error_percentage": f"{error_rate * 100:.2f}%"
    #     },
    #     "details": details
    # }

    error_percentage = f"{error_rate * 100:.2f}%"

    print(details)
    print(f"Total number of words checked: {total_checked}")
    print(f"Total number of errors found: {total_errors}")
    print(f"Rate of error: {error_rate}")
    print(f"Error rate in percentages: {error_percentage}")
            
    return error_rate