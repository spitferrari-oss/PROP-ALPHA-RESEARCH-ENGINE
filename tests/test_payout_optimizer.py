import numpy as np
import pandas as pd

from prop_alpha.config import PropFirmConfig
from prop_alpha.risk.payout_optimizer import compare_policies, default_policies, rank_policies_by_expected_payout


def _prop(**overrides):
    base = dict(account_size=100_000.0, profit_target=8_000.0, max_daily_loss=5_000.0,
                max_total_loss=10_000.0, trailing_drawdown=True, minimum_trading_days=5,
                payout_threshold=8_000.0)
    base.update(overrides)
    return PropFirmConfig(**base)


def _synthetic_trades(n_days=60, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        day = pd.Timestamp("2024-01-02", tz="America/New_York") + pd.Timedelta(days=d)
        n_trades = rng.integers(1, 4)
        for t in range(n_trades):
            entry = 17000.0
            stop_dist = rng.uniform(5, 15)
            r = rng.normal(0.3, 1.2)
            direction = 1
            rows.append({
                "entry_time": day + pd.Timedelta(minutes=30 * t),
                "exit_time": day + pd.Timedelta(minutes=30 * t + 15),
                "direction": direction,
                "entry_price": entry,
                "exit_price": entry + r * stop_dist,
                "stop_price": entry - stop_dist,
                "target_price": entry + 2 * stop_dist,
                "exit_reason": "TARGET" if r > 0 else "STOP",
                "r_multiple": r,
                "pnl": r * stop_dist * 20.0,
            })
    return pd.DataFrame(rows)


def test_default_policies_returns_five_named_policies():
    policies = default_policies()
    names = [p[0] for p in policies]
    assert names == ["A_constant_risk", "B_increase_after_profit", "C_decrease_after_loss",
                      "D_profit_lock_1R", "E_stop_after_2R"]


def test_compare_policies_returns_one_result_per_policy():
    trades = _synthetic_trades()
    results = compare_policies(trades, _prop(), point_value=20.0, seed=1, n_paths=500, n_days=20)
    assert len(results) == 5
    for r in results:
        assert "expected_payout" in r
        assert "p_breach" in r


def test_stop_trading_policies_never_produce_more_trades_than_baseline():
    trades = _synthetic_trades()
    results = compare_policies(trades, _prop(), point_value=20.0, seed=1, n_paths=500, n_days=20)
    by_name = {r["policy_name"]: r for r in results}
    assert by_name["D_profit_lock_1R"]["n_trades"] <= by_name["A_constant_risk"]["n_trades"]
    assert by_name["E_stop_after_2R"]["n_trades"] <= by_name["A_constant_risk"]["n_trades"]


def test_rank_policies_by_expected_payout_sorts_descending():
    results = [
        {"policy_name": "low", "expected_payout": 100.0, "p_breach": 0.1},
        {"policy_name": "high", "expected_payout": 500.0, "p_breach": 0.2},
        {"policy_name": "nan", "expected_payout": float("nan"), "p_breach": float("nan")},
    ]
    ranked = rank_policies_by_expected_payout(results)
    assert [r["policy_name"] for r in ranked] == ["high", "low", "nan"]


def test_compare_policies_handles_empty_trades():
    empty = _synthetic_trades().iloc[0:0]
    results = compare_policies(empty, _prop(), point_value=20.0, seed=1, n_paths=100, n_days=10)
    assert len(results) == 5
    for r in results:
        assert r["n_trades"] == 0
