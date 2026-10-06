"""Reasoner contracts, registry, and built-in graph-path implementation."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

from rdflib import Graph, OWL, RDF, RDFS, URIRef

from .models import BenchmarkCase


class UnsupportedReasoner(ValueError):
    """Raised when no reasoner is registered for an inference profile."""


@dataclass(frozen=True)
class ReasonerAnswer:
    """One reasoned RDF answer and its optional supporting proof."""

    value: URIRef
    proof: Tuple[Tuple[URIRef, URIRef, URIRef], ...] = ()


class Reasoner(Protocol):
    """Adapter interface implemented by graph and external reasoners."""

    name: str

    def reason(self, case: BenchmarkCase, graph: Graph) -> List[ReasonerAnswer]:
        """Return RDF answers and optional proofs for one reasoning case."""


class MaterializingReasoner(Reasoner, Protocol):
    """Optional reasoner capability required by constrained plan checks."""

    def materialize(self, graph: Graph) -> Graph:
        """Return a graph containing the profile's supported entailments."""


class ReasonerRegistry:
    """Map inference-profile names to replaceable reasoner adapters."""

    def __init__(self) -> None:
        self._reasoners: Dict[str, Reasoner] = {}

    def register(
        self, profile: str, reasoner: Reasoner, replace: bool = False
    ) -> None:
        """Register a reasoner, rejecting accidental replacement."""

        if profile in self._reasoners and not replace:
            raise ValueError(
                "A reasoner is already registered for {!r}".format(profile)
            )
        self._reasoners[profile] = reasoner

    def get(self, profile: str) -> Reasoner:
        """Return the reasoner configured for an inference profile."""

        try:
            return self._reasoners[profile]
        except KeyError as error:
            raise UnsupportedReasoner(
                "No reasoner registered for inference profile {!r}".format(profile)
            ) from error

    def materialize(self, profile: str, graph: Graph) -> Graph:
        """Return a graph containing entailments supported by a profile."""

        if profile == "none":
            return graph
        reasoner = self.get(profile)
        materialize = getattr(reasoner, "materialize", None)
        if not callable(materialize):
            raise UnsupportedReasoner(
                "Reasoner for inference profile {!r} does not support "
                "graph materialization".format(profile)
            )
        return materialize(graph)


def _resolve_identifier(value: Any, graph: Graph, location: str) -> URIRef:
    if not isinstance(value, str) or not value:
        raise ValueError("{} must be a non-empty RDF identifier".format(location))
    if value.startswith("<") and value.endswith(">"):
        return URIRef(value[1:-1])
    if "://" in value:
        return URIRef(value)
    if ":" not in value:
        raise ValueError("{} must be an IRI or prefixed name".format(location))

    prefix, local_name = value.split(":", 1)
    namespaces = dict(graph.namespaces())
    if prefix not in namespaces:
        raise ValueError("Unknown namespace prefix {!r}".format(prefix))
    return URIRef(str(namespaces[prefix]) + local_name)


def _positive_integer(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("{} must be a positive integer".format(location))
    return value


class GraphPathReasoner:
    """Derive reachable named resources along a transitive RDF predicate."""

    name = "graph-path-v1"

    def materialize(self, graph: Graph) -> Graph:
        """Materialize closure for declared and built-in transitive predicates."""

        materialized = Graph()
        for prefix, namespace in graph.namespaces():
            materialized.bind(prefix, namespace)
        for triple in graph:
            materialized.add(triple)

        predicates = {
            RDFS.subClassOf,
            RDFS.subPropertyOf,
            *graph.subjects(RDF.type, OWL.TransitiveProperty),
        }
        for predicate in predicates:
            adjacency: Dict[Any, List[Any]] = {}
            for source, target in graph.subject_objects(predicate):
                adjacency.setdefault(source, []).append(target)

            for source in adjacency:
                queue = deque(adjacency[source])
                visited = set()
                while queue:
                    target = queue.popleft()
                    if target in visited:
                        continue
                    visited.add(target)
                    materialized.add((source, predicate, target))
                    queue.extend(adjacency.get(target, ()))

        return materialized

    def reason(self, case: BenchmarkCase, graph: Graph) -> List[ReasonerAnswer]:
        if case.query.language != "graph_path":
            raise ValueError("graph_path reasoner requires a graph_path query")

        parameters = case.query.parameters
        source = _resolve_identifier(parameters.get("source"), graph, "source")
        predicate = _resolve_identifier(
            parameters.get("predicate"), graph, "predicate"
        )
        min_hops = _positive_integer(parameters.get("min_hops", 1), "min_hops")
        max_hops = _positive_integer(parameters.get("max_hops", 5), "max_hops")
        if max_hops < min_hops:
            raise ValueError("max_hops must be greater than or equal to min_hops")

        inherently_transitive = {
            RDFS.subClassOf,
            RDFS.subPropertyOf,
        }
        if (
            predicate not in inherently_transitive
            and (predicate, RDF.type, OWL.TransitiveProperty) not in graph
        ):
            predicate_name = predicate.n3(
                namespace_manager=graph.namespace_manager
            )
            raise ValueError("{} is not declared transitive".format(predicate_name))

        queue = deque([(source, ())])
        shortest_depth = {source: 0}
        answers = []

        while queue:
            current, proof = queue.popleft()
            depth = len(proof)
            if depth >= max_hops:
                continue

            neighbors = sorted(
                (
                    candidate
                    for candidate in graph.objects(current, predicate)
                    if isinstance(candidate, URIRef)
                ),
                key=str,
            )
            for neighbor in neighbors:
                next_depth = depth + 1
                if neighbor in shortest_depth:
                    continue
                shortest_depth[neighbor] = next_depth
                next_proof = proof + ((current, predicate, neighbor),)
                queue.append((neighbor, next_proof))
                if next_depth >= min_hops:
                    answers.append(
                        ReasonerAnswer(value=neighbor, proof=next_proof)
                    )

        return answers


class HermiTReasoner:
    """Classify an ontology with the in-process hermitpy reasoner.

    ``materialize`` copies the input graph and adds the direct
    ``rdfs:subClassOf`` links from hermitpy. ``reason`` answers ``graph_path``
    queries on that classified graph. Suites that do not select the ``hermit``
    profile never import hermitpy.
    """

    name = "hermitpy-v1"

    def materialize(self, graph: Graph) -> Graph:
        """Return the graph plus the classified direct subclass hierarchy."""

        pairs = self._reasoner(graph).direct_subclasses()
        materialized = Graph()
        for prefix, namespace in graph.namespaces():
            materialized.bind(prefix, namespace)
        for triple in graph:
            materialized.add(triple)
        for child, parent in pairs:
            materialized.add((URIRef(child), RDFS.subClassOf, URIRef(parent)))
        return materialized

    def reason(self, case: BenchmarkCase, graph: Graph) -> List[ReasonerAnswer]:
        """Answer a graph-path query against the classified hierarchy."""

        if case.query.language != "graph_path":
            raise ValueError(
                "hermit reasoner currently answers graph_path queries "
                "on the classified hierarchy"
            )
        return GraphPathReasoner().reason(case, self.materialize(graph))

    def _reasoner(self, graph: Graph):
        try:
            from hermitpy import Reasoner as HermitPyReasoner
        except ImportError as error:
            raise UnsupportedReasoner(
                "The hermit profile requires the hermitpy package. "
                "Install the sibling project with pip install -e ../hermitpy."
            ) from error
        return HermitPyReasoner(graph)


class OwlreadyReasoner:
    """Classify an ontology with HermiT through owlready2.

    Owlready2 ships HermiT and runs it with ``java``. ``JAVA_EXE`` stays
    ``java`` when that command is on ``PATH``. A full path is used only when
    Java is installed but not on ``PATH``, via ``JAVA_HOME``.
    """

    name = "owlready2-hermit"

    def materialize(self, graph: Graph) -> Graph:
        """Return the graph plus HermiT's direct subclass hierarchy."""

        pairs = self._direct_pairs(graph)
        materialized = Graph()
        for prefix, namespace in graph.namespaces():
            materialized.bind(prefix, namespace)
        for triple in graph:
            materialized.add(triple)
        for child, parent in pairs:
            materialized.add((URIRef(child), RDFS.subClassOf, URIRef(parent)))
        return materialized

    def reason(self, case: BenchmarkCase, graph: Graph) -> List[ReasonerAnswer]:
        """Answer a graph-path query against the classified hierarchy."""

        if case.query.language != "graph_path":
            raise ValueError(
                "owlready reasoner currently answers graph_path queries "
                "on the classified hierarchy"
            )
        return GraphPathReasoner().reason(case, self.materialize(graph))

    def _direct_pairs(self, graph: Graph) -> List[Tuple[str, str]]:
        owlready2, sync_reasoner, world_cls = self._owlready()
        self._use_java(owlready2)
        prepared = _declare_named_classes(graph)
        temp_path = _write_rdfxml(prepared)
        world = world_cls()
        try:
            onto = world.get_ontology(temp_path.as_uri()).load()
            try:
                sync_reasoner(onto, debug=0)
            except FileNotFoundError as error:
                raise UnsupportedReasoner(
                    "The owlready profile could not start Java. "
                    "Install a JDK and check that `java -version` works."
                ) from error
            return _pairs_from_world(world)
        finally:
            temp_path.unlink(missing_ok=True)
            close = getattr(world, "close", None)
            if callable(close):
                close()

    def _owlready(self):
        try:
            import owlready2
            from owlready2 import World, sync_reasoner
        except ImportError as error:
            raise UnsupportedReasoner(
                "The owlready profile requires owlready2. "
                "Install it with pip install owlready2."
            ) from error
        return owlready2, sync_reasoner, World

    def _use_java(self, owlready2) -> str:
        """Point owlready2 at a JVM without a hardcoded executable path."""

        configured = getattr(owlready2, "JAVA_EXE", "java")
        if configured and configured != "java" and Path(configured).is_file():
            return configured
        found = shutil.which("java")
        if not found:
            home = os.environ.get("JAVA_HOME")
            if home:
                name = "java.exe" if os.name == "nt" else "java"
                candidate = Path(home) / "bin" / name
                if candidate.is_file():
                    found = str(candidate)
        if not found:
            raise UnsupportedReasoner(
                "The owlready profile needs Java on PATH. "
                "Install a JDK and check `java -version`. "
                "If Java is installed but not on PATH, set JAVA_HOME."
            )
        owlready2.JAVA_EXE = found
        return found


def _declare_named_classes(graph: Graph) -> Graph:
    """Add class declarations so owlready2 keeps named subclass terms."""

    prepared = Graph()
    for prefix, namespace in graph.namespaces():
        prepared.bind(prefix, namespace)
    for triple in graph:
        prepared.add(triple)
    terms = set()
    for predicate in (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith):
        terms.update(prepared.subjects(predicate, None))
        terms.update(prepared.objects(None, predicate))
    owl_ns = str(OWL)
    for term in terms:
        if isinstance(term, URIRef) and not str(term).startswith(owl_ns):
            prepared.add((term, RDF.type, OWL.Class))
    return prepared


def _write_rdfxml(graph: Graph) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".owl", delete=False)
    path = Path(handle.name)
    handle.close()
    graph.serialize(path, format="xml")
    return path


def _pairs_from_world(world) -> List[Tuple[str, str]]:
    pairs = set()
    for cls in world.classes():
        child = getattr(cls, "iri", None)
        if not child or str(child).startswith(str(OWL)):
            continue
        for parent in list(cls.is_a) + list(cls.equivalent_to):
            parent_iri = _named_class_iri(parent)
            if parent_iri:
                pairs.add((child, parent_iri))
    nothing = str(OWL.Nothing)
    thing = str(OWL.Thing)
    unsatisfiable = {child for child, parent in pairs if parent == nothing}
    return sorted(
        pair
        for pair in pairs
        if not (pair[0] in unsatisfiable and pair[1] == thing)
    )


def _named_class_iri(entity) -> Optional[str]:
    if entity.__class__.__name__ in {"Restriction", "And", "Or", "Not", "OneOf"}:
        return None
    iri = getattr(entity, "iri", None)
    if not isinstance(iri, str):
        return None
    return iri


def default_reasoners() -> ReasonerRegistry:
    """Create the built-in reasoner registry."""

    registry = ReasonerRegistry()
    registry.register("graph_path", GraphPathReasoner())
    registry.register("hermit", HermiTReasoner())
    registry.register("owlready", OwlreadyReasoner())
    return registry
