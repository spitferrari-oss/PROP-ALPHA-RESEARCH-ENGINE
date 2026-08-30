import numpy as np
import pandas as pd

from prop_alpha.paper.shadow import build_shadow_log


def _oos_trades(n=5):
    entry = pd.date_range("2024-03-01 09:45", periods=n, freq="45min", tz="America/New_York")
    exit_ = entry + pd.Timedelta(minutes=30)
    return pd.DataFrame({
        "entry_time": entry,
        "exit_time": exit_,
        "direction": [1, -1, 1, 1, -1][:n],
        "r_multiple": [1.5, -1.0, 0.5, -0.8, 2.0][:n],
        "pnl": [150.0, -100.0, 50.0, -80.0, 200.0][:n],
    })


class _FakeModel:
    def predict_proba_rf(self, X):
        return np.linspace(0.4, 0.9, len(X))


def test_build_shadow_log_empty_trades_returns_empty_frame():
    log = build_shadow_log(pd.DataFrame(), pd.DataFrame(), None, {"expectancy_r": 0.3})
    assert log.empty
    assert list(log.columns) == [
        "entry_time", "exit_time", "direction",
        "expected_r", "actual_r", "pnl", "model_probability", "actual_result",
    ]


def test_build_shadow_log_basic_fields():
    trades = _oos_trades()
    X_oos = pd.DataFrame(index=range(len(trades)))
    log = build_shadow_log(trades, X_oos, None, {"expectancy_r": 0.25})
    assert len(log) == len(trades)
    assert (log["expected_r"] == 0.25).all()
    assert list(log["actual_r"]) == list(trades["r_multiple"])
    assert list(log["actual_result"]) == [1, 0, 1, 0, 1]
    assert log["model_probability"].isna().all()


def test_build_shadow_log_attaches_model_probability_when_model_and_features_align():
    trades = _oos_trades()
    X_oos = pd.DataFrame(index=range(len(trades)))
    log = build_shadow_log(trades, X_oos, _FakeModel(), {"expectancy_r": 0.25})
    assert not log["model_probability"].isna().any()
    assert (log["model_probability"] >= 0).all() and (log["model_probability"] <= 1).all()


def test_build_shadow_log_skips_model_probability_on_length_mismatch():
    trades = _oos_trades()
    X_oos = pd.DataFrame(index=range(len(trades) - 1))
    log = build_shadow_log(trades, X_oos, _FakeModel(), {"expectancy_r": 0.25})
    assert log["model_probability"].isna().all()
