"""Baseline STRATEGY 05 — Volume Profile breakout (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class VolumeProfileBreakout(Strategy):
    def __init__(self):
        self.meta = AlphaMeta(
            alpha_id="ALPHA_05",
            alpha_name="Volume Profile Breakout",
            family="MOMENTUM",
            subcategory="volume-profile breakout",
            directionality="BOTH",
            mechanism="Price breaks and holds outside the developing value area, signaling acceptance at new levels",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        prev_vah = df["vp_vah"].shift(1)
        prev_val = df["vp_val"].shift(1)
        long_cond = (df["close"] > df["vp_vah"]) & (df["close"].shift(1) <= prev_vah)
        short_cond = (df["close"] < df["vp_val"]) & (df["close"].shift(1) >= prev_val)
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
