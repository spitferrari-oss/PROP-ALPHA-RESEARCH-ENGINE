"""Baseline STRATEGY 04 — Volume Profile mean reversion (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class VolumeProfileMeanReversion(Strategy):
    def __init__(self):
        self.meta = AlphaMeta(
            alpha_id="ALPHA_04",
            alpha_name="Volume Profile Mean Reversion",
            family="MEAN_REVERSION",
            subcategory="volume-profile reversion",
            directionality="BOTH",
            mechanism="Price stretched outside the developing value area reverts toward the POC",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        reverting_up = df["close"] > df["close"].shift(1)
        reverting_down = df["close"] < df["close"].shift(1)
        long_cond = (df["close"] < df["vp_val"]) & reverting_up
        short_cond = (df["close"] > df["vp_vah"]) & reverting_down
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
