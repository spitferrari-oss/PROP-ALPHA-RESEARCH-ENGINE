"""Vendor-agnostic options data models (extension spec §26-29): every
options provider's parsed output converges onto `OptionsSnapshot`/
`OptionsLevel` — the same shape regardless of which vendor (GEXBOT today,
a future provider later) supplied the underlying metrics. Mirrors
`data.normalize`'s role on the futures side (Phase D): a provider owns its
own raw parsing (`options.gexbot.models.GexSnapshot`), this module owns
the canonical cross-provider shape (`options.normalize.normalize_gex_snapshot`
does the actual conversion).

`AvailabilityStatus`/`MetricAvailability`/`Metric` originated in Phase H's
`options.gexbot.models` (they were already provider-agnostic in spirit —
every options provider needs per-metric availability, not just GEXBOT)
and moved here in Phase I; `options.gexbot.models` re-exports them for
backward compatibility.
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
    """A single options metric value plus its own availability — extension
    §51-52: a metric no provider currently reports is `value=None` with
    `availability.status=UNAVAILABLE`, never silently defaulted to `0`.
    """
    value: float | None
    availability: MetricAvailability


class LevelType(str, Enum):
    """extension §29's level type list."""
    GAMMA_FLIP = "GAMMA_FLIP"
    POSITIVE_GAMMA = "POSITIVE_GAMMA"
    NEGATIVE_GAMMA = "NEGATIVE_GAMMA"
    MAJOR_GAMMA = "MAJOR_GAMMA"
    DEX_LEVEL = "DEX_LEVEL"
    VANNA_LEVEL = "VANNA_LEVEL"
    CHARM_LEVEL = "CHARM_LEVEL"


@dataclass(frozen=True)
class OptionsLevel:
    """extension §29's `level` object — one relevant options level.
    `distance_from_spot` and `strength` are `None` when there isn't yet
    enough information to compute them (see `options.levels`'s module
    docstring for exactly what "enough" means at this phase).
    """
    underlying: str
    timestamp: dt.datetime
    strike: float
    type: LevelType
    value: float
    distance_from_spot: float | None
    source: str
    metric: str
    strength: float | None = None


@dataclass(frozen=True)
class OptionsSnapshot:
    """extension §28's `options_state` model. `extra` is the extensibility
    hook §28 asks for ("Il modello deve essere estensibile") — a metric a
    future provider or GEXBOT plan tier reports that doesn't have a named
    field here yet is captured in `extra` rather than dropped or forcing
    an immediate schema change.
    """
    timestamp: dt.datetime
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
    orderflow_state: dict | None = None
    extra: dict[str, Metric] | None = None
