"""Full feature pipeline: price/volume/volatility/VWAP -> volume profile ->
session annotation (spec §10 Feature Engine, §7 Session Engine).
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.config import EngineConfig
from prop_alpha.features.price_volume import build_feature_set
from prop_alpha.features.volume_profile import add_volume_profile_features
from prop_alpha.sessions.engine import SessionEngine


def build_full_feature_set(df: pd.DataFrame, config: EngineConfig) -> pd.DataFrame:
    df = build_feature_set(df)
    df = add_volume_profile_features(
        df,
        tick_size=config.market.tick_size,
        bin_ticks=config.volume_profile.bin_ticks,
        value_area_pct=config.volume_profile.value_area_pct,
        hvn_lvn_z_threshold=config.volume_profile.hvn_lvn_z_threshold,
        session_timezone=config.session.timezone,
    )
    session_engine = SessionEngine.from_config(config)
    df = session_engine.annotate(df)
    return df
