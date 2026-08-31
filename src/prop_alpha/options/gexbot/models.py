"""GEXBOT-specific data models (extension spec §26-27): `GexSnapshot` is
GEXBOT's own parsed shape — `options.normalize.normalize_gex_snapshot`
(Phase I) converts it into the vendor-agnostic `options.models.OptionsSnapshot`
every downstream consumer actually depends on.

`AvailabilityStatus`/`MetricAvailability`/`Metric` moved to
`options.models` in Phase I (they were already provider-agnostic in
spirit) and are re-exported here for backward compatibility with anything
still importing them from this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from prop_alpha.options.models import AvailabilityStatus, Metric, MetricAvailability

__all__ = ["AvailabilityStatus", "MetricAvailability", "Metric", "GexSnapshot"]


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
