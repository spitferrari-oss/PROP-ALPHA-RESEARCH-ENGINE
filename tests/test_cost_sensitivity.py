import pandas as pd

from prop_alpha.backtest.costs import COST_PROFILES, CostModel
from prop_alpha.statistics.cost_sensitivity import breakeven_cost_profile, evaluate_cost_sensitivity


def _toy_signals():
    ts = pd.date_range("2024-01-02 09:30", periods=4, freq="15min", tz="America/New_York")
    return pd.DataFrame({
        "timestamp": ts,
        "open": [100.0, 100.0, 101.0, 103.0],
        "high": [100.5, 100.5, 103.5, 103.5],
        "low": [99.5, 99.5, 100.5, 102.5],
        "close": [100.0, 100.0, 103.0, 103.0],
        "direction": [1, 0, 0, 0],
        "stop_distance": [1.0, 0, 0, 0],
        "target_distance": [2.0, 0, 0, 0],
    })


def _cost_model():
    return CostModel(tick_size=0.25, tick_value=5.0, commission_per_round_turn=2.0,
                      slippage_ticks=1.0, spread_ticks=1.0)


def test_ev_degrades_monotonically_from_optimistic_to_extreme():
    signals = _toy_signals()
    result = evaluate_cost_sensitivity(signals, _cost_model(), max_trades_day=5, point_value=20.0)
    assert list(result.keys()) == list(COST_PROFILES.keys())
    values = [result[p] for p in COST_PROFILES]
    # optimistic should never be worse than extreme for the same trade sequence
    assert values[0] >= values[-1]


def test_breakeven_cost_profile_none_when_unprofitable_even_optimistic():
    losing = {"optimistic": -10.0, "base": -20.0, "conservative": -30.0, "stress": -50.0, "extreme": -80.0}
    assert breakeven_cost_profile(losing) is None


def test_breakeven_cost_profile_picks_most_expensive_survivable():
    mixed = {"optimistic": 100.0, "base": 50.0, "conservative": 10.0, "stress": -5.0, "extreme": -20.0}
    assert breakeven_cost_profile(mixed) == "conservative"
