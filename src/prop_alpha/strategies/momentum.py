"""Baseline STRATEGY 01 — Intraday momentum (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class IntradayMomentum(Strategy):
    def __init__(self, lookback: int = 4, z_threshold: float = 1.0):
        self.lookback = lookback
        self.z_threshold = z_threshold
        self.meta = AlphaMeta(
            alpha_id="ALPHA_01",
            alpha_name="Intraday Momentum",
            family="MOMENTUM",
            subcategory="time-series momentum",
            directionality="BOTH",
            mechanism="Trend persistence following directional order flow",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        mom = df["close"].pct_change(self.lookback)
        mom_z = (mom - mom.rolling(50).mean()) / mom.rolling(50).std()
        long_cond = (mom_z > self.z_threshold) & (df["relative_volume"] > 1.0)
        short_cond = (mom_z < -self.z_threshold) & (df["relative_volume"] > 1.0)
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
