"""Bootstrap engine (spec §31): stationary block bootstrap over daily P&L to
produce confidence intervals for EV, drawdown, and Sharpe rather than relying
on a single point estimate from one historical path.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _stationary_block_bootstrap_sample(values: np.ndarray, block_size: int, rng: np.random.Generator) -> np.ndarray:
    n = len(values)
    if n == 0:
        return values
    out = []
    while len(out) < n:
        start = rng.integers(0, n)
        block = values[start:start + block_size]
        if len(block) == 0:
            continue
        out.extend(block.tolist())
    return np.array(out[:n])


def bootstrap_daily_pnl(
    daily_pnl: pd.Series,
    n_boot: int = 2000,
    block_size: int = 5,
    seed: int = 42,
) -> dict:
    values = daily_pnl.dropna().to_numpy()
    rng = np.random.default_rng(seed)

    means, stds, sharpes, max_dds = [], [], [], []
    for _ in range(n_boot):
        sample = _stationary_block_bootstrap_sample(values, block_size, rng)
        if len(sample) == 0:
            continue
        m, s = sample.mean(), sample.std()
        means.append(m)
        stds.append(s)
        sharpes.append((m / s * np.sqrt(252)) if s > 0 else 0.0)
        cum = np.cumsum(sample)
        max_dds.append(np.min(cum - np.maximum.accumulate(cum)))

    def ci(arr):
        arr = np.array(arr)
        return {
            "mean": float(np.mean(arr)),
            "p5": float(np.percentile(arr, 5)),
            "p95": float(np.percentile(arr, 95)),
        }

    return {
        "ev_per_day": ci(means),
        "std_per_day": ci(stds),
        "sharpe": ci(sharpes),
        "max_drawdown": ci(max_dds),
        "n_boot": n_boot,
        "block_size": block_size,
    }
