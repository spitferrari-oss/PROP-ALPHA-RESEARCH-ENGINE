import pandas as pd
import pytest

from prop_alpha.config import RegimeConfig
from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.price_volume import build_feature_set
from prop_alpha.regimes.statistical import GmmRegimeClassifier


@pytest.fixture(scope="module")
def features():
    df = generate_synthetic_ohlcv(n_days=60, seed=41)
    return build_feature_set(df)


def _in_sample(df, frac=0.8):
    days = sorted(df["timestamp"].dt.tz_convert("America/New_York").dt.date.unique())
    cutoff = days[int(len(days) * frac)]
    day = df["timestamp"].dt.tz_convert("America/New_York").dt.date
    return set(days[:days.index(cutoff)]), df[day < cutoff]


def test_fit_predict_labels_within_range(features):
    is_days, df_is = _in_sample(features)
    clf = GmmRegimeClassifier(RegimeConfig(gmm_n_components=3)).fit(df_is)
    out = clf.predict(features)
    valid_labels = out.loc[out["regime_gmm"] >= 0, "regime_gmm"]
    assert valid_labels.between(0, 2).all()


def test_confidence_in_unit_interval(features):
    is_days, df_is = _in_sample(features)
    clf = GmmRegimeClassifier().fit(df_is)
    out = clf.predict(features)
    conf = out["regime_gmm_confidence"].dropna()
    assert (conf >= 0).all() and (conf <= 1).all()


def test_nan_rows_get_sentinel_label(features):
    is_days, df_is = _in_sample(features)
    clf = GmmRegimeClassifier().fit(df_is)
    out = clf.predict(features)
    nan_rows = features[FEATURE_NAN_MASK(features)]
    if not nan_rows.empty:
        idx = nan_rows.index
        assert (out.loc[idx, "regime_gmm"] == -1).all()


def FEATURE_NAN_MASK(df):
    from prop_alpha.regimes.statistical import FEATURE_COLUMNS
    return df[FEATURE_COLUMNS].isna().any(axis=1)


def test_reproducible_with_same_seed(features):
    is_days, df_is = _in_sample(features)
    clf1 = GmmRegimeClassifier(RegimeConfig(gmm_seed=7)).fit(df_is)
    clf2 = GmmRegimeClassifier(RegimeConfig(gmm_seed=7)).fit(df_is)
    out1 = clf1.predict(features)
    out2 = clf2.predict(features)
    assert (out1["regime_gmm"] == out2["regime_gmm"]).all()


def test_predict_before_fit_raises():
    clf = GmmRegimeClassifier()
    with pytest.raises(RuntimeError):
        clf.predict(pd.DataFrame({"log_returns": [0.1], "realized_vol_20": [0.1], "volume_z": [0.1]}))


def test_fit_raises_with_too_little_data():
    tiny = pd.DataFrame({"log_returns": [0.1, 0.2], "realized_vol_20": [0.1, 0.2], "volume_z": [0.1, 0.2]})
    clf = GmmRegimeClassifier(RegimeConfig(gmm_n_components=4))
    with pytest.raises(ValueError):
        clf.fit(tiny)
