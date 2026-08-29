"""Monte Carlo engine (spec §32): resample historical daily P&L with
replacement to build many synthetic account paths, used downstream by the
prop simulator to estimate P(breach) / P(payout) empirically rather than
from a closed-form formula.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_daily_pnl_paths(
    daily_pnl: pd.Series,
    n_paths: int = 5000,
    n_days: int = 30,
    seed: int = 42,
) -> np.ndarray:
    """Return an (n_paths, n_days) array of simulated daily P&L, drawn i.i.d.
    with replacement from the empirical daily P&L distribution.
    """
    values = daily_pnl.dropna().to_numpy()
    if len(values) == 0:
        return np.zeros((n_paths, n_days))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_paths, n_days))
    return values[idx]
