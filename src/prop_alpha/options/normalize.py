"""Cross-provider options snapshot normalization (extension spec §28,
Phase I): converts a provider-specific parsed snapshot — today, only
`options.gexbot.models.GexSnapshot` — into the vendor-agnostic
`options.models.OptionsSnapshot` every downstream consumer (Phase J
synchronization, Phase K features, Phase L market state) depends on
instead of a specific vendor's shape.
"""
from __future__ import annotations

import datetime as dt

from prop_alpha.options.gexbot.models import GexSnapshot
from prop_alpha.options.models import OptionsSnapshot

_GEX_SNAPSHOT_FIELDS = (
    "spot", "gex", "dex", "gamma_flip", "major_positive_gamma", "major_negative_gamma",
    "vanna", "charm", "vomma", "skew", "options_volume", "open_interest",
)


def normalize_gex_snapshot(
    snapshot: GexSnapshot,
    timestamp: dt.datetime | None = None,
    orderflow_state: dict | None = None,
) -> OptionsSnapshot:
    """`timestamp` is the snapshot-level timestamp extension §28 wants —
    distinct from each metric's own `MetricAvailability.timestamp`. When
    omitted, it defaults to the freshest available per-metric timestamp,
    or `now()` if every metric is unavailable (never left unset — §16/§17
    require a canonical, always-present timestamp).
    """
    metrics = {name: getattr(snapshot, name) for name in _GEX_SNAPSHOT_FIELDS}
    if timestamp is None:
        candidate_timestamps = [
            m.availability.timestamp for m in metrics.values() if m.availability.timestamp is not None
        ]
        timestamp = max(candidate_timestamps) if candidate_timestamps else dt.datetime.now(dt.timezone.utc)

    return OptionsSnapshot(
        timestamp=timestamp,
        underlying=snapshot.underlying,
        orderflow_state=orderflow_state,
        **metrics,
    )
