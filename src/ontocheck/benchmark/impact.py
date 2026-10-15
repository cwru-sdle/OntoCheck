"""Leave-one-out impact of concepts and relations on benchmark answers.

P is the mean of benchmark case scores from :class:`BenchmarkRunner`, not
vocabulary overlap. ``delta(c)`` is that mean on the full ontology minus the
mean after concept ``c`` is removed. The same difference is computed for a
relation. The sum of those deltas is an attributed drop; it does not
reconstruct ``P(O)``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from rdflib import BNode, Graph, Namespace, OWL, RDF, RDFS, URIRef
from rdflib.term import Node

from .evaluators import EvaluationContext
from .models import BenchmarkSuite, CaseResult, SuiteResult
from .runner import BenchmarkRunner, _averages

logger = logging.getLogger(__name__)

_BUILTIN_NAMESPACES = (
    str(RDF),
    str(RDFS),
    str(OWL),
    "http://www.w3.org/2001/XMLSchema#",
    "http://www.w3.org/2004/02/skos/core#",
)
_CLASS_TYPES = {OWL.Class, RDFS.Class}
_CLASS_AXIOMS = {RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith}
_PROPERTY_TYPES = {
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    RDF.Property,
}
_SCHEMA_RELATIONS = {
    RDFS.subClassOf,
    RDFS.subPropertyOf,
    RDFS.domain,
    RDFS.range,
    OWL.equivalentClass,
    OWL.disjointWith,
    OWL.equivalentProperty,
    OWL.propertyDisjointWith,
    OWL.inverseOf,
}


def _builtin(term: URIRef) -> bool:
    value = str(term)
    return any(value.startswith(namespace) for namespace in _BUILTIN_NAMESPACES)


def _copy_graph(graph: Graph) -> Graph:
    copied = Graph()
    for prefix, namespace in graph.namespaces():
        copied.bind(prefix, namespace)
    for triple in graph:
        copied.add(triple)
    return copied


def _bnode_closure(graph: Graph, seeds: Iterable[Node]) -> set:
    """Blank nodes reachable from ``seeds`` by walking blank-node links."""

    nodes = {node for node in seeds if isinstance(node, BNode)}
    changed = True
    while changed:
        changed = False
        for subject, _, obj in graph:
            if subject not in nodes and obj not in nodes:
                continue
            for term in (subject, obj):
                if isinstance(term, BNode) and term not in nodes:
                    nodes.add(term)
                    changed = True
    return nodes


def _appears(graph: Graph, symbol: URIRef) -> bool:
    for subject, predicate, obj in graph:
        if symbol in (subject, predicate, obj):
            return True
    return False


def ontology_concepts(graph: Graph) -> List[URIRef]:
    """Named classes that appear in an ontology graph.

    Individuals are not concepts. Built-in OWL and RDFS vocabulary, including
    ``owl:Thing`` and ``owl:Nothing``, is left out.
    """

    found = set()
    for subject, predicate, obj in graph:
        declared = (
            predicate == RDF.type
            and obj in _CLASS_TYPES
            and isinstance(subject, URIRef)
            and not _builtin(subject)
        )
        if declared:
            found.add(subject)
        if predicate in _CLASS_AXIOMS:
            for term in (subject, obj):
                if isinstance(term, URIRef) and not _builtin(term):
                    found.add(term)
        used_as_type = (
            predicate == RDF.type
            and isinstance(obj, URIRef)
            and not _builtin(obj)
            and obj not in _PROPERTY_TYPES
        )
        if used_as_type:
            found.add(obj)
    return sorted(found, key=str)


def ontology_relations(graph: Graph) -> List[URIRef]:
    """Object, data, and schema relations that appear in an ontology graph.

    ``rdf:type`` is not a relation under test. Declared properties are
    included even when no triple uses them as a predicate.
    """

    found = set()
    for subject, predicate, obj in graph:
        declared = (
            predicate == RDF.type
            and obj in _PROPERTY_TYPES
            and isinstance(subject, URIRef)
            and not _builtin(subject)
        )
        if declared:
            found.add(subject)
        if isinstance(predicate, URIRef) and not _builtin(predicate):
            found.add(predicate)
        if predicate in _SCHEMA_RELATIONS:
            found.add(predicate)
        if predicate == OWL.onProperty and isinstance(obj, URIRef):
            found.add(obj)
    return sorted(found, key=str)


def remove_concept(graph: Graph, concept: URIRef) -> Graph:
    """Return ``graph`` without concept ``concept``.

    Triples whose subject or object is ``concept`` are deleted, along with
    blank-node restrictions reachable only through those triples. A restriction
    another named term still points at is kept. The input graph is not changed.
    """

    seeds = []
    for subject, _, obj in graph:
        if subject == concept or obj == concept:
            seeds.extend((subject, obj))
    candidates = _bnode_closure(graph, seeds)
    keepers = []
    for subject, _, obj in graph:
        if subject == concept or obj == concept:
            continue
        if isinstance(subject, URIRef) and obj in candidates:
            keepers.append(obj)
    drop = candidates - _bnode_closure(graph, keepers)
    drop.add(concept)
    return _without(graph, drop, predicate=None)


def remove_relation(graph: Graph, relation: URIRef) -> Graph:
    """Return ``graph`` without relation ``relation``.

    Triples whose predicate is ``relation`` are deleted, as are domain,
    range, and other axioms about ``relation``. Blank-node restrictions on
    ``relation`` are deleted with them. The input graph is not changed.
    """

    seeds = []
    for subject, predicate, obj in graph:
        if predicate == OWL.onProperty and obj == relation:
            seeds.append(subject)
        if subject == relation:
            seeds.append(obj)
    drop = _bnode_closure(graph, seeds)
    return _without(graph, drop, predicate=relation)


def _without(graph: Graph, drop_nodes: set, predicate: Optional[URIRef]) -> Graph:
    kept = Graph()
    for prefix, namespace in graph.namespaces():
        kept.bind(prefix, namespace)
    for subject, triple_predicate, obj in graph:
        if predicate is not None and (
            triple_predicate == predicate or subject == predicate or obj == predicate
        ):
            continue
        if subject in drop_nodes or obj in drop_nodes:
            continue
        kept.add((subject, triple_predicate, obj))
    return kept


def _union(ontology: Graph, knowledge_graph: Optional[Graph]) -> Graph:
    combined = _copy_graph(ontology)
    if knowledge_graph is None:
        return combined
    for prefix, namespace in knowledge_graph.namespaces():
        combined.bind(prefix, namespace)
    for triple in knowledge_graph:
        combined.add(triple)
    return combined


def _case_scores(result: SuiteResult) -> Dict[str, float]:
    return {case.case_id: case.score for case in result.results}


@dataclass
class ImpactRow:
    """Answerability change after removing one concept or relation."""

    symbol: str
    kind: str
    baseline: float
    ablated: float
    delta: float
    changed_questions: Tuple[str, ...] = ()
    question_deltas: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-ready row."""

        return {
            "symbol": self.symbol,
            "kind": self.kind,
            "baseline": self.baseline,
            "ablated": self.ablated,
            "delta": self.delta,
            "changed_questions": list(self.changed_questions),
            "question_deltas": dict(self.question_deltas),
        }


@dataclass
class ImpactReport:
    """Leave-one-out impact of each concept and relation in an ontology.

    ``attributed_drop`` is the sum of per-symbol deltas. Leave-one-out
    double-counts alternatives and misses combinations, so this sum is not
    ``P`` of the full ontology.
    """

    baseline: float
    rows: List[ImpactRow]
    attributed_drop: float

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-ready report."""

        return {
            "baseline": self.baseline,
            "attributed_drop": self.attributed_drop,
            "rows": [row.as_dict() for row in self.rows],
        }


def _symbols(
    graph: Graph,
    kind: str,
    requested: Optional[Iterable[URIRef]],
    discovered: Sequence[URIRef],
) -> List[URIRef]:
    symbols = list(discovered if requested is None else requested)
    present = []
    for symbol in symbols:
        if not isinstance(symbol, URIRef):
            raise TypeError(
                "{} symbols must be IRI references".format(kind)
            )
        if _appears(graph, symbol):
            present.append(symbol)
        else:
            logger.debug("Skipping %s %s because it is not in the ontology", kind, symbol)
    return present


# These evaluators call the reasoner on the asserted graph themselves.
# Materializing first would collapse graph_path hop counts, so their P
# would no longer be the suite's case score.
_REASONING_TASKS = {"deduction", "constrained_plan"}


def _prepare(suite: BenchmarkSuite, graph: Graph) -> Graph:
    prepared = Graph()
    for prefix, uri in suite.namespaces.items():
        prepared.bind(prefix, Namespace(uri))
    for prefix, namespace in graph.namespaces():
        prepared.bind(prefix, namespace)
    for triple in graph:
        prepared.add(triple)
    return prepared


def _score(
    runner: BenchmarkRunner,
    suite: BenchmarkSuite,
    ontology: Graph,
    knowledge_graph: Optional[Graph],
) -> SuiteResult:
    """Score ``ontology`` union the knowledge graph.

    Asserted SPARQL (profile ``none``) does not call a reasoner. When a
    profile is set, SPARQL cases are scored on a graph materialized after
    ablation. Deduction and constrained-plan cases keep the asserted graph
    and invoke the reasoner themselves, which is the suite's own predicate.
    """

    graph = _union(ontology, knowledge_graph)
    profile = suite.inference_profile
    sparql_graph = graph
    needs_sparql_inference = profile != "none" and any(
        case.task_type not in _REASONING_TASKS for case in suite.cases
    )
    if needs_sparql_inference:
        sparql_graph = runner.reasoners.materialize(profile, graph)

    prepared_asserted = _prepare(suite, graph)
    prepared_sparql = (
        prepared_asserted
        if sparql_graph is graph
        else _prepare(suite, sparql_graph)
    )
    results = []
    for case in suite.cases:
        chosen = (
            prepared_asserted
            if profile == "none" or case.task_type in _REASONING_TASKS
            else prepared_sparql
        )
        context = EvaluationContext(
            graph=chosen,
            inference_profile=profile,
            reasoners=runner.reasoners,
        )
        started = perf_counter()
        try:
            result = runner.registry.get(case.task_type).evaluate(case, context)
        except Exception as error:
            result = CaseResult(
                case_id=case.id,
                level=case.level.value,
                task_type=case.task_type,
                status="error",
                score=0.0,
                answer_score=0.0,
                diagnostics=[str(error)],
            )
        result.inference_profile = profile
        result.runtime_ms = (perf_counter() - started) * 1000
        results.append(result)

    if not results:
        raise ValueError("A benchmark suite must contain at least one case")
    score = sum(result.score for result in results) / len(results)
    return SuiteResult(
        suite_id=suite.suite_id,
        score=score,
        results=results,
        scores_by_level=_averages(results, "level"),
        scores_by_task_type=_averages(results, "task_type"),
        context=suite.context,
    )


def assess_impact(
    suite: BenchmarkSuite,
    ontology: Graph,
    knowledge_graph: Optional[Graph] = None,
    concepts: Optional[Iterable[URIRef]] = None,
    relations: Optional[Iterable[URIRef]] = None,
    runner: Optional[BenchmarkRunner] = None,
) -> ImpactReport:
    """Measure leave-one-out answerability for concepts and relations in ``ontology``.

    Queries stay as written. Only the ontology graph is ablated; the knowledge
    graph, when given, is unioned unchanged before each score. Symbols that do
    not appear in the ontology are skipped. When ``concepts`` or ``relations``
    is omitted, the symbols are the classes and relations discovered in the
    ontology.
    """

    scorer = runner or BenchmarkRunner()
    concept_iris = _symbols(
        ontology, "concept", concepts, ontology_concepts(ontology)
    )
    relation_iris = _symbols(
        ontology, "relation", relations, ontology_relations(ontology)
    )
    baseline_result = _score(scorer, suite, ontology, knowledge_graph)
    baseline_scores = _case_scores(baseline_result)
    rows = []
    for kind, symbol, ablated in _ablations(ontology, concept_iris, relation_iris):
        ablated_result = _score(scorer, suite, ablated, knowledge_graph)
        ablated_scores = _case_scores(ablated_result)
        question_deltas = {
            case_id: baseline_scores[case_id] - ablated_scores.get(case_id, 0.0)
            for case_id in baseline_scores
        }
        changed = tuple(
            case_id
            for case_id, delta in question_deltas.items()
            if delta != 0.0
        )
        rows.append(
            ImpactRow(
                symbol=str(symbol),
                kind=kind,
                baseline=baseline_result.score,
                ablated=ablated_result.score,
                delta=baseline_result.score - ablated_result.score,
                changed_questions=changed,
                question_deltas=question_deltas,
            )
        )
        logger.debug(
            "Impact %s %s delta=%s changed=%s",
            kind,
            symbol,
            rows[-1].delta,
            changed,
        )
    attributed = sum(row.delta for row in rows)
    return ImpactReport(
        baseline=baseline_result.score,
        rows=rows,
        attributed_drop=attributed,
    )


def _ablations(
    ontology: Graph,
    concepts: Sequence[URIRef],
    relations: Sequence[URIRef],
) -> List[Tuple[str, URIRef, Graph]]:
    ablations = []
    for concept in concepts:
        ablations.append(("concept", concept, remove_concept(ontology, concept)))
    for relation in relations:
        ablations.append(("relation", relation, remove_relation(ontology, relation)))
    return ablations
