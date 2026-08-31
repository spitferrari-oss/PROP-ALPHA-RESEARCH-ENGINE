"""Distance-to-level features (extension spec §30): for each options
level, the absolute/percentage/ATR-normalized/volatility-normalized
distance from the current futures price.

This completes what `options.levels.extract_levels` (Phase I)
deliberately left as a placeholder — that module can only compute
distance against the options snapshot's *own* reported spot price (no
other data needed); this one uses the synced futures price and ATR
(extension §35's synchronization, Phase J) to produce the properly
normalized distance §30 actually specifies:

    Distance_ATR = |Price - Level| / ATR
"""
from __future__ import annotations

from dataclasses import dataclass

from prop_alpha.options.models import OptionsLevel


@dataclass(frozen=True)
class DistanceFeatures:
    absolute: float
    percentage: float
    atr_normalized: float | None
    vol_normalized: float | None


def compute_distance_features(
    price: float,
    level_value: float,
    atr: float | None = None,
    realized_vol: float | None = None,
) -> DistanceFeatures:
    """`realized_vol` is expected as a fraction (e.g. 0.01 for 1%), so
    `vol_normalized` distance is comparable in scale to `atr_normalized`
    distance rather than needing its own separate interpretation.
    """
    absolute = price - level_value
    percentage = (absolute / price) if price else float("nan")
    atr_normalized = (absolute / atr) if atr not in (None, 0) else None
    vol_normalized = (absolute / (price * realized_vol)) if realized_vol not in (None, 0) and price else None
    return DistanceFeatures(
        absolute=absolute, percentage=percentage, atr_normalized=atr_normalized, vol_normalized=vol_normalized,
    )


def compute_level_distances(
    levels: list[OptionsLevel],
    price: float,
    atr: float | None = None,
    realized_vol: float | None = None,
) -> list[dict]:
    return [
        {
            "level": level,
            "distance": compute_distance_features(price, level.value, atr, realized_vol),
        }
        for level in levels
    ]
