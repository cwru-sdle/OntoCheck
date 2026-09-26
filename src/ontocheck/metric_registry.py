"""
OntoCheck Metric Registry

Provides descriptor and result types that let every metric declare where it
comes from, what it costs to run, and how its score should be interpreted.

The original ``METRIC_DISPATCHER`` in ``run_assessment`` maps a metric name
directly to a callable and writes whatever that callable returns into a
three-column CSV.  That is sufficient for eighteen hand-written metrics but
does not scale to the metrics imported from the OQuaRE, OOPS! and FOOPS!
frameworks, which additionally require:

* **Provenance** -- the catalogue item a metric implements (an OOPS! pitfall
  code, a FOOPS! test identifier, an OQuaRE metric abbreviation), so that
  results can be reported against the source framework.
* **Severity** -- OOPS! classifies pitfalls as critical, important or minor.
  Any aggregate quality score must weight them accordingly.
* **Execution requirements** -- whether a metric needs network access, an
  ABox (instance data), or a reasoner.  Needed so that offline and
  continuous-integration runs can skip cleanly rather than fail.
* **Scale** -- OOPS! and FOOPS! produce counts and booleans while OQuaRE
  produces values normalised to a 1--5 quality scale.  Aggregation requires
  knowing which is which.
* **Structured findings** -- the list of affected entities, returned as data
  rather than emitted to a log, so that results can be consumed
  programmatically.

Source
------
Framework identifiers and severity levels follow:

* OOPS! Pitfall Catalogue -- https://oops.linkeddata.es/catalogue.jsp
* FOOPS! Metric and Test Catalogue -- https://w3id.org/foops/catalog
* OQuaRE -- Duque-Ramos et al. (2011), *OQuaRE: A SQuaRE-based approach for
  evaluating the quality of ontologies*

Version: 0.0.1
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SourceFramework(str, Enum):
    """
    Provenance of a metric.

    Definitions
    -----------
    - ``ONTOCHECK``: originally authored for OntoCheck, with no direct
      counterpart in an external framework.
    - ``OOPS``: implements an item from the OOPS! Pitfall Catalogue.
    - ``FOOPS``: implements a test from the FOOPS! FAIR test catalogue.
    - ``OQUARE``: implements a metric from the OQuaRE quality model.

    Source
    ------
    https://oops.linkeddata.es/catalogue.jsp,
    https://w3id.org/foops/catalog,
    Duque-Ramos et al. (2011)
    """

    ONTOCHECK = "OntoCheck"
    OOPS = "OOPS!"
    FOOPS = "FOOPS!"
    OQUARE = "OQuaRE"


class Severity(str, Enum):
    """
    Severity of a detected defect.

    Definitions
    -----------
    - ``CRITICAL``: OOPS! "critical" -- must be corrected; otherwise the
      ontology's consistency, applicability or reasoning behaviour is affected.
    - ``IMPORTANT``: OOPS! "important" -- not critical for reasoning, but
      correction is advised.
    - ``MINOR``: OOPS! "minor" -- does not cause a problem, but correcting it
      improves the ontology.
    - ``INFO``: no defect semantics; the metric reports a measurement rather
      than a pitfall.  Used for the OQuaRE structural metrics.

    Source
    ------
    OOPS! Pitfall Catalogue -- https://oops.linkeddata.es/catalogue.jsp
    """

    CRITICAL = "critical"
    IMPORTANT = "important"
    MINOR = "minor"
    INFO = "info"


class Scale(str, Enum):
    """
    Interpretation of a metric's numeric score.

    Definitions
    -----------
    - ``BOOLEAN``: the metric passes or fails; ``score`` is ``True``/``False``.
    - ``COUNT``: ``score`` is a non-negative count of affected entities, where
      zero is the desirable value.
    - ``PROPORTION``: ``score`` lies in [0, 1], where 1 is the desirable value.
    - ``OQUARE_1_5``: ``score`` lies in [1, 5] following the OQuaRE scaling
      functions, where 5 is the desirable value.
    - ``RAW``: an unnormalised measurement with no inherent direction.

    Notes
    -----
    ``higher_is_better`` on :class:`MetricDescriptor` disambiguates direction
    for the ``COUNT`` and ``RAW`` scales.
    """

    BOOLEAN = "boolean"
    COUNT = "count"
    PROPORTION = "proportion"
    OQUARE_1_5 = "oquare_1_5"
    RAW = "raw"


class Category(str, Enum):
    """
    Functional grouping used for CLI selection and reporting.

    Definitions
    -----------
    The four original OntoCheck categories (``LABELING``, ``STRUCTURAL``,
    ``ACCESSIBILITY``, ``NAMING``) are retained so that existing behaviour is
    unchanged.  ``METADATA``, ``PROVENANCE``, ``VERSIONING`` and
    ``QUALITY_MODEL`` are added for the imported framework metrics.
    """

    LABELING = "labeling"
    STRUCTURAL = "structural"
    ACCESSIBILITY = "accessibility"
    NAMING = "naming"
    METADATA = "metadata"
    PROVENANCE = "provenance"
    VERSIONING = "versioning"
    QUALITY_MODEL = "quality_model"
    TASK_BASED = "task_based"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class MetricResult:
    """
    Structured result returned by a metric.

    Replaces the previous convention in which metrics emitted their findings
    through :mod:`logging` and returned ``None``, which left the ``Score``
    column of ``assessment_scores.csv`` empty for several metrics.

    Version: 0.0.1

    Parameters
    ----------
    metric_id : str
        Registry identifier of the metric that produced this result.
    score : bool, int, float, or None
        The metric's value, interpreted according to the descriptor's
        :class:`Scale`.  ``None`` indicates the metric could not be computed.
    passed : bool or None
        Whether the ontology passes this check.  ``None`` for measurement
        metrics that carry no pass/fail semantics.
    affected : list, optional
        Entities implicated by the finding, as URI strings.  Empty when the
        check passes or the metric is a pure measurement.
    total_examined : int, optional
        Size of the population the metric examined, so that a count can be
        interpreted relative to ontology size.
    detail : dict, optional
        Additional metric-specific values.
    message : str, optional
        One-line human-readable summary.
    status : str, optional
        ``"Success"``, ``"Skipped: <reason>"`` or ``"Error: <message>"``.
        Mirrors the ``Status`` column written by ``run_assessment``.

    Examples
    --------
    >>> MetricResult(
    ...     metric_id="oopsP06CycleCheck",
    ...     score=2,
    ...     passed=False,
    ...     affected=["http://example.org/A", "http://example.org/B"],
    ...     total_examined=418,
    ...     message="2 classes participate in subsumption cycles",
    ... )
    """

    metric_id: str
    score: Any = None
    passed: Optional[bool] = None
    affected: List[str] = field(default_factory=list)
    total_examined: int = 0
    detail: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    status: str = "Success"

    def to_row(self):
        """
        Convert to the three-column dict written by ``run_assessment``.

        Returns
        -------
        dict
            Mapping with ``Metric``, ``Score`` and ``Status`` keys, matching
            the existing CSV schema so that downstream consumers of
            ``assessment_scores.csv`` continue to work unchanged.
        """
        return {
            "Metric": self.metric_id,
            "Score": self.score if self.score is not None else "N/A",
            "Status": self.status,
        }

    def to_extended_row(self):
        """
        Convert to an extended dict including provenance and findings.

        Returns
        -------
        dict
            Mapping with ``Metric``, ``Score``, ``Passed``, ``Affected``,
            ``TotalExamined``, ``Message`` and ``Status`` keys.  Intended for
            the richer CSV written when the new framework metrics are run.
        """
        return {
            "Metric": self.metric_id,
            "Score": self.score if self.score is not None else "N/A",
            "Passed": "" if self.passed is None else self.passed,
            "Affected": len(self.affected),
            "TotalExamined": self.total_examined,
            "Message": self.message,
            "Status": self.status,
        }


# ---------------------------------------------------------------------------
# Descriptor type
# ---------------------------------------------------------------------------

@dataclass
class MetricDescriptor:
    """
    Declarative description of a single metric.

    Version: 0.0.2

    Parameters
    ----------
    metric_id : str
        Unique registry key, also the name accepted by ``--metrics``.
    name : str
        Human-readable metric name.
    function : callable
        Implementation.  Called as ``function(ttl_file, **kwargs)`` and
        expected to return a :class:`MetricResult`.
    category : Category
        Functional grouping used for CLI selection and reporting.
    source_framework : SourceFramework
        Framework the metric derives from.
    source_id : str, optional
        Identifier within that framework -- an OOPS! pitfall code such as
        ``"P06"``, a FOOPS! test identifier such as ``"VER1-T"``, or an
        OQuaRE abbreviation such as ``"DITOnto"``.  Empty for metrics
        original to OntoCheck.
    source_url : str, optional
        Direct link to the catalogue entry.
    severity : Severity, optional
        Severity assigned by the source framework.
    scale : Scale, optional
        Interpretation of the returned score.
    higher_is_better : bool, optional
        Direction of improvement, for the ``COUNT`` and ``RAW`` scales.
    requires_network : bool, optional
        Whether the metric performs HTTP requests.  Such metrics are skipped
        when assessment is run with networking disabled.
    requires_abox : bool, optional
        Whether the metric requires instance data.  Several OQuaRE metrics
        (notably ``CROnto``) are undefined over a TBox alone.
    requires_reasoner : bool, optional
        Whether the metric requires a DL reasoner.
    requires_questions : bool, optional
        Whether the metric needs competency questions (SPARQL) in addition to
        the ontology.  Such metrics receive ``questions``,
        ``domain_prefixes`` and ``domain_ns_fragments`` keyword arguments and
        are skipped when no questions are supplied.
    fair_principle : str, optional
        FAIR principle addressed, for FOOPS!-derived tests (e.g. ``"F1"``).
    description : str, optional
        One-line summary shown in ``--list-metrics`` output.

    Notes
    -----
    ``requires_network``, ``requires_abox`` and ``requires_reasoner`` exist so
    that a metric can be skipped with an informative status rather than
    raising.  The previous dispatcher caught every exception and recorded
    ``Error: <message>``, which conflates "cannot run here" with "is broken".
    """

    metric_id: str
    name: str
    function: Callable
    category: Category
    source_framework: SourceFramework
    source_id: str = ""
    source_url: str = ""
    severity: Severity = Severity.INFO
    scale: Scale = Scale.COUNT
    higher_is_better: bool = False
    requires_network: bool = False
    requires_abox: bool = False
    requires_reasoner: bool = False
    requires_questions: bool = False
    fair_principle: str = ""
    description: str = ""

    @property
    def provenance(self):
        """
        Return a citation string for this metric.

        Returns
        -------
        str
            For example ``"OOPS! P06"`` or ``"OQuaRE DITOnto"``.  For metrics
            original to OntoCheck, just ``"OntoCheck"``.
        """
        if self.source_id:
            return f"{self.source_framework.value} {self.source_id}"
        return self.source_framework.value


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

METRIC_REGISTRY: Dict[str, MetricDescriptor] = {}


def register_metric(descriptor):
    """
    Add a metric descriptor to the global registry.

    Version: 0.0.1

    Parameters
    ----------
    descriptor : MetricDescriptor
        The descriptor to register.

    Returns
    -------
    MetricDescriptor
        The registered descriptor, so that this function may be used as a
        decorator factory or in an assignment.

    Raises
    ------
    ValueError
        If a metric with the same ``metric_id`` is already registered.
    """
    if descriptor.metric_id in METRIC_REGISTRY:
        raise ValueError(
            f"Metric '{descriptor.metric_id}' is already registered "
            f"(existing: {METRIC_REGISTRY[descriptor.metric_id].provenance})."
        )
    METRIC_REGISTRY[descriptor.metric_id] = descriptor
    return descriptor


def get_metric(metric_id):
    """
    Look up a registered metric descriptor.

    Parameters
    ----------
    metric_id : str
        Registry identifier.

    Returns
    -------
    MetricDescriptor or None
        The descriptor, or ``None`` if not registered.
    """
    return METRIC_REGISTRY.get(metric_id)


def metrics_by_framework(framework):
    """
    Return all metric identifiers deriving from a given framework.

    Parameters
    ----------
    framework : SourceFramework
        Framework to filter by.

    Returns
    -------
    list of str
        Sorted metric identifiers.

    Examples
    --------
    >>> metrics_by_framework(SourceFramework.OOPS)   # doctest: +SKIP
    ['oopsP06CycleCheck', 'oopsP10DisjointnessCheck', ...]
    """
    return sorted(
        m_id for m_id, d in METRIC_REGISTRY.items()
        if d.source_framework == framework
    )


def metrics_by_category(category):
    """
    Return all metric identifiers in a given category.

    Parameters
    ----------
    category : Category
        Category to filter by.

    Returns
    -------
    list of str
        Sorted metric identifiers.
    """
    return sorted(
        m_id for m_id, d in METRIC_REGISTRY.items()
        if d.category == category
    )


def runnable_metrics(allow_network=True, has_abox=False, has_reasoner=False,
                     has_questions=False):
    """
    Return the metrics that can execute under the given capabilities.

    Version: 0.0.2

    Parameters
    ----------
    allow_network : bool, optional
        Whether outbound HTTP requests are permitted.  Default ``True``.
    has_abox : bool, optional
        Whether instance data is available.  Default ``False``, matching the
        TBox-only assumption of the current package.
    has_reasoner : bool, optional
        Whether a DL reasoner is available.  Default ``False``.
    has_questions : bool, optional
        Whether competency questions are available.  Default ``False``.

    Returns
    -------
    list of str
        Sorted identifiers of metrics whose requirements are satisfied.

    Notes
    -----
    Use this rather than catching exceptions to determine runnability, so that
    "cannot run in this environment" is reported distinctly from "failed".
    """
    out = []
    for m_id, d in METRIC_REGISTRY.items():
        if d.requires_network and not allow_network:
            continue
        if d.requires_abox and not has_abox:
            continue
        if d.requires_reasoner and not has_reasoner:
            continue
        if d.requires_questions and not has_questions:
            continue
        out.append(m_id)
    return sorted(out)


def skip_reason(descriptor, allow_network=True, has_abox=False,
                has_reasoner=False, has_questions=False):
    """
    Explain why a metric cannot run, if it cannot.

    Parameters
    ----------
    descriptor : MetricDescriptor
        Metric to test.
    allow_network : bool, optional
        Whether outbound HTTP requests are permitted.
    has_abox : bool, optional
        Whether instance data is available.
    has_reasoner : bool, optional
        Whether a DL reasoner is available.
    has_questions : bool, optional
        Whether competency questions were supplied.  Default ``False``.

    Returns
    -------
    str or None
        A reason string suitable for the ``Status`` column, or ``None`` if the
        metric can run.
    """
    if descriptor.requires_network and not allow_network:
        return "Skipped (requires network access)"
    if descriptor.requires_abox and not has_abox:
        return "Skipped (requires instance data / ABox)"
    if descriptor.requires_reasoner and not has_reasoner:
        return "Skipped (requires a DL reasoner)"
    if descriptor.requires_questions and not has_questions:
        return "Skipped (requires competency questions)"
    return None


def build_dispatcher():
    """
    Build a flat ``{name: callable}`` mapping for backward compatibility.

    The original ``METRIC_DISPATCHER`` is a flat dictionary consumed directly
    by ``run_assessment._run_agnostic_metrics`` and by ``cli._build_parser``.
    This function reproduces that shape from the registry so that registry
    metrics can be invoked through the existing code path without change.

    Version: 0.0.2

    Returns
    -------
    dict
        Mapping from metric identifier to implementation callable.

    Notes
    -----
    Callables reached this way return :class:`MetricResult` objects rather
    than bare scores.  ``MetricResult.to_row`` restores the original CSV
    shape, so the compatibility shim in ``run_assessment`` should call it.
    """
    return {m_id: d.function for m_id, d in METRIC_REGISTRY.items()}


def summarise_registry():
    """
    Summarise registry contents by framework and category.

    Returns
    -------
    dict
        Mapping with ``by_framework`` and ``by_category`` sub-dictionaries of
        counts, plus a ``total`` key.

    Examples
    --------
    >>> summarise_registry()["total"]   # doctest: +SKIP
    15
    """
    by_framework = {}
    by_category = {}
    for d in METRIC_REGISTRY.values():
        by_framework[d.source_framework.value] = (
            by_framework.get(d.source_framework.value, 0) + 1
        )
        by_category[d.category.value] = by_category.get(d.category.value, 0) + 1
    return {
        "total": len(METRIC_REGISTRY),
        "by_framework": by_framework,
        "by_category": by_category,
    }
