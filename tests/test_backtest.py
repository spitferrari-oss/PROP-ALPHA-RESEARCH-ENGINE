import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.backtest.engine import run_backtest


def _cost_model(**overrides):
    base = dict(tick_size=0.25, tick_value=5.0, commission_per_round_turn=0.0,
                slippage_ticks=0.0, spread_ticks=0.0)
    base.update(overrides)
    return CostModel(**base)


def test_stop_hit_before_target_when_both_touched_same_bar():
    # Conservative assumption: if both stop and target are touched within the
    # same bar, the stop is assumed to fill first.
    ts = pd.date_range("2024-01-02 09:30", periods=3, freq="15min", tz="America/New_York")
    df = pd.DataFrame({
        "timestamp": ts,
        "open": [100.0, 100.0, 100.0],
        "high": [100.5, 105.0, 105.0],
        "low": [99.5, 95.0, 95.0],
        "close": [100.0, 100.0, 100.0],
        "direction": [1, 0, 0],
        "stop_distance": [1.0, 0, 0],
        "target_distance": [2.0, 0, 0],
    })
    trades = run_backtest(df, _cost_model(), max_trades_day=5, point_value=20.0)
    assert len(trades) == 1
    assert trades[0].exit_reason == "STOP"


def test_position_flattened_at_end_of_day():
    ts1 = pd.date_range("2024-01-02 09:30", periods=3, freq="15min", tz="America/New_York")
    ts2 = pd.date_range("2024-01-03 09:30", periods=1, freq="15min", tz="America/New_York")
    ts = list(ts1) + list(ts2)
    df = pd.DataFrame({
        "timestamp": ts,
        "open": [100.0, 100.0, 100.2, 101.0],
        "high": [100.5, 100.5, 100.5, 101.5],
        "low": [99.5, 99.5, 99.8, 100.5],
        "close": [100.0, 100.0, 100.2, 101.0],
        "direction": [1, 0, 0, 0],
        "stop_distance": [5.0, 0, 0, 0],
        "target_distance": [10.0, 0, 0, 0],
    })
    trades = run_backtest(df, _cost_model(), max_trades_day=5, point_value=20.0)
    assert len(trades) == 1
    assert trades[0].exit_reason == "EOD"
    assert trades[0].exit_time == ts1[-1]


def test_no_entries_without_signal():
    ts = pd.date_range("2024-01-02 09:30", periods=5, freq="15min", tz="America/New_York")
    df = pd.DataFrame({
        "timestamp": ts,
        "open": [100.0] * 5,
        "high": [100.5] * 5,
        "low": [99.5] * 5,
        "close": [100.0] * 5,
        "direction": [0] * 5,
        "stop_distance": [1.0] * 5,
        "target_distance": [2.0] * 5,
    })
    trades = run_backtest(df, _cost_model(), max_trades_day=5, point_value=20.0)
    assert len(trades) == 0


def test_max_trades_per_day_respected():
    # Alternate signal every other bar with immediate EOD/stop resolution
    # forced by a tiny stop distance so a new entry can occur soon after.
    ts = pd.date_range("2024-01-02 09:30", periods=10, freq="15min", tz="America/New_York")
    direction = [1, 0] * 5
    df = pd.DataFrame({
        "timestamp": ts,
        "open": [100.0] * 10,
        "high": [100.1] * 10,
        "low": [99.0] * 10,  # always trips the stop next bar
        "close": [100.0] * 10,
        "direction": direction,
        "stop_distance": [0.5] * 10,
        "target_distance": [1.0] * 10,
    })
    trades = run_backtest(df, _cost_model(), max_trades_day=2, point_value=20.0)
    assert len(trades) <= 2
