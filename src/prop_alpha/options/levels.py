"""Options Level Engine (extension spec §29, Phase I): turns the
level-shaped metrics already present in an `OptionsSnapshot` (gamma flip,
major positive/negative gamma) into `OptionsLevel` objects.

`distance_from_spot` here is computed against the options snapshot's own
reported spot price — a convenience distance available with no other
data — not the ATR/volatility-normalized, futures-price-synced distance
extension §30 wants; that refinement is Phase K's job, once Phase J's
futures/options synchronization exists to align the two price series.
`strength` (also named in §29's `level` object) has no defined derivation
yet either — left `None` rather than guessed at, also Phase K's job.
"""
from __future__ import annotations

from prop_alpha.options.models import AvailabilityStatus, LevelType, OptionsLevel, OptionsSnapshot

_AVAILABLE_STATUSES = (AvailabilityStatus.AVAILABLE, AvailabilityStatus.STALE)

_LEVEL_METRIC_MAP: dict[str, LevelType] = {
    "gamma_flip": LevelType.GAMMA_FLIP,
    "major_positive_gamma": LevelType.MAJOR_GAMMA,
    "major_negative_gamma": LevelType.MAJOR_GAMMA,
}


def extract_levels(snapshot: OptionsSnapshot, source: str = "gexbot") -> list[OptionsLevel]:
    spot_value = snapshot.spot.value if snapshot.spot.availability.status in _AVAILABLE_STATUSES else None

    levels: list[OptionsLevel] = []
    for metric_name, level_type in _LEVEL_METRIC_MAP.items():
        metric = getattr(snapshot, metric_name)
        if metric.availability.status not in _AVAILABLE_STATUSES:
            continue
        distance = (metric.value - spot_value) if spot_value is not None else None
        levels.append(OptionsLevel(
            underlying=snapshot.underlying,
            timestamp=metric.availability.timestamp or snapshot.timestamp,
            strike=metric.value,
            type=level_type,
            value=metric.value,
            distance_from_spot=distance,
            source=source,
            metric=metric_name,
            strength=None,
        ))
    return levels
