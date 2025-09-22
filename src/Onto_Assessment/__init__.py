from .altLabelCheck import mainAltLabelCheck_v_0_0_1
from .check_external_data_provider_links_ttl import check_external_data_provider_links_ttl
from .check_for_isolated_elements import check_for_isolated_elements
from .check_human_readable_license_ttl import check_human_readable_license_ttl
from .check_rdf_dump_accessibility_ttl import check_rdf_dump_accessibility_ttl
from .check_sparql_accessibility_ttl import check_sparql_accessibility_ttl
from .count_class_connected_components import count_class_connected_components
from .defCheck import mainDefCheck_v_0_0_1
from .find_duplicate_labels_from_graph import find_duplicate_labels_from_graph
from .get_properties_missing_domain_and_range import get_properties_missing_domain_and_range
from .leafNodeCheck import mainLeafNodeCheck_v_0_0_1
from .semanticConnection import mainSemanticConnection_v_0_0_1
from .run_assessment import run_ontology_assessment

__all__ = [
    "mainAltLabelCheck_v_0_0_1",
    "check_external_data_provider_links_ttl",
    "check_for_isolated_elements",
    "check_human_readable_license_ttl",
    "check_rdf_dump_accessibility_ttl",
    "check_sparql_accessibility_ttl",
    "count_class_connected_components",
    "mainDefCheck_v_0_0_1",
    "find_duplicate_labels_from_graph",
    "get_properties_missing_domain_and_range",
    "mainLeafNodeCheck_v_0_0_1",
    "mainSemanticConnection_v_0_0_1",
    "run_ontology_assessment"
]
