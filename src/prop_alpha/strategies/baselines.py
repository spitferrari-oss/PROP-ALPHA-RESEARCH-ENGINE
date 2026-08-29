"""Trivial baseline comparators (spec §90): every real alpha must demonstrate
incremental value over these before it can be taken seriously. They are
tagged family="BASELINE" so the report can compare against them separately
from the ranked alpha table rather than mixing them into it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class BuyAndHold(Strategy):
    """Long from the first bar of each session to end-of-day flatten."""

    def __init__(self):
        self.meta = AlphaMeta(
            alpha_id="BASE_01", alpha_name="Buy & Hold (session)", family="BASELINE",
            directionality="LONG", mechanism="No edge — pure long exposure for the session",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        day = df["timestamp"].dt.tz_convert("America/New_York").dt.date
        bar_of_day = df.groupby(day).cumcount()
        df["direction"] = np.where(bar_of_day == 0, 1, 0)
        return df


class RandomEntry(Strategy):
    """Long-only entries at uniformly random bars — no edge, no direction skill."""

    def __init__(self, entry_prob: float = 0.05, seed: int = 42):
        self.entry_prob = entry_prob
        self.seed = seed
        self.meta = AlphaMeta(
            alpha_id="BASE_02", alpha_name="Random Entry", family="BASELINE",
            directionality="LONG", mechanism="No edge — random entry timing, always long",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        rng = np.random.default_rng(self.seed)
        df["direction"] = np.where(rng.random(len(df)) < self.entry_prob, 1, 0)
        return df


class RandomDirection(Strategy):
    """Random entries with a random long/short direction — no edge at all."""

    def __init__(self, entry_prob: float = 0.05, seed: int = 43):
        self.entry_prob = entry_prob
        self.seed = seed
        self.meta = AlphaMeta(
            alpha_id="BASE_03", alpha_name="Random Direction", family="BASELINE",
            directionality="BOTH", mechanism="No edge — random entry timing and random direction",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        rng = np.random.default_rng(self.seed)
        enter = rng.random(len(df)) < self.entry_prob
        direction = rng.choice([-1, 1], size=len(df))
        df["direction"] = np.where(enter, direction, 0)
        return df


class SimpleMovingAverageCrossover(Strategy):
    """Fast/slow SMA crossover — the textbook trend baseline."""

    def __init__(self, fast: int = 5, slow: int = 20):
        self.fast = fast
        self.slow = slow
        self.meta = AlphaMeta(
            alpha_id="BASE_04", alpha_name="Simple MA Crossover", family="BASELINE",
            directionality="BOTH", mechanism="Naive trend-following crossover, no regime/liquidity/session filters",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        fast_ma = df["close"].rolling(self.fast).mean()
        slow_ma = df["close"].rolling(self.slow).mean()
        prev_fast, prev_slow = fast_ma.shift(1), slow_ma.shift(1)
        long_cond = (fast_ma > slow_ma) & (prev_fast <= prev_slow)
        short_cond = (fast_ma < slow_ma) & (prev_fast >= prev_slow)
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df


class SimpleBreakout(Strategy):
    """Naive N-bar high/low breakout with no volume/volatility/regime filter,
    for comparison against the filtered breakout alphas (ALPHA_02, ALPHA_05, ALPHA_07)."""

    def __init__(self):
        self.meta = AlphaMeta(
            alpha_id="BASE_05", alpha_name="Simple Breakout", family="BASELINE",
            directionality="BOTH", mechanism="Naive N-bar range breakout, no confirming filters",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        long_cond = df["close"] > df["prior_swing_high"]
        short_cond = df["close"] < df["prior_swing_low"]
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df


class SimpleMeanReversion(Strategy):
    """Naive z-score-vs-SMA reversion with no volume/session/regime filter,
    for comparison against the filtered reversion alphas (ALPHA_03, ALPHA_04)."""

    def __init__(self, window: int = 20, z_threshold: float = 2.0):
        self.window = window
        self.z_threshold = z_threshold
        self.meta = AlphaMeta(
            alpha_id="BASE_06", alpha_name="Simple Mean Reversion", family="BASELINE",
            directionality="BOTH", mechanism="Naive SMA z-score reversion, no confirming filters",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        sma = df["close"].rolling(self.window).mean()
        std = df["close"].rolling(self.window).std()
        z = (df["close"] - sma) / std
        long_cond = z < -self.z_threshold
        short_cond = z > self.z_threshold
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df


BASELINE_STRATEGIES = [
    BuyAndHold, RandomEntry, RandomDirection,
    SimpleMovingAverageCrossover, SimpleBreakout, SimpleMeanReversion,
]
