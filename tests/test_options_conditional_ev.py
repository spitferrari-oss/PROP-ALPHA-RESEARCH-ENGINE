import pandas as pd

from prop_alpha.options.conditional_ev import conditional_ev_by_gex_regime


def _trades():
    return pd.DataFrame({
        "entry_time": pd.to_datetime([
            "2024-01-02 09:31", "2024-01-02 09:46", "2024-01-02 10:01", "2024-01-02 10:16",
        ], utc=True),
        "pnl": [100.0, -50.0, 200.0, -20.0],
        "r_multiple": [1.0, -0.5, 2.0, -0.2],
    })


def _synced(regimes):
    return pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2024-01-02 09:31", "2024-01-02 09:46", "2024-01-02 10:01", "2024-01-02 10:16",
        ], utc=True),
        "gex_regime": regimes,
    })


def test_conditional_ev_groups_by_regime_and_sorts_by_ev_descending():
    trades = _trades()
    synced = _synced(["POSITIVE_GAMMA", "NEGATIVE_GAMMA", "POSITIVE_GAMMA", "NEGATIVE_GAMMA"])

    result = conditional_ev_by_gex_regime(trades, synced)

    assert set(result["gex_regime"]) == {"POSITIVE_GAMMA", "NEGATIVE_GAMMA"}
    positive_row = result[result["gex_regime"] == "POSITIVE_GAMMA"].iloc[0]
    assert positive_row["n_trades"] == 2
    assert positive_row["ev_dollars"] == 150.0  # (100 + 200) / 2
    # sorted descending by EV -> POSITIVE_GAMMA (150) before NEGATIVE_GAMMA (-35)
    assert result.iloc[0]["gex_regime"] == "POSITIVE_GAMMA"


def test_conditional_ev_empty_trades_returns_empty_frame_with_columns():
    result = conditional_ev_by_gex_regime(pd.DataFrame(), _synced(["NEUTRAL"] * 4))
    assert list(result.columns) == ["gex_regime", "n_trades", "win_rate", "avg_r", "ev_dollars"]
    assert result.empty


def test_conditional_ev_missing_regime_column_returns_empty_frame():
    trades = _trades()
    synced = pd.DataFrame({"timestamp": _synced(["NEUTRAL"] * 4)["timestamp"]})  # no gex_regime column
    result = conditional_ev_by_gex_regime(trades, synced)
    assert result.empty


def test_conditional_ev_unmatched_trade_falls_back_to_unknown():
    trades = _trades()
    synced = _synced(["POSITIVE_GAMMA", "POSITIVE_GAMMA", "POSITIVE_GAMMA", "POSITIVE_GAMMA"]).iloc[:2]
    result = conditional_ev_by_gex_regime(trades, synced)
    assert "UNKNOWN" in set(result["gex_regime"])
