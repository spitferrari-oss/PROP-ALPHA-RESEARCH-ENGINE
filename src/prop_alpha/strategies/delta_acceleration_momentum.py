"""Baseline STRATEGY 08 — Delta acceleration momentum (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class DeltaAccelerationMomentum(Strategy):
    def __init__(self, z_threshold: float = 1.5):
        self.z_threshold = z_threshold
        self.meta = AlphaMeta(
            alpha_id="ALPHA_08",
            alpha_name="Delta Acceleration Momentum",
            family="MICROSTRUCTURE",
            subcategory="order-flow acceleration",
            directionality="BOTH",
            mechanism="A sharp increase in the rate of order-flow imbalance precedes continued price movement",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "delta_acceleration_z" not in df.columns:
            df["direction"] = 0
            return df
        long_cond = (df["delta_acceleration_z"] > self.z_threshold) & (df["close"] > df["close"].shift(1))
        short_cond = (df["delta_acceleration_z"] < -self.z_threshold) & (df["close"] < df["close"].shift(1))
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
