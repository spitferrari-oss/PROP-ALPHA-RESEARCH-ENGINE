"""Alpha object (spec §9): standard representation for every strategy."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

RESEARCH_STATES = [
    "HYPOTHESIS", "PROTOTYPE", "BACKTESTED", "IN_SAMPLE_VALIDATED",
    "OUT_OF_SAMPLE", "WALK_FORWARD", "ROBUST", "PAPER",
    "LIVE_CANDIDATE", "LIVE", "DEGRADED", "RETIRED",
]


@dataclass
class AlphaMeta:
    alpha_id: str
    alpha_name: str
    family: str
    subcategory: str = ""
    market: str = "NQ"
    session: str = "US_OPEN"
    timeframe: str = "15m"
    directionality: str = "BOTH"
    stop_atr_mult: float = 1.5
    target_r_multiple: float = 2.0
    research_status: str = "PROTOTYPE"
    mechanism: str = ""


class Strategy(ABC):
    """Base class for every alpha. `generate_signals` must only use
    information available up to and including bar t when producing a
    signal for bar t (no look-ahead) — the backtest engine enters at the
    *next* bar's open.
    """

    meta: AlphaMeta

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return df with an added integer column 'direction' in {-1, 0, 1}."""
        raise NotImplementedError

    def with_risk_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach stop/target distances (in price) derived from ATR, using
        only the ATR value known as of the signal bar.
        """
        df = self.generate_signals(df)
        atr = df["atr_14"]
        df["stop_distance"] = atr * self.meta.stop_atr_mult
        df["target_distance"] = df["stop_distance"] * self.meta.target_r_multiple
        return df
