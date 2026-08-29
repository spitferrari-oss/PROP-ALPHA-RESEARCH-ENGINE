"""Rule-based Market Regime Engine (spec §12).

A priority-ordered cascade over already-computed, already-normalized
features (volatility percentile, true-range/ATR ratio, relative volume,
VWAP slope) — every threshold is on a ratio or percentile, never a raw
price level (spec §116 "No Magic Numbers" / §117 Normalization Engine).
Every input is available as of the bar's own close, so this classifier has
no look-ahead by construction.

Regimes are mutually exclusive per bar (first matching rule wins), except
liquidity, which is reported as separate boolean columns since a bar can be
e.g. both TREND_UP and LOW_LIQUIDITY at once — collapsing that into one
label would throw information away.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.config import RegimeConfig

REGIME_LABELS = [
    "PANIC", "BREAKOUT", "COMPRESSION", "EXPANSION",
    "TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY",
    "RANGE", "UNKNOWN",
]

REQUIRED_COLUMNS = [
    "volatility_percentile", "atr_14", "true_range", "relative_volume",
    "close", "vwap", "vwap_slope", "prior_swing_high", "prior_swing_low",
    "rolling_high_20", "rolling_low_20",
]


def classify_regime_rule_based(df: pd.DataFrame, config: RegimeConfig | None = None) -> pd.DataFrame:
    config = config or RegimeConfig()
    df = df.copy()

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"classify_regime_rule_based requires columns {missing} — run build_feature_set first")

    core = df[REQUIRED_COLUMNS]
    valid = core.notna().all(axis=1)

    vol_pct = df["volatility_percentile"]
    atr = df["atr_14"]
    tr = df["true_range"]
    rel_vol = df["relative_volume"]
    close = df["close"]
    vwap = df["vwap"]
    vwap_slope = df["vwap_slope"]
    prior_high = df["prior_swing_high"]
    prior_low = df["prior_swing_low"]
    rolling_high_prior = df["rolling_high_20"].shift(config.trend_lookback_bars)
    rolling_low_prior = df["rolling_low_20"].shift(config.trend_lookback_bars)

    panic = (tr > config.panic_tr_atr_mult * atr) & (rel_vol > config.panic_relative_volume)
    breakout = ((close > prior_high) | (close < prior_low)) & (vol_pct > config.breakout_volatility_percentile)
    compression = (vol_pct < config.compression_volatility_percentile) & (tr < config.compression_tr_atr_mult * atr)
    expansion = tr > config.expansion_tr_atr_mult * atr
    trend_up = (close > vwap) & (vwap_slope > 0) & (close > rolling_high_prior)
    trend_down = (close < vwap) & (vwap_slope < 0) & (close < rolling_low_prior)
    high_volatility = vol_pct > config.high_volatility_percentile
    low_volatility = vol_pct < config.low_volatility_percentile

    conditions = [panic, breakout, compression, expansion, trend_up, trend_down, high_volatility, low_volatility]
    choices = ["PANIC", "BREAKOUT", "COMPRESSION", "EXPANSION", "TREND_UP", "TREND_DOWN",
               "HIGH_VOLATILITY", "LOW_VOLATILITY"]

    regime = np.select(conditions, choices, default="RANGE")
    regime = np.where(valid, regime, "UNKNOWN")

    df["regime_rule"] = regime
    df["high_liquidity"] = valid & (rel_vol > 1.5)
    df["low_liquidity"] = valid & (rel_vol < 0.5)
    return df
