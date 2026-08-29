import pandas as pd

from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.price_volume import build_feature_set


def test_prior_day_high_low_absent_on_first_day_present_after():
    df = generate_synthetic_ohlcv(n_days=3, seed=21)
    feats = build_feature_set(df)
    day = feats["timestamp"].dt.tz_convert("America/New_York").dt.date
    days = sorted(day.unique())

    first_day_rows = feats[day == days[0]]
    assert first_day_rows["prior_day_high"].isna().all()
    assert first_day_rows["prior_day_low"].isna().all()

    later_rows = feats[day != days[0]]
    assert later_rows["prior_day_high"].notna().all()
    assert later_rows["prior_day_low"].notna().all()


def test_prior_day_high_matches_previous_days_actual_max():
    df = generate_synthetic_ohlcv(n_days=3, seed=22)
    feats = build_feature_set(df)
    day = feats["timestamp"].dt.tz_convert("America/New_York").dt.date
    days = sorted(day.unique())

    day1_actual_high = feats[day == days[0]]["high"].max()
    day2_prior_high = feats[day == days[1]]["prior_day_high"].iloc[0]
    assert day1_actual_high == day2_prior_high


def test_prior_day_high_is_never_below_prior_day_low():
    df = generate_synthetic_ohlcv(n_days=10, seed=23)
    feats = build_feature_set(df)
    valid = feats.dropna(subset=["prior_day_high", "prior_day_low"])
    assert (valid["prior_day_high"] >= valid["prior_day_low"]).all()


def test_prior_swing_levels_use_only_past_data():
    df = generate_synthetic_ohlcv(n_days=5, seed=24)
    feats = build_feature_set(df)
    # prior_swing_high at row i must equal rolling_high_20 as of row i-1.
    shifted = feats["rolling_high_20"].shift(1)
    valid = feats["prior_swing_high"].notna() & shifted.notna()
    assert (feats.loc[valid, "prior_swing_high"] == shifted[valid]).all()


def test_delta_acceleration_z_is_finite_where_defined():
    df = generate_synthetic_ohlcv(n_days=5, seed=25)
    feats = build_feature_set(df)
    valid = feats["delta_acceleration_z"].dropna()
    assert len(valid) > 0
    assert valid.abs().max() < 1000  # sanity bound, not a tight statistical claim
