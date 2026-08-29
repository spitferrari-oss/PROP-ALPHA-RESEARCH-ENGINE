"""Baseline STRATEGY 02 — Opening range breakout (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class OpeningRangeBreakout(Strategy):
    def __init__(self, or_bars: int = 2):
        self.or_bars = or_bars
        self.meta = AlphaMeta(
            alpha_id="ALPHA_02",
            alpha_name="Opening Range Breakout",
            family="MOMENTUM",
            subcategory="breakout",
            directionality="BOTH",
            mechanism="Opening imbalance resolution / initial balance breakout",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        day = df["timestamp"].dt.tz_convert("America/New_York").dt.date
        df["_bar_of_day"] = df.groupby(day).cumcount()

        or_high = df.groupby(day)["high"].transform(
            lambda s: s.iloc[: self.or_bars].max()
        )
        or_low = df.groupby(day)["low"].transform(
            lambda s: s.iloc[: self.or_bars].min()
        )

        after_or = df["_bar_of_day"] >= self.or_bars
        long_cond = after_or & (df["close"] > or_high)
        short_cond = after_or & (df["close"] < or_low)
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        df.drop(columns=["_bar_of_day"], inplace=True)
        return df
