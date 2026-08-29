"""Baseline STRATEGY 06 — Previous Day High/Low reversal (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class PriorDayHighLowReversal(Strategy):
    def __init__(self):
        self.meta = AlphaMeta(
            alpha_id="ALPHA_06",
            alpha_name="Previous Day High/Low Reversal",
            family="MEAN_REVERSION",
            subcategory="overnight/prior-level reversal",
            directionality="BOTH",
            mechanism="A sweep of yesterday's high/low that fails to hold triggers a liquidity-grab reversal",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        swept_low_rejected = (df["low"] <= df["prior_day_low"]) & (df["close"] > df["prior_day_low"])
        swept_high_rejected = (df["high"] >= df["prior_day_high"]) & (df["close"] < df["prior_day_high"])
        df["direction"] = np.select([swept_low_rejected, swept_high_rejected], [1, -1], default=0)
        return df
