import pytest

from prop_alpha.config import EngineConfig
from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.discovery.conditions import CONDITION_LIBRARY
from prop_alpha.discovery.setup_generator import GeneratedStrategy, generate_candidate_setups
from prop_alpha.features.pipeline import build_full_feature_set
from prop_alpha.regimes.pipeline import build_regime_features


def test_invalid_direction_raises():
    with pytest.raises(ValueError):
        GeneratedStrategy("X", [CONDITION_LIBRARY[0]], direction=0)


def test_generate_candidate_setups_respects_max_candidates():
    candidates = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=2, max_candidates=10, seed=1)
    assert len(candidates) == 10


def test_generate_candidate_setups_size_one_only():
    candidates = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=1, max_candidates=1000, seed=1)
    assert len(candidates) == 2 * len(CONDITION_LIBRARY)
    assert all(len(c.conditions) == 1 for c in candidates)


def test_alpha_ids_are_unique():
    candidates = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=2, max_candidates=80, seed=1)
    ids = [c.meta.alpha_id for c in candidates]
    assert len(ids) == len(set(ids))


def test_reproducible_with_same_seed():
    a = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=2, max_candidates=50, seed=7)
    b = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=2, max_candidates=50, seed=7)
    assert [c.meta.alpha_name for c in a] == [c.meta.alpha_name for c in b]


def test_invalid_max_combo_size_raises():
    with pytest.raises(ValueError):
        generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=3, max_candidates=10)


def test_family_is_discovered_and_status_hypothesis():
    candidates = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=1, max_candidates=2, seed=1)
    for c in candidates:
        assert c.meta.family == "DISCOVERED"
        assert c.meta.research_status == "HYPOTHESIS"


def test_generate_signals_produces_valid_directions():
    df = generate_synthetic_ohlcv(n_days=30, seed=51)
    config = EngineConfig()
    feats = build_full_feature_set(df, config)
    days = sorted(feats["timestamp"].dt.tz_convert("America/New_York").dt.date.unique())
    in_sample_days = set(days[: int(len(days) * 0.8)])
    feats = build_regime_features(feats, in_sample_days, config.regime)

    candidates = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=2, max_candidates=15, seed=1)
    for candidate in candidates:
        signals = candidate.generate_signals(feats)
        assert set(signals["direction"].unique()).issubset({-1, 0, 1})
        # Every non-zero direction must equal the candidate's own fixed direction.
        nonzero = signals.loc[signals["direction"] != 0, "direction"]
        if not nonzero.empty:
            assert (nonzero == candidate.direction).all()
