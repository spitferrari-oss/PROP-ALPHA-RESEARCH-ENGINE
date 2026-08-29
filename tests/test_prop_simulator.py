import numpy as np

from prop_alpha.config import PropFirmConfig
from prop_alpha.prop.simulator import simulate_prop_paths


def _prop(**overrides):
    base = dict(
        account_size=100_000.0, profit_target=8_000.0, max_daily_loss=5_000.0,
        max_total_loss=10_000.0, trailing_drawdown=True, minimum_trading_days=5,
        payout_threshold=8_000.0,
    )
    base.update(overrides)
    return PropFirmConfig(**base)


def test_all_paths_breach_on_immediate_large_loss():
    paths = np.full((100, 10), -6_000.0)  # exceeds max_daily_loss every day
    result = simulate_prop_paths(paths, _prop())
    assert result["p_breach"] == 1.0
    assert result["p_payout"] == 0.0


def test_all_paths_pay_out_on_steady_profit():
    paths = np.full((100, 20), 1_000.0)  # +1000/day, reaches +8000 by day 8
    result = simulate_prop_paths(paths, _prop())
    assert result["p_payout"] == 1.0
    assert result["p_breach"] == 0.0
    assert result["expected_payout"] == 8_000.0
    assert result["expected_days_to_payout"] >= 5  # minimum_trading_days respected


def test_flat_paths_neither_breach_nor_payout():
    paths = np.zeros((50, 15))
    result = simulate_prop_paths(paths, _prop())
    assert result["p_breach"] == 0.0
    assert result["p_payout"] == 0.0
    assert result["terminal_balance_p50"] == 100_000.0


def test_reducing_allowed_risk_cannot_increase_breach_probability():
    # Property-based invariant (spec §87): scaling daily P&L down (lower
    # risk) must not increase the probability of breaching account limits.
    rng = np.random.default_rng(7)
    base_paths = rng.normal(loc=-200, scale=3000, size=(2000, 20))

    full_risk = simulate_prop_paths(base_paths, _prop())
    half_risk = simulate_prop_paths(base_paths * 0.5, _prop())

    assert half_risk["p_breach"] <= full_risk["p_breach"] + 1e-9
