"""Baseline STRATEGY 03 — VWAP mean reversion (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class VwapMeanReversion(Strategy):
    def __init__(self, z_threshold: float = 2.0):
        self.z_threshold = z_threshold
        self.meta = AlphaMeta(
            alpha_id="ALPHA_03",
            alpha_name="VWAP Mean Reversion",
            family="MEAN_REVERSION",
            subcategory="VWAP reversion",
            directionality="BOTH",
            mechanism="Overextension from session value followed by reversion to fair value",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        reverting_up = df["close"] > df["close"].shift(1)
        reverting_down = df["close"] < df["close"].shift(1)
        long_cond = (df["vwap_z"] < -self.z_threshold) & reverting_up
        short_cond = (df["vwap_z"] > self.z_threshold) & reverting_down
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
