"""Options feature engine (extension spec §31-33, Phase K): GEX regime
classification, DEX state, and GEX dynamics — derived research features
over already-normalized/synced options metrics.

No-Assumption Principle (extension §37): nothing here encodes what a
regime or state value *means* for price direction — "positive GEX =
bullish," "large DEX = reversal," and similar narratives are exactly what
§37 forbids hardcoding. These functions only ever label *state*; whether
any state correlates with anything is an empirical question for
`options.conditional_ev`, not something decided here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class GexRegime(str, Enum):
    """extension §31's example state list. Deliberately generic labels,
    not "bullish"/"bearish" — see this module's No-Assumption Principle
    note above.
    """
    STRONG_POSITIVE_GAMMA = "STRONG_POSITIVE_GAMMA"
    POSITIVE_GAMMA = "POSITIVE_GAMMA"
    NEUTRAL = "NEUTRAL"
    NEGATIVE_GAMMA = "NEGATIVE_GAMMA"
    STRONG_NEGATIVE_GAMMA = "STRONG_NEGATIVE_GAMMA"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class GexRegimeThresholds:
    """Cutoffs in *standard deviations* of the underlying's own recent GEX
    history (see `normalize_gex_series`), not raw GEX units — extension
    §67 explicitly forbids classifying on an absolute value when the
    scale is instrument/notional-dependent and drifts over time. These
    defaults are a neutral placeholder, not a claimed real-world
    calibration (extension §31: "Le classificazioni devono essere
    data-driven o configurabili").
    """
    strong_positive: float = 2.0
    positive: float = 0.5
    negative: float = -0.5
    strong_negative: float = -2.0


def normalize_gex_series(gex_values: pd.Series) -> pd.Series:
    """Z-score against the series' own history. Returns all-NaN when
    there's too little history (<2 obs) or no variance to normalize
    against, rather than dividing by zero or fabricating a scale.
    """
    valid = gex_values.dropna()
    if len(valid) < 2:
        return pd.Series(float("nan"), index=gex_values.index)
    std = gex_values.std()
    if not std or std != std:
        return pd.Series(float("nan"), index=gex_values.index)
    return (gex_values - gex_values.mean()) / std


def classify_gex_regime(normalized_gex: float | None, thresholds: GexRegimeThresholds | None = None) -> GexRegime:
    """`normalized_gex` must already be normalized (e.g. via
    `normalize_gex_series`) — this function does not normalize on its own,
    so it never silently classifies against a raw, scale-dependent value.
    """
    if normalized_gex is None or normalized_gex != normalized_gex:  # None or NaN
        return GexRegime.UNKNOWN
    thresholds = thresholds or GexRegimeThresholds()
    if normalized_gex >= thresholds.strong_positive:
        return GexRegime.STRONG_POSITIVE_GAMMA
    if normalized_gex >= thresholds.positive:
        return GexRegime.POSITIVE_GAMMA
    if normalized_gex <= thresholds.strong_negative:
        return GexRegime.STRONG_NEGATIVE_GAMMA
    if normalized_gex <= thresholds.negative:
        return GexRegime.NEGATIVE_GAMMA
    return GexRegime.NEUTRAL


def classify_gex_regime_series(gex_values: pd.Series, thresholds: GexRegimeThresholds | None = None) -> pd.Series:
    normalized = normalize_gex_series(gex_values)
    return normalized.apply(lambda v: classify_gex_regime(v, thresholds).value)


def compute_dex_state(dex_series: pd.Series) -> pd.DataFrame:
    """extension §32: magnitude/sign/change/acceleration — "quando
    sufficientemente disponibile." `dex_concentration` (also named in
    §32) has no defined derivation from a single aggregate DEX value —
    it would need a per-strike DEX breakdown GEXBOT's snapshot endpoint
    doesn't provide (see `options.gexbot.client`'s docstring); left as an
    all-`NaN` column rather than guessed at, not omitted, so callers see
    the gap rather than a silently missing feature.
    """
    magnitude = dex_series.abs()
    sign = dex_series.apply(lambda v: float((v > 0) - (v < 0)) if v == v else float("nan"))
    change = dex_series.diff()
    acceleration = change.diff()
    return pd.DataFrame({
        "dex_magnitude": magnitude,
        "dex_sign": sign,
        "dex_concentration": float("nan"),
        "dex_change": change,
        "dex_acceleration": acceleration,
    })


def compute_gex_dynamics(gex_series: pd.Series) -> pd.DataFrame:
    """ΔGEX_t and Δ²GEX_t (extension §33) — plain differences, "research
    features, not signal automatici" per §33's own words: no
    interpretation, threshold, or regime label applied here.
    """
    delta = gex_series.diff()
    delta2 = delta.diff()
    return pd.DataFrame({"gex_delta": delta, "gex_delta2": delta2})
