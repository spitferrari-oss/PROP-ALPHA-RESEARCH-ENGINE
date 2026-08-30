"""Live/Paper Monitor (spec §100/§101): Expected trade vs Actual trade,
Expected R vs Actual R, Model probability vs Actual result — over the
shadow log built by `shadow.build_shadow_log`. Reuses the same calibration
diagnostics (Brier score, log loss, ECE) already built for the ML
Meta-Alpha layer in Phase 8, applied here to the shadow period instead of
the OOS split it was originally evaluated against.

Expected vs actual *slippage* (also named in spec §100) is not compared
here — the deterministic backtest cost model always makes them identical,
so the comparison would be vacuous; see `shadow.py`'s module docstring.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.ml.calibration import compute_calibration_metrics


def evaluate_paper_monitor(shadow_log: pd.DataFrame, min_trades_for_calibration: int = 10) -> dict:
    n = len(shadow_log)
    if n == 0:
        return {
            "status": "NO_SHADOW_TRADES",
            "n_shadow_trades": 0,
            "expected_r": float("nan"),
            "actual_mean_r": float("nan"),
            "r_prediction_error": float("nan"),
            "win_rate": float("nan"),
            "calibration": None,
        }

    actual_r = shadow_log["actual_r"].astype(float)
    expected_r_val = shadow_log["expected_r"].iloc[0]
    expected_r_val = float(expected_r_val) if expected_r_val == expected_r_val else float("nan")

    calibration = None
    probs = shadow_log["model_probability"]
    valid = probs.notna()
    if int(valid.sum()) >= min_trades_for_calibration:
        calibration = compute_calibration_metrics(
            shadow_log.loc[valid, "actual_result"], probs[valid], n_bins=10,
        )

    return {
        "status": "OK",
        "n_shadow_trades": n,
        "expected_r": expected_r_val,
        "actual_mean_r": float(actual_r.mean()),
        "r_prediction_error": (float(actual_r.mean()) - expected_r_val) if expected_r_val == expected_r_val else float("nan"),
        "win_rate": float(shadow_log["actual_result"].mean()),
        "calibration": calibration,
    }
