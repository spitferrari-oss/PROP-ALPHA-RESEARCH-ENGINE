import numpy as np
import pandas as pd
import pytest

from prop_alpha.research_templates.gex_market_frame import enrich_synced_frame_with_gex_features


def _synced_frame():
    return pd.DataFrame({
        "close": [100.0, 101.0, 102.0, 103.0],
        "options_gex": [0.0, 0.0, 0.0, 100.0],  # last value a strong positive outlier
        "options_dex": [10.0, -5.0, 0.0, np.nan],
        "options_gamma_flip": [99.0, 100.0, 101.0, 102.0],
    })


def test_enrich_adds_gex_regime_column():
    result = enrich_synced_frame_with_gex_features(_synced_frame())
    assert "gex_regime" in result.columns
    assert len(result) == 4


def test_enrich_adds_dex_state_columns():
    result = enrich_synced_frame_with_gex_features(_synced_frame())
    for col in ("dex_magnitude", "dex_sign", "dex_concentration", "dex_change", "dex_acceleration"):
        assert col in result.columns


def test_enrich_preserves_original_columns():
    result = enrich_synced_frame_with_gex_features(_synced_frame())
    assert list(_synced_frame().columns) == [c for c in result.columns if c in _synced_frame().columns]
    assert result["close"].tolist() == [100.0, 101.0, 102.0, 103.0]


def test_enrich_missing_options_gex_raises():
    df = _synced_frame().drop(columns=["options_gex"])
    with pytest.raises(ValueError, match="options_gex"):
        enrich_synced_frame_with_gex_features(df)


def test_enrich_missing_options_dex_raises():
    df = _synced_frame().drop(columns=["options_dex"])
    with pytest.raises(ValueError, match="options_dex"):
        enrich_synced_frame_with_gex_features(df)


def test_enrich_does_not_mutate_input():
    df = _synced_frame()
    enrich_synced_frame_with_gex_features(df)
    assert "gex_regime" not in df.columns
