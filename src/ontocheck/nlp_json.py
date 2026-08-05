import json
from pathlib import Path
from helpers import _clean_and_extract_phrases, _to_pascal_case, _to_camel_case
import logging

logger = logging.getLogger(__name__)


def build_question_json(
    txt_path: str | Path,
    output_json_path: str | Path,
    prefix: str = "mds",
    namespace_uri: str = "https://cwrusdle.bitbucket.io/mds/",
    starting_qid: int = 1000000
):
    """
    Reads natural language questions from a .txt file, extracts ontology 
    terms using helper functions, and builds the structured JSON format.
    """
    txt_file = Path(txt_path)
    output_file = Path(output_json_path)

    with open(txt_file, "r", encoding="utf-8") as f:
        questions = [line.strip() for line in f if line.strip()]

    json_records = []

    for idx, question_text in enumerate(questions):
        qid = starting_qid + idx
        
        # Use the imported helper function
        concept_phrases = _clean_and_extract_phrases(question_text)
        
        nodes = []
        edges = []
        sparql_select_vars = []
        sparql_where_clauses = []
        
        for n_idx, phrase in enumerate(concept_phrases):
            # Use the imported helper functions
            pascal_term = _to_pascal_case(phrase)
            camel_var = _to_camel_case(phrase)
            friendly_name = " ".join(w.capitalize() for w in phrase.split())
            
            node_id = f"{prefix}:{pascal_term}"
            nodes.append({
                "nid": n_idx,
                "node_type": "class",
                "id": node_id,
                "class": node_id,
                "friendly_name": friendly_name,
                "question_node": 1 if n_idx > 0 else 0,
                "function": "none"
            })
            
            if n_idx > 0:
                edges.append({
                    "start": n_idx,
                    "end": 0,
                    "relation": "rdfs:subClassOf",
                    "friendly_name": "subclass of"
                })

            sparql_select_vars.append(f"?{camel_var}")
            sparql_where_clauses.append(f"  ?{camel_var} a {node_id} .")

        vars_str = " ".join(sparql_select_vars) if sparql_select_vars else "?concept"
        where_str = "\n".join(sparql_where_clauses) if sparql_where_clauses else f"  ?concept a {prefix}:Concept ."
        
        sparql_query = (
            f"PREFIX {prefix}: <{namespace_uri}>\n"
            f"PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            f"SELECT {vars_str}\n"
            f"WHERE {{\n"
            f"{where_str}\n"
            f"}}"
        )

        record = {
            "qid": qid,
            "question": question_text,
            "answer": [],
            "function": "none",
            "commonness": None,
            "num_node": len(nodes),
            "num_edge": len(edges),
            "graph_query": {
                "nodes": nodes,
                "edges": edges
            },
            "sparql_query": sparql_query
        }
        
        json_records.append(record)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(json_records, f, indent=2)

    logger.info(f"Processed {len(json_records)} questions. Saved to {output_file.name}")