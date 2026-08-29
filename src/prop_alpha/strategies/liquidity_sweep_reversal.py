"""Baseline STRATEGY 10 — Liquidity sweep reversal (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class LiquiditySweepReversal(Strategy):
    def __init__(self):
        self.meta = AlphaMeta(
            alpha_id="ALPHA_10",
            alpha_name="Liquidity Sweep Reversal",
            family="MICROSTRUCTURE",
            subcategory="liquidity sweep",
            directionality="BOTH",
            mechanism="A stop-run through a recent swing level that reverses with confirming order flow signals"
            " a liquidity grab rather than genuine continuation",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "delta" not in df.columns:
            df["direction"] = 0
            return df
        swept_low = (df["low"] <= df["prior_swing_low"]) & (df["close"] > df["prior_swing_low"])
        swept_high = (df["high"] >= df["prior_swing_high"]) & (df["close"] < df["prior_swing_high"])
        long_cond = swept_low & (df["delta"] > 0)
        short_cond = swept_high & (df["delta"] < 0)
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
