"""GEXBOT response parsing (extension spec §26-27, §51-52): translates
GEXBOT's raw JSON into `models.GexSnapshot`. GEXBOT's exact field names
are not independently verified in this environment (see `client.py`'s
module docstring) — each metric is looked up under several plausible
aliases, and marked `UNAVAILABLE` rather than guessed at when nothing
matches, per §26's explicit warning against assuming a metric's
availability or shape. Adjust `_FIELD_ALIASES` once verified against a
real GEXBOT account/plan.
"""
from __future__ import annotations

import datetime as dt

from prop_alpha.options.gexbot.models import AvailabilityStatus, GexSnapshot, Metric, MetricAvailability

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "spot": ("spot", "spot_price", "underlying_price"),
    "gex": ("gex", "total_gex", "gamma_exposure"),
    "dex": ("dex", "total_dex", "delta_exposure"),
    "gamma_flip": ("gamma_flip", "flip_point", "zero_gamma"),
    "major_positive_gamma": ("major_positive_gamma", "major_pos_gamma", "call_wall"),
    "major_negative_gamma": ("major_negative_gamma", "major_neg_gamma", "put_wall"),
    "vanna": ("vanna", "total_vanna"),
    "charm": ("charm", "total_charm"),
    "vomma": ("vomma", "total_vomma"),
    "skew": ("skew",),
    "options_volume": ("options_volume", "volume", "total_volume"),
    "open_interest": ("open_interest", "oi", "total_oi"),
}


def _parse_timestamp(value) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)
    if isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    return None


def _extract_metric(
    raw: dict, field: str, received_at: dt.datetime, source: str, stale_after_seconds: float,
) -> Metric:
    for alias in _FIELD_ALIASES[field]:
        if alias in raw and raw[alias] is not None:
            raw_ts = raw.get("timestamp", raw.get(f"{alias}_timestamp"))
            metric_ts = _parse_timestamp(raw_ts) if raw_ts is not None else received_at
            freshness = (received_at - metric_ts).total_seconds() if metric_ts is not None else None
            status = (
                AvailabilityStatus.STALE
                if freshness is not None and freshness > stale_after_seconds
                else AvailabilityStatus.AVAILABLE
            )
            return Metric(
                value=float(raw[alias]),
                availability=MetricAvailability(
                    status=status, timestamp=metric_ts, source=source, freshness_seconds=freshness,
                ),
            )
    return Metric(
        value=None,
        availability=MetricAvailability(
            status=AvailabilityStatus.UNAVAILABLE, timestamp=None, source=source, freshness_seconds=None,
        ),
    )


def parse_snapshot(
    raw: dict,
    underlying: str,
    received_at: dt.datetime | None = None,
    source: str = "gexbot",
    stale_after_seconds: float = 60.0,
) -> GexSnapshot:
    received_at = received_at or dt.datetime.now(dt.timezone.utc)
    fields = {
        name: _extract_metric(raw, name, received_at, source, stale_after_seconds)
        for name in _FIELD_ALIASES
    }
    return GexSnapshot(underlying=underlying, **fields)
