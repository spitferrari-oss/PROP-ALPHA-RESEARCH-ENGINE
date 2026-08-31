"""Location Engine (extension spec §43): `MarketLocation_t` — the current
price's distance to every relevant coordinate on the market map, futures
side (VWAP, volume profile POC/VAH/VAL, prior-day POC/VAH/VAL, prior-day
high/low, opening range high/low) and options side (whatever `OptionsLevel`
objects `options.levels.extract_levels` produced for the synced snapshot).

Reuses `options.distance.compute_distance_features` for both: despite
living in the `options` package, that function only computes a
price/level-value distance and doesn't touch anything options-specific, so
it is the correct shared primitive rather than duplicating its formula
here.

A futures-side level whose column is missing (or `None`/`NaN`) from
`futures_bar` is simply absent from `MarketLocation.distances` — never a
fabricated distance to a level that wasn't actually reported.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from prop_alpha.options.distance import compute_distance_features
from prop_alpha.options.models import OptionsLevel

# (distance name, futures_bar column, category)
_FUTURES_LEVEL_COLUMNS = (
    ("vwap", "vwap", "futures"),
    ("vp_poc", "volume_profile_poc", "futures"),
    ("vp_vah", "volume_profile_vah", "futures"),
    ("vp_val", "volume_profile_val", "futures"),
    ("vp_prior_poc", "prior_day_volume_profile_poc", "futures"),
    ("vp_prior_vah", "prior_day_volume_profile_vah", "futures"),
    ("vp_prior_val", "prior_day_volume_profile_val", "futures"),
    ("prior_day_high", "prior_day_high", "futures"),
    ("prior_day_low", "prior_day_low", "futures"),
    ("opening_range_high", "opening_range_high", "futures"),
    ("opening_range_low", "opening_range_low", "futures"),
)


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(value)
    except TypeError:
        return False


@dataclass(frozen=True)
class LocationDistance:
    name: str
    category: str  # "futures" | "options"
    absolute: float
    percentage: float
    atr_normalized: float | None
    vol_normalized: float | None


@dataclass(frozen=True)
class MarketLocation:
    timestamp: dt.datetime
    price: float
    distances: list[LocationDistance] = field(default_factory=list)

    def get(self, name: str) -> LocationDistance | None:
        for distance in self.distances:
            if distance.name == name:
                return distance
        return None

    def as_dict(self) -> dict:
        """One scalar per distance, ATR-normalized when available and
        falling back to percentage distance otherwise (extension §30's
        preferred normalization, with a usable value even when no ATR was
        supplied).
        """
        return {
            distance.name: distance.atr_normalized
            if distance.atr_normalized is not None
            else distance.percentage
            for distance in self.distances
        }


def build_market_location(
    futures_bar: dict,
    price: float,
    timestamp: dt.datetime,
    atr: float | None = None,
    realized_vol: float | None = None,
    options_levels: list[OptionsLevel] | None = None,
) -> MarketLocation:
    distances: list[LocationDistance] = []

    for name, column, category in _FUTURES_LEVEL_COLUMNS:
        level_value = futures_bar.get(column)
        if _is_missing(level_value):
            continue
        features = compute_distance_features(price, level_value, atr, realized_vol)
        distances.append(LocationDistance(name=name, category=category, **vars(features)))

    for level in options_levels or ():
        if _is_missing(level.value):
            continue
        features = compute_distance_features(price, level.value, atr, realized_vol)
        distances.append(
            LocationDistance(name=f"options_{level.metric}", category="options", **vars(features))
        )

    return MarketLocation(timestamp=timestamp, price=price, distances=distances)
