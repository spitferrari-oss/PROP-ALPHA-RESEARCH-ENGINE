"""Symbolic Regression (spec §48): search for simple, interpretable
expressions over existing features that correlate with a forward-return
target, preferring fewer terms at equal information coefficient (spec §49
Strategy Complexity Score — "a parità di performance, preferire la
strategia più semplice").

`compute_forward_return` deliberately uses *future* bars (`shift(-horizon)`)
— that is correct and required here, since the forward return is the
regression *target/label* being searched for a predictor of, never an input
feature fed into a strategy signal. It must never be used anywhere else.
"""
from __future__ import annotations

import itertools
from typing import Callable

import pandas as pd


def compute_forward_return(df: pd.DataFrame, horizon_bars: int = 4) -> pd.Series:
    """Forward return `horizon_bars` bars ahead — a label for symbolic
    regression, not a feature. Never use this column as a strategy input.
    """
    return df["close"].shift(-horizon_bars) / df["close"] - 1.0


def _build_expression_pool(feature_names: list[str]) -> list[tuple[str, Callable[[pd.DataFrame], pd.Series], int]]:
    pool: list[tuple[str, Callable[[pd.DataFrame], pd.Series], int]] = []
    for f in feature_names:
        pool.append((f, (lambda df, f=f: df[f]), 1))
    for f1, f2 in itertools.combinations(feature_names, 2):
        pool.append((f"{f1} - {f2}", (lambda df, f1=f1, f2=f2: df[f1] - df[f2]), 2))
        pool.append((f"{f1} + {f2}", (lambda df, f1=f1, f2=f2: df[f1] + df[f2]), 2))
    return pool


def symbolic_search(
    df: pd.DataFrame,
    feature_names: list[str],
    target: pd.Series,
    top_k: int = 10,
    min_obs: int = 100,
) -> list[dict]:
    """Rank expressions by |Spearman IC| with `target`, breaking ties toward
    lower complexity (fewer terms). Returns at most `top_k` results.
    """
    pool = _build_expression_pool(feature_names)
    results = []

    for expression, fn, complexity in pool:
        series = fn(df)
        valid = series.notna() & target.notna()
        n_obs = int(valid.sum())
        if n_obs < min_obs:
            continue
        ic = series[valid].corr(target[valid], method="spearman")
        if ic != ic:  # NaN (e.g. zero variance)
            continue
        results.append({
            "expression": expression,
            "ic": float(ic),
            "complexity": complexity,
            "n_obs": n_obs,
        })

    results.sort(key=lambda r: (-abs(r["ic"]), r["complexity"]))
    return results[:top_k]
