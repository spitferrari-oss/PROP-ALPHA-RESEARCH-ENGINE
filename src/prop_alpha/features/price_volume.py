"""Feature engine: price, volume, volatility, VWAP, order-flow features
(spec §10). Every feature here uses only information available at bar close
at time t (no look-ahead) — enforced by only ever calling .shift/.rolling
on past-and-current data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _session_day(ts: pd.Series) -> pd.Series:
    return ts.dt.tz_convert("America/New_York").dt.date if ts.dt.tz is not None else ts.dt.date


def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["returns"] = df["close"].pct_change()
    df["log_returns"] = np.log(df["close"] / df["close"].shift(1))
    df["range"] = df["high"] - df["low"]
    df["true_range"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ),
    )
    df["atr_14"] = df["true_range"].rolling(14).mean()
    df["body"] = (df["close"] - df["open"]).abs()
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["rolling_high_20"] = df["high"].rolling(20).max()
    df["rolling_low_20"] = df["low"].rolling(20).min()
    return df


def add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["volume_z"] = (df["volume"] - df["volume"].rolling(20).mean()) / df["volume"].rolling(20).std()
    df["relative_volume"] = df["volume"] / df["volume"].rolling(20).mean()
    if "buy_volume" in df.columns and "sell_volume" in df.columns:
        df["delta"] = df["buy_volume"] - df["sell_volume"]
        df["cumulative_delta"] = df.groupby(_session_day(df["timestamp"]))["delta"].cumsum()
        df["delta_change"] = df["delta"].diff()
        df["delta_acceleration"] = df["delta_change"].diff()
    return df


def add_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["realized_vol_20"] = df["log_returns"].rolling(20).std() * np.sqrt(20)
    df["volatility_percentile"] = df["realized_vol_20"].rolling(100, min_periods=20).rank(pct=True)
    return df


def add_vwap_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    day = _session_day(df["timestamp"])
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    cum_pv = pv.groupby(day).cumsum()
    cum_vol = df["volume"].groupby(day).cumsum()
    df["vwap"] = cum_pv / cum_vol
    df["vwap_distance"] = (df["close"] - df["vwap"]) / df["vwap"]
    df["vwap_slope"] = df["vwap"].diff()
    dist_std = df["vwap_distance"].rolling(20).std()
    df["vwap_z"] = df["vwap_distance"] / dist_std
    return df


def build_feature_set(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full feature pipeline in order (spec §10)."""
    df = add_price_features(df)
    df = add_volume_features(df)
    df = add_volatility_features(df)
    df = add_vwap_features(df)
    return df
