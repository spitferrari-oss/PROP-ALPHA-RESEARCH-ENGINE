import pytest

from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.price_volume import build_feature_set
from prop_alpha.strategies.momentum import IntradayMomentum
from prop_alpha.strategies.opening_range import OpeningRangeBreakout
from prop_alpha.strategies.vwap_reversion import VwapMeanReversion

STRATEGIES = [IntradayMomentum, OpeningRangeBreakout, VwapMeanReversion]


@pytest.fixture(scope="module")
def features():
    df = generate_synthetic_ohlcv(n_days=30, seed=3)
    return build_feature_set(df)


@pytest.mark.parametrize("strategy_cls", STRATEGIES)
def test_direction_values_are_valid(strategy_cls, features):
    strategy = strategy_cls()
    signals = strategy.generate_signals(features)
    assert set(signals["direction"].unique()).issubset({-1, 0, 1})


@pytest.mark.parametrize("strategy_cls", STRATEGIES)
def test_risk_levels_nonnegative_when_signal_present(strategy_cls, features):
    strategy = strategy_cls()
    signals = strategy.with_risk_levels(features)
    active = signals[signals["direction"] != 0].dropna(subset=["stop_distance"])
    assert (active["stop_distance"] >= 0).all()
    assert (active["target_distance"] >= 0).all()
