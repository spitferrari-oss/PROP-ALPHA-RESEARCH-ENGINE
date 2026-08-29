"""Baseline STRATEGY 09 — Absorption reversal (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class AbsorptionReversal(Strategy):
    def __init__(self, volume_threshold: float = 1.5, body_atr_fraction: float = 0.3):
        self.volume_threshold = volume_threshold
        self.body_atr_fraction = body_atr_fraction
        self.meta = AlphaMeta(
            alpha_id="ALPHA_09",
            alpha_name="Absorption Reversal",
            family="MICROSTRUCTURE",
            subcategory="absorption",
            directionality="BOTH",
            mechanism="Heavy one-sided volume that fails to move price (absorption) signals the aggressor is being"
            " absorbed by resting liquidity, favoring a reversal",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "delta" not in df.columns:
            df["direction"] = 0
            return df
        absorption = (df["relative_volume"] > self.volume_threshold) & (
            df["body"] < self.body_atr_fraction * df["atr_14"]
        )
        long_cond = absorption & (df["delta"] < 0) & (df["close"] >= df["open"])
        short_cond = absorption & (df["delta"] > 0) & (df["close"] <= df["open"])
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
