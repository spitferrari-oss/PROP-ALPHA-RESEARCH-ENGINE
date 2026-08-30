import numpy as np
import pandas as pd

from prop_alpha.paper.monitor import evaluate_paper_monitor


def _shadow_log(n=20, seed=0):
    rng = np.random.default_rng(seed)
    actual_r = rng.normal(0.3, 1.0, n)
    probs = rng.uniform(0.3, 0.9, n)
    actual_result = (rng.uniform(0, 1, n) < probs).astype(int)
    return pd.DataFrame({
        "entry_time": pd.date_range("2024-04-01", periods=n, freq="1D", tz="America/New_York"),
        "exit_time": pd.date_range("2024-04-01", periods=n, freq="1D", tz="America/New_York"),
        "direction": 1,
        "expected_r": 0.4,
        "actual_r": actual_r,
        "pnl": actual_r * 100,
        "model_probability": probs,
        "actual_result": actual_result,
    })


def test_no_shadow_trades_status():
    empty = pd.DataFrame(columns=["actual_r", "expected_r", "actual_result", "model_probability"])
    result = evaluate_paper_monitor(empty)
    assert result["status"] == "NO_SHADOW_TRADES"
    assert result["n_shadow_trades"] == 0


def test_evaluate_paper_monitor_basic_stats():
    log = _shadow_log()
    result = evaluate_paper_monitor(log)
    assert result["status"] == "OK"
    assert result["n_shadow_trades"] == 20
    assert result["expected_r"] == 0.4
    assert abs(result["actual_mean_r"] - log["actual_r"].mean()) < 1e-9
    assert abs(result["r_prediction_error"] - (log["actual_r"].mean() - 0.4)) < 1e-9
    assert result["calibration"] is not None


def test_calibration_omitted_below_min_trades_threshold():
    log = _shadow_log(n=5)
    result = evaluate_paper_monitor(log, min_trades_for_calibration=10)
    assert result["calibration"] is None
