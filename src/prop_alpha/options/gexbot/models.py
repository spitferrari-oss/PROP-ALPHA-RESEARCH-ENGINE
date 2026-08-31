"""GEXBOT data models (extension spec §26-27): every metric this adapter
can report is paired with its own `MetricAvailability` — extension §26
explicitly warns that not every metric is available at the same
frequency or on the same endpoint, and §27 requires availability/
timestamp/source/freshness tracked *per metric*, not once for the whole
snapshot. A metric GEXBOT doesn't currently report is `value=None` with
`availability.status=UNAVAILABLE` — never silently defaulted to `0`
(extension §51-52's "zero and missing are never the same thing").
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class MetricAvailability:
    status: AvailabilityStatus
    timestamp: dt.datetime | None
    source: str
    freshness_seconds: float | None


@dataclass(frozen=True)
class Metric:
    value: float | None
    availability: MetricAvailability


@dataclass(frozen=True)
class GexSnapshot:
    """Extension §26's metric list, to the extent a snapshot-style
    endpoint can carry it. Options order flow (§34) is deliberately not a
    field here — it's a time series, not a snapshot value, and belongs to
    `orderflow.py` (Phase K), not this model.
    """
    underlying: str
    spot: Metric
    gex: Metric
    dex: Metric
    gamma_flip: Metric
    major_positive_gamma: Metric
    major_negative_gamma: Metric
    vanna: Metric
    charm: Metric
    vomma: Metric
    skew: Metric
    options_volume: Metric
    open_interest: Metric
