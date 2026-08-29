import pandas as pd

from prop_alpha.config import PropFirmConfig
from prop_alpha.risk.position_sizing import SizingConfig, apply_position_sizing, contracts_for_trade


def _prop(**overrides):
    base = dict(account_size=100_000.0, profit_target=8_000.0, max_daily_loss=5_000.0,
                max_total_loss=10_000.0, trailing_drawdown=True, minimum_trading_days=5,
                payout_threshold=8_000.0)
    base.update(overrides)
    return PropFirmConfig(**base)


def test_zero_contracts_for_invalid_stop():
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=0.005)
    assert contracts_for_trade(config, equity=100_000, stop_distance_points=0, point_value=20.0) == 0
    assert contracts_for_trade(config, equity=100_000, stop_distance_points=-5, point_value=20.0) == 0


def test_fixed_contracts_method_ignores_equity():
    config = SizingConfig(method="fixed_contracts", fixed_contracts=3, max_contracts=20)
    n = contracts_for_trade(config, equity=1.0, stop_distance_points=10, point_value=20.0)
    assert n == 3


def test_fixed_risk_scales_with_equity():
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=0.01, max_contracts=1000)
    # risk_dollars = equity * 1%; risk_per_contract = 10 points * $20 = $200
    small = contracts_for_trade(config, equity=20_000, stop_distance_points=10, point_value=20.0)
    large = contracts_for_trade(config, equity=200_000, stop_distance_points=10, point_value=20.0)
    assert small == 1  # 20_000*0.01 / 200 = 1.0
    assert large == 10  # 200_000*0.01 / 200 = 10.0


def test_max_contracts_cap_enforced():
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=1.0, max_contracts=5)
    n = contracts_for_trade(config, equity=1_000_000, stop_distance_points=1, point_value=20.0)
    assert n == 5


def test_dynamic_rule_increase_after_profit():
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=0.01, dynamic_rule="increase_after_profit",
                           dynamic_multiplier=2.0, max_contracts=1000)
    flat = contracts_for_trade(config, equity=100_000, stop_distance_points=10, point_value=20.0, daily_cum_r_so_far=0.0)
    after_profit = contracts_for_trade(config, equity=100_000, stop_distance_points=10, point_value=20.0, daily_cum_r_so_far=1.0)
    assert after_profit == 2 * flat


def test_dynamic_rule_decrease_after_loss():
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=0.01, dynamic_rule="decrease_after_loss",
                           dynamic_multiplier=2.0, max_contracts=1000)
    flat = contracts_for_trade(config, equity=100_000, stop_distance_points=10, point_value=20.0, daily_cum_r_so_far=0.0)
    after_loss = contracts_for_trade(config, equity=100_000, stop_distance_points=10, point_value=20.0, daily_cum_r_so_far=-1.0)
    assert after_loss == flat // 2


def test_prop_aware_caps_below_remaining_budget():
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=1.0, max_contracts=1000, prop_aware=True)
    # Risk per contract = 10 * $20 = $200; only $500 of daily budget left -> at most 2 contracts.
    n = contracts_for_trade(config, equity=1_000_000, stop_distance_points=10, point_value=20.0,
                             remaining_daily_risk_budget=500.0)
    assert n == 2


def _toy_trades():
    ts1 = pd.date_range("2024-01-02 09:30", periods=1, freq="15min", tz="America/New_York")
    ts2 = pd.date_range("2024-01-03 09:30", periods=1, freq="15min", tz="America/New_York")
    return pd.DataFrame({
        "entry_time": list(ts1) + list(ts2),
        "exit_time": list(ts1) + list(ts2),
        "direction": [1, 1],
        "entry_price": [100.0, 100.0],
        "exit_price": [102.0, 98.0],
        "stop_price": [99.0, 99.0],  # stop_distance = 1.0 point
        "target_price": [102.0, 102.0],
        "exit_reason": ["TARGET", "STOP"],
        "r_multiple": [2.0, -1.0],
        "pnl": [40.0, -20.0],  # per-contract dollar pnl
    })


def test_apply_position_sizing_scales_pnl_by_contracts():
    trades = _toy_trades()
    config = SizingConfig(method="fixed_contracts", fixed_contracts=3, prop_aware=False)
    sized = apply_position_sizing(trades, config, _prop(), point_value=20.0)
    assert (sized["contracts"] == 3).all()
    assert sized["pnl"].tolist() == [120.0, -60.0]


def test_apply_position_sizing_never_exceeds_daily_budget_on_a_single_trade():
    trades = _toy_trades()
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=1.0, max_contracts=1000, prop_aware=True)
    prop = _prop(max_daily_loss=1_000.0)
    sized = apply_position_sizing(trades, config, prop, point_value=20.0)
    # stop_distance=1.0 point * $20/point = $20 risk per contract; budget on day 1 is $1000.
    worst_case_loss = sized["contracts"] * 1.0 * 20.0
    assert (worst_case_loss <= 1_000.0 + 1e-9).all()


def test_apply_position_sizing_resets_daily_state_across_days():
    # Day 1's trade closes +2R; if daily_cum_r carried over into day 2, the
    # "increase_after_profit" rule would double day 2's risk. It shouldn't:
    # day 2 must size off a flat, reset daily_cum_r=0, using only day 2's
    # start-of-day equity (which does legitimately include day 1's P&L).
    trades = _toy_trades()
    config = SizingConfig(method="fixed_risk", risk_per_trade_pct=0.01, dynamic_rule="increase_after_profit",
                           dynamic_multiplier=2.0, max_contracts=1000, prop_aware=False)
    sized = apply_position_sizing(trades, config, _prop(), point_value=20.0)

    day1_contracts = sized.loc[0, "contracts"]
    day1_equity_after = 100_000.0 + day1_contracts * trades.loc[0, "pnl"]
    expected_day2_contracts = contracts_for_trade(
        config, equity=day1_equity_after, stop_distance_points=1.0, point_value=20.0, daily_cum_r_so_far=0.0,
    )
    assert sized.loc[1, "contracts"] == expected_day2_contracts


def test_empty_trades_returns_empty_with_contracts_column():
    empty = _toy_trades().iloc[0:0]
    sized = apply_position_sizing(empty, SizingConfig(), _prop(), point_value=20.0)
    assert sized.empty
    assert "contracts" in sized.columns
