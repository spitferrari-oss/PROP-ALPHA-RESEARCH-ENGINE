"""Turns a vendor-agnostic `OptionsSnapshot` (Phase I) into the immutable,
per-metric raw records the options recorder writes (hardening pass Step
27). One record per metric, not one per snapshot — extension §26's own
principle is that different metrics can have different availability/
freshness even within the same snapshot; a single per-snapshot record
would flatten that distinction away.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from prop_alpha.options.models import OptionsSnapshot

_SNAPSHOT_METRIC_NAMES = (
    "spot", "gex", "dex", "gamma_flip", "major_positive_gamma", "major_negative_gamma",
    "vanna", "charm", "vomma", "skew", "options_volume", "open_interest",
)


@dataclass(frozen=True)
class OptionsSnapshotRecord:
    provider: str
    underlying: str
    timestamp_native: dt.datetime | None
    timestamp_received: dt.datetime
    timestamp_normalized: dt.datetime
    metric: str
    value: float | None
    availability: str
    freshness_seconds: float | None
    raw_reference: str | None = None


def collect_snapshot_records(
    snapshot: OptionsSnapshot,
    provider: str,
    received_at: dt.datetime | None = None,
    raw_reference: str | None = None,
) -> list[OptionsSnapshotRecord]:
    if received_at is None:
        received_at = dt.datetime.now(dt.timezone.utc)
    elif received_at.tzinfo is None:
        raise ValueError(
            "received_at must be timezone-aware — extension §16/§17 require UTC-aware timestamps throughout."
        )

    records = []
    for name in _SNAPSHOT_METRIC_NAMES:
        metric = getattr(snapshot, name)
        availability = metric.availability
        records.append(OptionsSnapshotRecord(
            provider=provider,
            underlying=snapshot.underlying,
            timestamp_native=availability.timestamp,
            timestamp_received=received_at,
            timestamp_normalized=availability.timestamp or snapshot.timestamp,
            metric=name,
            value=metric.value,
            availability=availability.status.value,
            freshness_seconds=availability.freshness_seconds,
            raw_reference=raw_reference,
        ))
    return records
