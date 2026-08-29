"""Baseline STRATEGY 12 — Opening drive continuation (spec §89)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.strategies.base import AlphaMeta, Strategy


class OpeningDriveContinuation(Strategy):
    def __init__(self, drive_atr_fraction: float = 0.4, continuation_bars: int = 5):
        self.drive_atr_fraction = drive_atr_fraction
        self.continuation_bars = continuation_bars
        self.meta = AlphaMeta(
            alpha_id="ALPHA_12",
            alpha_name="Opening Drive Continuation",
            family="MOMENTUM",
            subcategory="opening drive",
            directionality="BOTH",
            mechanism="A strong, high-conviction opening bar reflects an order imbalance that tends to persist"
            " through the early session",
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        day = df["timestamp"].dt.tz_convert("America/New_York").dt.date
        bar_of_day = df.groupby(day).cumcount()

        first_open = df.groupby(day)["open"].transform(lambda s: s.iloc[0])
        first_close = df.groupby(day)["close"].transform(lambda s: s.iloc[0])
        first_atr = df.groupby(day)["atr_14"].transform(lambda s: s.iloc[0])

        drive_direction = np.sign(first_close - first_open)
        strong_drive = (first_close - first_open).abs() > self.drive_atr_fraction * first_atr

        in_window = (bar_of_day >= 1) & (bar_of_day <= self.continuation_bars)
        long_cond = in_window & strong_drive & (drive_direction == 1) & (df["close"] > first_close)
        short_cond = in_window & strong_drive & (drive_direction == -1) & (df["close"] < first_close)
        df["direction"] = np.select([long_cond, short_cond], [1, -1], default=0)
        return df
