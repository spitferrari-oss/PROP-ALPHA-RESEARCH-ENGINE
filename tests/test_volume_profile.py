import pandas as pd

from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.volume_profile import add_volume_profile_features


def test_poc_between_vah_and_val():
    df = generate_synthetic_ohlcv(n_days=15, seed=11)
    feats = add_volume_profile_features(df, tick_size=0.25, bin_ticks=10)
    valid = feats.dropna(subset=["vp_poc", "vp_vah", "vp_val"])
    assert len(valid) > 0
    assert (valid["vp_vah"] >= valid["vp_poc"] - 1e-9).all()
    assert (valid["vp_poc"] >= valid["vp_val"] - 1e-9).all()
    assert (valid["vp_width"] >= 0).all()


def test_prior_day_levels_are_absent_on_first_day_and_present_after():
    df = generate_synthetic_ohlcv(n_days=3, seed=12)
    feats = add_volume_profile_features(df, tick_size=0.25, bin_ticks=10)
    day = feats["timestamp"].dt.tz_convert("America/New_York").dt.date
    first_day = day.iloc[0]

    first_day_rows = feats[day == first_day]
    assert first_day_rows["vp_prior_poc"].isna().all()

    later_rows = feats[day != first_day]
    assert later_rows["vp_prior_poc"].notna().all()


def test_prior_poc_matches_previous_days_final_developing_poc():
    df = generate_synthetic_ohlcv(n_days=3, seed=13)
    feats = add_volume_profile_features(df, tick_size=0.25, bin_ticks=10)
    day = feats["timestamp"].dt.tz_convert("America/New_York").dt.date
    days = sorted(day.unique())

    day1_last_poc = feats[day == days[0]]["vp_poc"].iloc[-1]
    day2_prior_poc = feats[day == days[1]]["vp_prior_poc"].iloc[0]
    assert day1_last_poc == day2_prior_poc


def test_distance_to_prior_poc_is_close_minus_prior_poc():
    df = generate_synthetic_ohlcv(n_days=3, seed=14)
    feats = add_volume_profile_features(df, tick_size=0.25, bin_ticks=10)
    valid = feats.dropna(subset=["vp_prior_poc"])
    diff = valid["vp_dist_to_prior_poc"] - (valid["close"] - valid["vp_prior_poc"])
    assert (diff.abs() < 1e-9).all()
