"""Baseline STRATEGY 11 — Compression -> expansion (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class CompressionExpansion(Strategy):
    def __init__(self, compression_percentile: float = 0.2, expansion_atr_mult: float = 1.5):
        self.compression_percentile = compression_percentile
        self.expansion_atr_mult = expansion_atr_mult
        self.meta = AlphaMeta(
            alpha_id="ALPHA_11",
            alpha_name="Compression to Expansion",
            family="MOMENTUM",
            subcategory="volatility breakout",
            directionality="BOTH",
            mechanism="A low-volatility compression regime resolves directionally once range expansion begins",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        compression = df["volatility_percentile"].shift(1) < self.compression_percentile
        expansion = df["true_range"] > self.expansion_atr_mult * df["atr_14"].shift(1)
        long_cond = compression & expansion & (df["close"] > df["open"])
        short_cond = compression & expansion & (df["close"] < df["open"])
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
