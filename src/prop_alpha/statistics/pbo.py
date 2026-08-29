"""Probability of Backtest Overfitting via Combinatorially Symmetric
Cross-Validation (spec §30; Bailey, Borwein, Lopez de Prado & Zhu 2014).

Given a pool of N candidate alphas' daily P&L over the same T trading days,
CSCV asks: if you had only picked the best-looking strategy in-sample, how
often would it have turned out to be *below the median* out-of-sample? A
high PBO means the ranking that picked a "winner" is not trustworthy — it
is evidence of selecting on noise across the trial pool, not evidence
against any single strategy.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd


def build_pnl_matrix(daily_pnl_by_strategy: dict[str, pd.Series], all_days: list) -> pd.DataFrame:
    """Align each strategy's daily P&L onto the full trading-day calendar,
    filling untraded days with 0 P&L (a strategy that stood aside earned
    nothing that day — not a missing observation).
    """
    matrix = pd.DataFrame(index=pd.Index(all_days, name="day"))
    for name, series in daily_pnl_by_strategy.items():
        matrix[name] = series.reindex(all_days, fill_value=0.0)
    return matrix


def compute_pbo(pnl_matrix: pd.DataFrame, n_splits: int = 8) -> dict:
    n_days, n_strategies = pnl_matrix.shape
    if n_strategies < 2 or n_splits < 2 or n_days < n_splits * 2:
        return {"pbo": float("nan"), "n_combinations": 0, "n_strategies": n_strategies, "n_splits": n_splits}

    block_size = n_days // n_splits
    blocks = [pnl_matrix.iloc[i * block_size:(i + 1) * block_size] for i in range(n_splits)]
    half = n_splits // 2

    logits = []
    for is_idx in combinations(range(n_splits), half):
        is_idx = set(is_idx)
        oos_idx = [i for i in range(n_splits) if i not in is_idx]
        is_data = pd.concat([blocks[i] for i in sorted(is_idx)])
        oos_data = pd.concat([blocks[i] for i in oos_idx])

        is_std = is_data.std().replace(0, np.nan)
        oos_std = oos_data.std().replace(0, np.nan)
        is_sharpe = is_data.mean() / is_std
        oos_sharpe = oos_data.mean() / oos_std

        if is_sharpe.dropna().empty or oos_sharpe.dropna().empty:
            continue
        best_in_sample = is_sharpe.idxmax()

        # Relative rank of the IS winner within the OOS Sharpe distribution,
        # in (0, 1); clipped away from the boundary so the logit is finite.
        rank = oos_sharpe.rank(pct=True).get(best_in_sample, np.nan)
        if pd.isna(rank):
            continue
        rank = min(max(rank, 1.0 / (2 * n_strategies)), 1.0 - 1.0 / (2 * n_strategies))
        logits.append(np.log(rank / (1 - rank)))

    if not logits:
        return {"pbo": float("nan"), "n_combinations": 0, "n_strategies": n_strategies, "n_splits": n_splits}

    logits = np.array(logits)
    return {
        "pbo": float((logits < 0).mean()),
        "n_combinations": len(logits),
        "n_strategies": n_strategies,
        "n_splits": n_splits,
        "mean_logit": float(logits.mean()),
    }
