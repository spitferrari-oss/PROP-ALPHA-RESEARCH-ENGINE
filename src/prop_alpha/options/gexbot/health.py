"""GEXBOT provider health (extension spec §90): connected/authenticated/
last_update/latency/error_rate/data_age/available_metrics — what the
eventual Data Center dashboard (Phase M) renders for the options feed,
mirroring `data.live.health.FeedHealth`'s role on the futures side.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from prop_alpha.options.gexbot.models import AvailabilityStatus, GexSnapshot

_SNAPSHOT_METRIC_NAMES = (
    "spot", "gex", "dex", "gamma_flip", "major_positive_gamma", "major_negative_gamma",
    "vanna", "charm", "vomma", "skew", "options_volume", "open_interest",
)


@dataclass(frozen=True)
class GexbotHealth:
    connected: bool
    authenticated: bool
    last_update: dt.datetime | None
    latency_ms: float | None
    error_rate: float
    data_age_seconds: float | None
    available_metrics: tuple[str, ...]


def compute_health(
    snapshot: GexSnapshot | None,
    connected: bool,
    authenticated: bool,
    n_polls: int,
    n_errors: int,
    latency_ms: float | None = None,
    now: dt.datetime | None = None,
) -> GexbotHealth:
    now = now or dt.datetime.now(dt.timezone.utc)
    error_rate = (n_errors / n_polls) if n_polls else 0.0

    if snapshot is None:
        return GexbotHealth(
            connected=connected, authenticated=authenticated, last_update=None,
            latency_ms=latency_ms, error_rate=error_rate, data_age_seconds=None, available_metrics=(),
        )

    available_metrics = tuple(
        name for name in _SNAPSHOT_METRIC_NAMES
        if getattr(snapshot, name).availability.status in (AvailabilityStatus.AVAILABLE, AvailabilityStatus.STALE)
    )
    timestamps = [
        getattr(snapshot, name).availability.timestamp for name in _SNAPSHOT_METRIC_NAMES
        if getattr(snapshot, name).availability.timestamp is not None
    ]
    last_update = max(timestamps) if timestamps else None
    data_age = (now - last_update).total_seconds() if last_update is not None else None

    return GexbotHealth(
        connected=connected, authenticated=authenticated, last_update=last_update,
        latency_ms=latency_ms, error_rate=error_rate, data_age_seconds=data_age,
        available_metrics=available_metrics,
    )
