from rdflib import Graph, Namespace, OWL, RDF, RDFS

def mds_design_check_v_0_0_1(ttl_file):
    MDS = Namespace("https://cwrusdle.bitbucket.io/mds/")
    preds = {
        "hasDomain": MDS.hasDomain,
        "hasSubDomain": MDS.hasSubDomain,
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

    valid_count = 0
    for name, pred in preds.items():
        valid_count = 0
        for cls in all_classes:
            # Check for at least one non-empty object for this predicate
            objects = [str(o).strip() for o in mds_graph.objects(cls, pred) if str(o).strip()]
            
            if objects:
                valid_count += 1
            else:
                missing_report[name].append(str(cls))

        # Calculate percentage
        percentage = (valid_count / total_class_count * 100) if total_class_count > 0 else 0
        metric[name] = {
            "count": valid_count,
            "percentage": f"{round(percentage, 2)}%"
        }

    print(missing_report)
    print(f"Total number of classes checked: {total_class_count}")

    error_rate = valid_count / total_class_count

    return error_rate
