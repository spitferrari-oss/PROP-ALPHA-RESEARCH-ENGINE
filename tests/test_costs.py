import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.backtest.engine import run_backtest


def _toy_df():
    # 3 bars: signal bar (direction=1), entry bar, exit bar hitting target.
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


def test_higher_commission_reduces_pnl():
    df = _toy_df()
    cheap = CostModel(tick_size=0.25, tick_value=5.0, commission_per_round_turn=1.0,
                       slippage_ticks=0.0, spread_ticks=0.0)
    expensive = CostModel(tick_size=0.25, tick_value=5.0, commission_per_round_turn=50.0,
                           slippage_ticks=0.0, spread_ticks=0.0)

    cheap_trades = run_backtest(df.copy(), cheap, max_trades_day=5, point_value=20.0)
    expensive_trades = run_backtest(df.copy(), expensive, max_trades_day=5, point_value=20.0)

    assert len(cheap_trades) == 1
    assert len(expensive_trades) == 1
    assert expensive_trades[0].pnl < cheap_trades[0].pnl


def test_higher_slippage_reduces_pnl():
    df = _toy_df()
    low_slip = CostModel(tick_size=0.25, tick_value=5.0, commission_per_round_turn=0.0,
                          slippage_ticks=0.0, spread_ticks=0.0)
    high_slip = CostModel(tick_size=0.25, tick_value=5.0, commission_per_round_turn=0.0,
                           slippage_ticks=10.0, spread_ticks=0.0)

    low_trades = run_backtest(df.copy(), low_slip, max_trades_day=5, point_value=20.0)
    high_trades = run_backtest(df.copy(), high_slip, max_trades_day=5, point_value=20.0)

    assert high_trades[0].pnl < low_trades[0].pnl
