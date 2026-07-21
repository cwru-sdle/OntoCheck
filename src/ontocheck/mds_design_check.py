from rdflib import Graph, Namespace, OWL, RDF, RDFS

def mds_design_check_v_0_0_1(ttl_file):
    """Evaluates an MDS ontology file for mandatory structural design predicates.

    This function parses a Turtle (.ttl) file, extracts all explicit OWL/RDFS
    classes, and evaluates whether each class defines required metadata 
    predicates (`inDom` and `hasStudyStage`). A class is considered valid 
    if and only if it possesses at least one non-empty value for ALL specified
    predicates.

    Args:
        ttl_file (str): Path to the target Turtle (.ttl) file to parse.

    Returns:
        float: The proportion of classes that satisfy all required predicate 
            constraints (valid_classes / total_classes), ranging from 0.0 to 1.0.

    Prints:
        missing_report (dict): A mapping of predicate names to lists of class IRIs
            missing that specific predicate.
        total_class_count (int): Total number of unique classes evaluated.

    Author: Van Tran
    Version: 0.0.1
    """
    MDS = Namespace("https://cwrusdle.bitbucket.io/mds/")
    preds = {
        "inDomain": MDS.inDomain,
        "hasStudyStage": MDS.hasStudyStage
    }

    mds_graph = Graph()
    mds_graph.parse(ttl_file, format="turtle")

    # Filter for subjects that are explicitly defined as Classes
    all_classes = list(mds_graph.subjects(RDF.type, OWL.Class)) + \
                  list(mds_graph.subjects(RDF.type, RDFS.Class))
    all_classes = list(set(all_classes)) # Remove duplicates
    
    total_class_count = len(all_classes)
    metric = {}
    missing_report = {name: [] for name in preds}

    # Track overall valid classes that possess BOTH predicates
    valid_count = 0

    for cls in all_classes:
        has_all_preds = True
        
        for name, pred in preds.items():
            objects = [str(o).strip() for o in mds_graph.objects(cls, pred) if str(o).strip()]
            
            if not objects:
                missing_report[name].append(str(cls))
                has_all_preds = False

        if has_all_preds:
            valid_count += 1

    # Calculate overall metrics
    percentage = (valid_count / total_class_count * 100) if total_class_count > 0 else 0
    metric["overall"] = {
        "count": valid_count,
        "percentage": f"{round(percentage, 2)}%"
    }

    print(missing_report)
    print(f"Total number of classes checked: {total_class_count}")

    error_rate = valid_count / total_class_count if total_class_count > 0 else 0

    return error_rate
