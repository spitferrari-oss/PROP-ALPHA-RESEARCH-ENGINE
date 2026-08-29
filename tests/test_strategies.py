import pytest

from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.price_volume import build_feature_set
from prop_alpha.features.volume_profile import add_volume_profile_features
from prop_alpha.strategies.absorption_reversal import AbsorptionReversal
from prop_alpha.strategies.baselines import BASELINE_STRATEGIES, RandomDirection, RandomEntry
from prop_alpha.strategies.compression_expansion import CompressionExpansion
from prop_alpha.strategies.delta_acceleration_momentum import DeltaAccelerationMomentum
from prop_alpha.strategies.liquidity_sweep_reversal import LiquiditySweepReversal
from prop_alpha.strategies.momentum import IntradayMomentum
from prop_alpha.strategies.opening_drive_continuation import OpeningDriveContinuation
from prop_alpha.strategies.opening_range import OpeningRangeBreakout
from prop_alpha.strategies.prior_day_breakout import PriorDayHighLowBreakout
from prop_alpha.strategies.prior_day_reversal import PriorDayHighLowReversal
from prop_alpha.strategies.volume_profile_breakout import VolumeProfileBreakout
from prop_alpha.strategies.volume_profile_reversion import VolumeProfileMeanReversion
from prop_alpha.strategies.vwap_reversion import VwapMeanReversion

ALPHA_STRATEGIES = [
    IntradayMomentum, OpeningRangeBreakout, VwapMeanReversion,
    VolumeProfileMeanReversion, VolumeProfileBreakout,
    PriorDayHighLowReversal, PriorDayHighLowBreakout,
    DeltaAccelerationMomentum, AbsorptionReversal, LiquiditySweepReversal,
    CompressionExpansion, OpeningDriveContinuation,
]

ALL_STRATEGIES = ALPHA_STRATEGIES + BASELINE_STRATEGIES


@pytest.fixture(scope="module")
def features():
    df = generate_synthetic_ohlcv(n_days=30, seed=3)
    df = build_feature_set(df)
    df = add_volume_profile_features(df, tick_size=0.25, bin_ticks=10)
    return df


def _instantiate(strategy_cls):
    if strategy_cls is RandomEntry:
        return strategy_cls(seed=1)
    if strategy_cls is RandomDirection:
        return strategy_cls(seed=2)
    return strategy_cls()


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_direction_values_are_valid(strategy_cls, features):
    strategy = _instantiate(strategy_cls)
    signals = strategy.generate_signals(features)
    assert set(signals["direction"].unique()).issubset({-1, 0, 1})


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_risk_levels_nonnegative_when_signal_present(strategy_cls, features):
    strategy = _instantiate(strategy_cls)
    signals = strategy.with_risk_levels(features)
    active = signals[signals["direction"] != 0].dropna(subset=["stop_distance"])
    assert (active["stop_distance"] >= 0).all()
    assert (active["target_distance"] >= 0).all()


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_alpha_ids_are_unique_and_present(strategy_cls, features):
    strategy = _instantiate(strategy_cls)
    assert strategy.meta.alpha_id
    assert strategy.meta.alpha_name


def test_all_alpha_ids_unique():
    ids = [_instantiate(cls).meta.alpha_id for cls in ALL_STRATEGIES]
    assert len(ids) == len(set(ids))


def test_baseline_family_is_tagged_baseline():
    for cls in BASELINE_STRATEGIES:
        assert _instantiate(cls).meta.family == "BASELINE"


def test_alpha_families_are_not_baseline():
    for cls in ALPHA_STRATEGIES:
        assert _instantiate(cls).meta.family != "BASELINE"


def test_random_strategies_reproducible_with_same_seed(features):
    a = RandomEntry(seed=7).generate_signals(features)
    b = RandomEntry(seed=7).generate_signals(features)
    assert (a["direction"] == b["direction"]).all()
