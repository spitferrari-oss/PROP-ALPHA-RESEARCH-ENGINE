"""Atomic condition library for combinatorial setup generation (spec §18).
Each condition is a named boolean predicate over already-computed feature
columns (spec §10/§12), so composing conditions never introduces new
look-ahead beyond what the feature engine already guarantees.

`mechanism_hint` and `regime_hint` feed the auto-generated hypothesis text
(spec §20) so every discovered candidate carries a plausible economic
rationale, not just a bare boolean expression.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class Condition:
    name: str
    fn: Callable[[pd.DataFrame], pd.Series]
    mechanism_hint: str
    regime_hint: str | None = None


def _regime_is(name: str) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda df, name=name: df["regime_rule"] == name


CONDITION_LIBRARY: list[Condition] = [
    Condition("price_above_vwap", lambda df: df["close"] > df["vwap"],
              "price trading above session fair value, a mild persistence signal"),
    Condition("price_below_vwap", lambda df: df["close"] < df["vwap"],
              "price trading below session fair value, a mild persistence signal"),
    Condition("vwap_z_extreme_low", lambda df: df["vwap_z"] < -2.0,
              "price stretched far below VWAP, a mean-reversion setup"),
    Condition("vwap_z_extreme_high", lambda df: df["vwap_z"] > 2.0,
              "price stretched far above VWAP, a mean-reversion setup"),
    Condition("delta_accel_positive", lambda df: df.get("delta_acceleration_z", pd.Series(dtype=float)) > 1.0,
              "accelerating buy-side order flow, a momentum/persistence signal"),
    Condition("delta_accel_negative", lambda df: df.get("delta_acceleration_z", pd.Series(dtype=float)) < -1.0,
              "accelerating sell-side order flow, a momentum/persistence signal"),
    Condition("high_relative_volume", lambda df: df["relative_volume"] > 1.5,
              "elevated participation, more informative order flow"),
    Condition("low_relative_volume", lambda df: df["relative_volume"] < 0.7,
              "thin participation, liquidity-driven rather than information-driven moves"),
    Condition("high_volatility", lambda df: df["volatility_percentile"] > 0.7,
              "expanded realized volatility regime"),
    Condition("low_volatility", lambda df: df["volatility_percentile"] < 0.3,
              "compressed realized volatility regime, often precedes expansion"),
    Condition("regime_trend_up", _regime_is("TREND_UP"),
              "classified uptrend regime (spec §12)", regime_hint="TREND_UP"),
    Condition("regime_trend_down", _regime_is("TREND_DOWN"),
              "classified downtrend regime (spec §12)", regime_hint="TREND_DOWN"),
    Condition("regime_range", _regime_is("RANGE"),
              "classified range regime, favors mean reversion (spec §12)", regime_hint="RANGE"),
    Condition("regime_breakout", _regime_is("BREAKOUT"),
              "classified breakout regime (spec §12)", regime_hint="BREAKOUT"),
    Condition("regime_expansion", _regime_is("EXPANSION"),
              "classified volatility-expansion regime (spec §12)", regime_hint="EXPANSION"),
    Condition("regime_compression", _regime_is("COMPRESSION"),
              "classified compression regime, often precedes a breakout (spec §12)", regime_hint="COMPRESSION"),
    Condition("not_transitioning", lambda df: ~df.get("regime_transitioning", pd.Series(False, index=df.index)),
              "regime classification is currently stable, not whipsawing (spec §13)"),
    Condition("above_prior_day_high", lambda df: df["close"] > df["prior_day_high"],
              "price breaking yesterday's range, fresh price discovery"),
    Condition("below_prior_day_low", lambda df: df["close"] < df["prior_day_low"],
              "price breaking yesterday's range, fresh price discovery"),
    Condition("near_developing_poc", lambda df: (df["close"] - df["vp_poc"]).abs() < df["atr_14"],
              "price near the developing point of control, a magnet/fair-value level"),
]
