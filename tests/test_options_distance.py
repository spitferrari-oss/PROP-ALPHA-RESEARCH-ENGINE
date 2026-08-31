import datetime as dt

from prop_alpha.options.distance import compute_distance_features, compute_level_distances
from prop_alpha.options.models import LevelType, OptionsLevel


def test_compute_distance_features_absolute_and_percentage():
    features = compute_distance_features(price=4500.0, level_value=4480.0)
    assert features.absolute == 20.0
    assert features.percentage == 20.0 / 4500.0


def test_compute_distance_features_atr_normalized():
    features = compute_distance_features(price=4500.0, level_value=4480.0, atr=10.0)
    assert features.atr_normalized == 2.0


def test_compute_distance_features_atr_none_when_atr_missing_or_zero():
    assert compute_distance_features(4500.0, 4480.0, atr=None).atr_normalized is None
    assert compute_distance_features(4500.0, 4480.0, atr=0.0).atr_normalized is None


def test_compute_distance_features_vol_normalized():
    features = compute_distance_features(price=4500.0, level_value=4480.0, realized_vol=0.01)
    assert features.vol_normalized == 20.0 / (4500.0 * 0.01)


def test_compute_distance_features_vol_none_when_vol_missing_or_zero():
    assert compute_distance_features(4500.0, 4480.0, realized_vol=None).vol_normalized is None
    assert compute_distance_features(4500.0, 4480.0, realized_vol=0.0).vol_normalized is None


def test_compute_distance_features_zero_price_percentage_is_nan():
    features = compute_distance_features(price=0.0, level_value=10.0)
    assert features.percentage != features.percentage  # NaN


def _level(value):
    return OptionsLevel(
        underlying="SPX", timestamp=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc), strike=value,
        type=LevelType.GAMMA_FLIP, value=value, distance_from_spot=None, source="gexbot", metric="gamma_flip",
    )


def test_compute_level_distances_returns_one_entry_per_level():
    levels = [_level(4480.0), _level(4550.0)]
    results = compute_level_distances(levels, price=4500.0, atr=10.0)
    assert len(results) == 2
    assert results[0]["level"] is levels[0]
    assert results[0]["distance"].absolute == 20.0
    assert results[1]["distance"].absolute == -50.0
