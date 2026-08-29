import pandas as pd

from prop_alpha.risk.stop_trading import StopTradingPolicy, apply_day_policy


def _trades_for_day(day: str, r_multiples: list[float]) -> pd.DataFrame:
    ts = pd.date_range(f"{day} 09:30", periods=len(r_multiples), freq="15min", tz="America/New_York")
    return pd.DataFrame({
        "entry_time": ts,
        "exit_time": ts,
        "r_multiple": r_multiples,
        "pnl": [r * 100.0 for r in r_multiples],
    })


def test_no_policy_keeps_all_trades():
    trades = _trades_for_day("2024-01-02", [1.0, -1.0, 2.0])
    policy = StopTradingPolicy(name="none")
    out = apply_day_policy(trades, policy)
    assert len(out) == 3


def test_stop_after_profit_r_drops_trades_after_threshold_hit():
    trades = _trades_for_day("2024-01-02", [1.0, 0.5, 1.0, -1.0])  # cum_r: 1.0, 1.5, 2.5, ...
    policy = StopTradingPolicy(name="lock", stop_after_profit_r=1.5)
    out = apply_day_policy(trades, policy)
    # Trade 2 (index 1) pushes cum_r to 1.5 and is kept; trade 3+ are dropped.
    assert len(out) == 2
    assert out["r_multiple"].tolist() == [1.0, 0.5]


def test_stop_after_loss_r_drops_trades_after_threshold_hit():
    trades = _trades_for_day("2024-01-02", [-1.0, -1.0, 1.0])  # cum_r: -1.0, -2.0, ...
    policy = StopTradingPolicy(name="loss_control", stop_after_loss_r=2.0)
    out = apply_day_policy(trades, policy)
    assert len(out) == 2
    assert out["r_multiple"].tolist() == [-1.0, -1.0]


def test_stop_after_n_losses_drops_trades_after_threshold_hit():
    trades = _trades_for_day("2024-01-02", [-0.5, 1.0, -0.5, 2.0])  # losses at idx 0, 2
    policy = StopTradingPolicy(name="two_losses", stop_after_n_losses=2)
    out = apply_day_policy(trades, policy)
    assert len(out) == 3
    assert out["r_multiple"].tolist() == [-0.5, 1.0, -0.5]


def test_policy_resets_across_days():
    day1 = _trades_for_day("2024-01-02", [2.0, 1.0])  # would trip stop_after_profit_r=1.5 after trade 1
    day2 = _trades_for_day("2024-01-03", [1.0, 1.0])
    trades = pd.concat([day1, day2], ignore_index=True)
    policy = StopTradingPolicy(name="lock", stop_after_profit_r=1.5)
    out = apply_day_policy(trades, policy)
    # Day 1: only trade 1 survives (cum_r=2.0 >= 1.5). Day 2: fresh start, first
    # trade alone already trips it (cum_r=1.0 < 1.5, so both should be kept
    # only up through the trade that crosses 1.5) -> both day-2 trades kept
    # since cum_r after trade 1 is 1.0 (<1.5) and after trade 2 is 2.0 (>=1.5).
    assert len(out) == 1 + 2


def test_describe_lists_active_rules():
    policy = StopTradingPolicy(name="x", stop_after_profit_r=2.0, stop_after_n_losses=3)
    desc = policy.describe()
    assert "2.0" in desc
    assert "3" in desc


def test_empty_trades_returns_empty():
    empty = _trades_for_day("2024-01-02", []).iloc[0:0]
    out = apply_day_policy(empty, StopTradingPolicy(name="x", stop_after_profit_r=1.0))
    assert out.empty
