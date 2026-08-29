import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.pipeline import build_full_feature_set
from prop_alpha.config import EngineConfig
from prop_alpha.statistics.walk_forward import make_folds, run_walk_forward
from prop_alpha.strategies.momentum import IntradayMomentum


def _cost_model():
    return CostModel(tick_size=0.25, tick_value=5.0, commission_per_round_turn=4.2,
                      slippage_ticks=1.0, spread_ticks=1.0)


def test_make_folds_covers_every_day_exactly_once():
    df = generate_synthetic_ohlcv(n_days=40, seed=31)
    folds = make_folds(df, n_folds=5)
    all_days = sorted(d for fold in folds for d in fold)
    expected_days = sorted(df["timestamp"].dt.tz_convert("America/New_York").dt.date.unique())
    assert all_days == list(expected_days)
    assert len(folds) == 5


def test_make_folds_handles_more_folds_than_days():
    df = generate_synthetic_ohlcv(n_days=3, seed=32)
    folds = make_folds(df, n_folds=10)
    assert len(folds) == 1


def test_run_walk_forward_returns_one_ev_per_fold():
    df = generate_synthetic_ohlcv(n_days=60, seed=33)
    config = EngineConfig()
    feats = build_full_feature_set(df, config)
    strategy = IntradayMomentum()
    result = run_walk_forward(
        strategy, feats, _cost_model(),
        max_trades_day=3, point_value=20.0, n_folds=4,
    )
    assert result["n_folds"] == 4
    assert len(result["fold_ev_per_day"]) == 4
    assert 0.0 <= result["positive_fold_fraction"] <= 1.0
