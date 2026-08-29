"""Baseline STRATEGY 07 — Previous Day High/Low breakout (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class PriorDayHighLowBreakout(Strategy):
    def __init__(self):
        self.meta = AlphaMeta(
            alpha_id="ALPHA_07",
            alpha_name="Previous Day High/Low Breakout",
            family="MOMENTUM",
            subcategory="prior-level breakout",
            directionality="BOTH",
            mechanism="A clean break of yesterday's range signals continuation into fresh price discovery",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        long_cond = df["close"] > df["prior_day_high"]
        short_cond = df["close"] < df["prior_day_low"]
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
