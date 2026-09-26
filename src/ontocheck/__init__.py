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
from .mds_design_check import mds_design_check_v_0_0_1
from .spell_check import spell_check_v_0_0_1
from .run_assessment import run_assessment
from .task_based_metric import task_based_metric_v_0_0_1
from .check_class_name_capital import mainClassNameCapitalCheck_v_0_0_1
from .check_class_name_space import mainClassNameSpaceCheck_v_0_0_1
from .check_label import mainLabelCheck_v_0_0_1
from .class_search import mainClassSearch_v_0_0_1
from .nlp_json import build_question_json

# ---------------------------------------------------------------------------
# Metric registry and framework integration
# ---------------------------------------------------------------------------
from .metric_registry import (
    Category,
    MetricDescriptor,
    MetricResult,
    Scale,
    Severity,
    SourceFramework,
    METRIC_REGISTRY,
    build_dispatcher,
    get_metric,
    metrics_by_category,
    metrics_by_framework,
    register_metric,
    runnable_metrics,
    skip_reason,
    summarise_registry,
)
from .framework_metrics import (
    SEVERITY_WEIGHTS,
    add_cli_arguments,
    extend_dispatcher,
    print_metric_catalogue,
    resolve_cli_frameworks,
    run_framework_metrics,
    summarise_results,
    write_extended_csv,
)

# ---------------------------------------------------------------------------
# OOPS! -- all 41 pitfalls
# ---------------------------------------------------------------------------
from .oops_lexical_checks import (
    oops_p01_polysemous_elements_v_0_0_1,
    oops_p02_synonyms_as_classes_v_0_0_1,
    oops_p03_is_relationship_v_0_0_1,
    oops_p04_unconnected_elements_v_0_0_1,
    oops_p07_merged_concepts_v_0_0_1,
    oops_p08_missing_annotations_v_0_0_1,
    oops_p11_missing_domain_range_v_0_0_1,
    oops_p12_undeclared_equivalent_properties_v_0_0_1,
    oops_p20_misused_annotations_v_0_0_1,
    oops_p22_naming_conventions_v_0_0_1,
    oops_p23_duplicated_datatype_v_0_0_1,
    oops_p30_undeclared_equivalent_classes_v_0_0_1,
    oops_p32_same_label_v_0_0_1,
    oops_p41_no_license_v_0_0_1,
)
from .oops_axiom_checks import (
    oops_p05_wrong_inverse_v_0_0_1,
    oops_p09_missing_domain_information_v_0_0_1,
    oops_p14_misused_allvaluesfrom_v_0_0_1,
    oops_p15_some_not_v_0_0_1,
    oops_p16_primitive_instead_of_defined_v_0_0_1,
    oops_p17_overspecialized_hierarchy_v_0_0_1,
    oops_p18_overspecialized_domain_range_v_0_0_1,
    oops_p27_wrong_equivalent_properties_v_0_0_1,
    oops_p28_wrong_symmetric_v_0_0_1,
    oops_p29_wrong_transitive_v_0_0_1,
    oops_p31_wrong_equivalent_classes_v_0_0_1,
    oops_p37_not_available_on_web_v_0_0_1,
)
from .oops_structural_checks import (
    oops_p06_cycle_check_v_0_0_1,
    oops_p10_disjointness_check_v_0_0_1,
    oops_p13_undeclared_inverse_check_v_0_0_1,
    oops_p19_multiple_domain_range_check_v_0_0_1,
    oops_p21_miscellaneous_class_check_v_0_0_1,
    oops_p24_recursive_definition_check_v_0_0_1,
    oops_p25_self_inverse_check_v_0_0_1,
    oops_p26_symmetric_with_inverse_check_v_0_0_1,
    oops_p33_single_property_chain_check_v_0_0_1,
    oops_p34_untyped_class_check_v_0_0_1,
    oops_p35_untyped_property_check_v_0_0_1,
    oops_p36_uri_file_extension_check_v_0_0_1,
    oops_p38_ontology_declaration_check_v_0_0_1,
    oops_p39_ambiguous_namespace_check_v_0_0_1,
    oops_p40_namespace_hijacking_check_v_0_0_1,
)

# ---------------------------------------------------------------------------
# FOOPS! -- all 24 tests
# ---------------------------------------------------------------------------
from .foops_access_checks import (
    foops_cn1_content_negotiation_v_0_0_1,
    foops_doc1_html_documentation_v_0_0_1,
    foops_find2_prefix_registered_v_0_0_1,
    foops_find3_community_registry_v_0_0_1,
    foops_find3bis_metadata_persistence_v_0_0_1,
    foops_om41_license_declared_v_0_0_1,
    foops_om42_license_resolvable_v_0_0_1,
    foops_purl1_persistent_url_v_0_0_1,
    foops_rdf1_rdf_available_v_0_0_1,
    foops_uri1_uri_resolvable_v_0_0_1,
    foops_uri2_consistent_ids_v_0_0_1,
    foops_voc1_metadata_vocabulary_reuse_v_0_0_1,
    foops_voc2_vocabulary_reuse_v_0_0_1,
)
from .foops_metadata_checks import (
    foops_find1_prefix_declared_v_0_0_1,
    foops_http1_open_protocol_v_0_0_1,
    foops_om1_minimum_metadata_v_0_0_1,
    foops_om2_recommended_metadata_v_0_0_1,
    foops_om3_detailed_metadata_v_0_0_1,
    foops_om51_basic_provenance_v_0_0_1,
    foops_om52_detailed_provenance_v_0_0_1,
    foops_voc3_all_terms_labelled_v_0_0_1,
    foops_voc4_all_terms_defined_v_0_0_1,
)
from .foops_version_checks import (
    foops_ver1_version_iri_declared_v_0_0_1,
    foops_ver2_version_iri_resolves_v_0_0_1,
)

# ---------------------------------------------------------------------------
# OQuaRE -- 18 metrics and scaling functions
# ---------------------------------------------------------------------------
from .oquare_metrics import (
    STATIC_SCALE,
    oquare_anonto_v_0_0_1,
    oquare_aronto_v_0_0_1,
    oquare_cbonto_v_0_0_1,
    oquare_cronto_v_0_0_1,
    oquare_ditonto_v_0_0_1,
    oquare_inronto_v_0_0_1,
    oquare_lcomonto_v_0_0_1,
    oquare_naconto_v_0_0_1,
    oquare_noconto_v_0_0_1,
    oquare_nomonto_v_0_0_1,
    oquare_ponto_v_0_0_1,
    oquare_pronto_v_0_0_1,
    oquare_rfconto_v_0_0_1,
    oquare_rronto_v_0_0_1,
    oquare_tmonto2_v_0_0_1,
    oquare_tmonto_v_0_0_1,
    oquare_wmconto2_v_0_0_1,
    oquare_wmconto_v_0_0_1,
    scale_dynamic,
    scale_static,
)

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
    "mds_design_check_v_0_0_1",
    "spell_check_v_0_0_1",
    "mainClassNameCapitalCheck_v_0_0_1",
    "mainClassNameSpaceCheck_v_0_0_1",
    "mainLabelCheck_v_0_0_1",
    "mainClassSearch_v_0_0_1",
    "run_assessment",
    "task_based_metric_v_0_0_1",
    "build_question_json",

    # Metric registry
    "Category",
    "MetricDescriptor",
    "MetricResult",
    "Scale",
    "Severity",
    "SourceFramework",
    "METRIC_REGISTRY",
    "build_dispatcher",
    "get_metric",
    "metrics_by_category",
    "metrics_by_framework",
    "register_metric",
    "runnable_metrics",
    "skip_reason",
    "summarise_registry",

    # Framework integration
    "SEVERITY_WEIGHTS",
    "add_cli_arguments",
    "extend_dispatcher",
    "print_metric_catalogue",
    "resolve_cli_frameworks",
    "run_framework_metrics",
    "summarise_results",
    "write_extended_csv",

    # OOPS! (P01-P41)
    "oops_p01_polysemous_elements_v_0_0_1",
    "oops_p02_synonyms_as_classes_v_0_0_1",
    "oops_p03_is_relationship_v_0_0_1",
    "oops_p04_unconnected_elements_v_0_0_1",
    "oops_p05_wrong_inverse_v_0_0_1",
    "oops_p06_cycle_check_v_0_0_1",
    "oops_p07_merged_concepts_v_0_0_1",
    "oops_p08_missing_annotations_v_0_0_1",
    "oops_p09_missing_domain_information_v_0_0_1",
    "oops_p10_disjointness_check_v_0_0_1",
    "oops_p11_missing_domain_range_v_0_0_1",
    "oops_p12_undeclared_equivalent_properties_v_0_0_1",
    "oops_p13_undeclared_inverse_check_v_0_0_1",
    "oops_p14_misused_allvaluesfrom_v_0_0_1",
    "oops_p15_some_not_v_0_0_1",
    "oops_p16_primitive_instead_of_defined_v_0_0_1",
    "oops_p17_overspecialized_hierarchy_v_0_0_1",
    "oops_p18_overspecialized_domain_range_v_0_0_1",
    "oops_p19_multiple_domain_range_check_v_0_0_1",
    "oops_p20_misused_annotations_v_0_0_1",
    "oops_p21_miscellaneous_class_check_v_0_0_1",
    "oops_p22_naming_conventions_v_0_0_1",
    "oops_p23_duplicated_datatype_v_0_0_1",
    "oops_p24_recursive_definition_check_v_0_0_1",
    "oops_p25_self_inverse_check_v_0_0_1",
    "oops_p26_symmetric_with_inverse_check_v_0_0_1",
    "oops_p27_wrong_equivalent_properties_v_0_0_1",
    "oops_p28_wrong_symmetric_v_0_0_1",
    "oops_p29_wrong_transitive_v_0_0_1",
    "oops_p30_undeclared_equivalent_classes_v_0_0_1",
    "oops_p31_wrong_equivalent_classes_v_0_0_1",
    "oops_p32_same_label_v_0_0_1",
    "oops_p33_single_property_chain_check_v_0_0_1",
    "oops_p34_untyped_class_check_v_0_0_1",
    "oops_p35_untyped_property_check_v_0_0_1",
    "oops_p36_uri_file_extension_check_v_0_0_1",
    "oops_p37_not_available_on_web_v_0_0_1",
    "oops_p38_ontology_declaration_check_v_0_0_1",
    "oops_p39_ambiguous_namespace_check_v_0_0_1",
    "oops_p40_namespace_hijacking_check_v_0_0_1",
    "oops_p41_no_license_v_0_0_1",

    # FOOPS! (24 tests, catalogue order)
    "foops_cn1_content_negotiation_v_0_0_1",
    "foops_doc1_html_documentation_v_0_0_1",
    "foops_find1_prefix_declared_v_0_0_1",
    "foops_find2_prefix_registered_v_0_0_1",
    "foops_find3_community_registry_v_0_0_1",
    "foops_find3bis_metadata_persistence_v_0_0_1",
    "foops_http1_open_protocol_v_0_0_1",
    "foops_om1_minimum_metadata_v_0_0_1",
    "foops_om2_recommended_metadata_v_0_0_1",
    "foops_om3_detailed_metadata_v_0_0_1",
    "foops_om41_license_declared_v_0_0_1",
    "foops_om42_license_resolvable_v_0_0_1",
    "foops_om51_basic_provenance_v_0_0_1",
    "foops_om52_detailed_provenance_v_0_0_1",
    "foops_purl1_persistent_url_v_0_0_1",
    "foops_rdf1_rdf_available_v_0_0_1",
    "foops_uri1_uri_resolvable_v_0_0_1",
    "foops_uri2_consistent_ids_v_0_0_1",
    "foops_ver1_version_iri_declared_v_0_0_1",
    "foops_ver2_version_iri_resolves_v_0_0_1",
    "foops_voc1_metadata_vocabulary_reuse_v_0_0_1",
    "foops_voc2_vocabulary_reuse_v_0_0_1",
    "foops_voc3_all_terms_labelled_v_0_0_1",
    "foops_voc4_all_terms_defined_v_0_0_1",

    # OQuaRE (18 metrics + scaling)
    "STATIC_SCALE",
    "scale_static",
    "scale_dynamic",
    "oquare_anonto_v_0_0_1",
    "oquare_aronto_v_0_0_1",
    "oquare_cbonto_v_0_0_1",
    "oquare_cronto_v_0_0_1",
    "oquare_ditonto_v_0_0_1",
    "oquare_inronto_v_0_0_1",
    "oquare_lcomonto_v_0_0_1",
    "oquare_naconto_v_0_0_1",
    "oquare_noconto_v_0_0_1",
    "oquare_nomonto_v_0_0_1",
    "oquare_ponto_v_0_0_1",
    "oquare_pronto_v_0_0_1",
    "oquare_rfconto_v_0_0_1",
    "oquare_rronto_v_0_0_1",
    "oquare_tmonto_v_0_0_1",
    "oquare_tmonto2_v_0_0_1",
    "oquare_wmconto_v_0_0_1",
    "oquare_wmconto2_v_0_0_1",
]