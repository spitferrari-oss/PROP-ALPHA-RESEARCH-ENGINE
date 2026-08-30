"""Shadow Mode engine (spec §132): "compute what would have been done
without sending real orders" — before anything is promoted toward live,
the system must be able to show what it would have decided in a paper
context and compare that against the model's own IS-fitted expectations.

This environment has no live data feed, and spec §123 forbids presenting
fabricated data as real market evidence. So shadow mode here replays the
already-computed out-of-sample holdout — the same trades Phase 4's
statistical validation used — as the shadow log's source, rather than
inventing a fake "live" stream. In a genuine deployment this module would
instead be fed newly-collected forward data gathered after promotion
(spec §131 Stage 3+); replaying OOS is an honest stand-in that lets the
monitoring mechanism below (monitor.py, decay.py, drift.py) be exercised
end-to-end without pretending it is real forward performance.

`expected_r` is intentionally a single constant per shadow log — the
alpha's own in-sample expectancy (spec's "Expected trade" of spec §100) —
compared against each trade's realized `actual_r`. An "expected vs actual
slippage" column is deliberately NOT included: the backtest/shadow cost
model is deterministic, so expected and actual slippage would always be
identical and the comparison would be theater, not a real check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SHADOW_LOG_COLUMNS = [
    "entry_time", "exit_time", "direction",
    "expected_r", "actual_r", "pnl", "model_probability", "actual_result",
]


def build_shadow_log(
    oos_trades: pd.DataFrame,
    X_oos: pd.DataFrame,
    meta_model,
    alpha_result: dict,
) -> pd.DataFrame:
    """`oos_trades` is the top-ranked alpha's out-of-sample trade frame
    (already computed for the ML Meta-Alpha layer). `X_oos` is that same
    OOS trade set's feature matrix (same row order/length), and
    `meta_model` is the fitted `MetaAlphaModel` from `evaluate_meta_alpha`
    (or None when no model was fit, e.g. insufficient data) — used only to
    attach the model's own P(win) alongside the realized outcome, for the
    Live/Paper Monitor's calibration check.
    """
    if oos_trades.empty:
        return pd.DataFrame(columns=SHADOW_LOG_COLUMNS)

    oos_trades = oos_trades.reset_index(drop=True)
    expected_r = alpha_result.get("expectancy_r", float("nan"))

    if meta_model is not None and X_oos is not None and len(X_oos) == len(oos_trades):
        model_probability = meta_model.predict_proba_rf(X_oos)
    else:
        model_probability = np.full(len(oos_trades), np.nan)

    return pd.DataFrame({
        "entry_time": oos_trades["entry_time"],
        "exit_time": oos_trades["exit_time"],
        "direction": oos_trades["direction"],
        "expected_r": expected_r,
        "actual_r": oos_trades["r_multiple"].astype(float),
        "pnl": oos_trades["pnl"].astype(float),
        "model_probability": model_probability,
        "actual_result": (oos_trades["pnl"] > 0).astype(int),
    })
