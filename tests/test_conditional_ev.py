import pandas as pd

from prop_alpha.regimes.conditional_ev import conditional_ev_by_regime


def _trades():
    ts = pd.date_range("2024-01-02 09:30", periods=4, freq="15min", tz="America/New_York")
    return pd.DataFrame({
        "entry_time": ts,
        "exit_time": ts,
        "r_multiple": [1.0, -1.0, 2.0, -0.5],
        "pnl": [100.0, -100.0, 200.0, -50.0],
    })


def _features():
    ts = pd.date_range("2024-01-02 09:30", periods=4, freq="15min", tz="America/New_York")
    return pd.DataFrame({"timestamp": ts, "regime_rule": ["TREND_UP", "TREND_UP", "RANGE", "RANGE"]})


def test_groups_by_regime_and_computes_ev():
    out = conditional_ev_by_regime(_trades(), _features())
    assert set(out["regime_rule"]) == {"TREND_UP", "RANGE"}
    trend_row = out[out["regime_rule"] == "TREND_UP"].iloc[0]
    assert trend_row["n_trades"] == 2
    assert trend_row["ev_dollars"] == 0.0  # (100 + -100) / 2
    range_row = out[out["regime_rule"] == "RANGE"].iloc[0]
    assert range_row["n_trades"] == 2
    assert range_row["ev_dollars"] == 75.0  # (200 - 50) / 2


def test_sorted_descending_by_ev():
    out = conditional_ev_by_regime(_trades(), _features())
    assert out["ev_dollars"].is_monotonic_decreasing


def test_empty_trades_returns_empty_frame():
    empty = _trades().iloc[0:0]
    out = conditional_ev_by_regime(empty, _features())
    assert out.empty
    assert "regime_rule" in out.columns


def test_unmatched_entry_time_falls_back_to_unknown():
    trades = _trades().copy()
    trades.loc[0, "entry_time"] = pd.Timestamp("2099-01-01", tz="America/New_York")
    out = conditional_ev_by_regime(trades, _features())
    assert "UNKNOWN" in set(out["regime_rule"])
