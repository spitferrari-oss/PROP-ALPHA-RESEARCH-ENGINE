"""Volume Profile feature engine (spec §10): POC, VAH, VAL, HVN/LVN counts,
profile width, developing (intraday) values, and prior-day levels.

The price ladder uses a *fixed* bin size (tick_size * bin_ticks), not the
day's realized high/low range — using the full-day range to build bin edges
would leak end-of-day information into bins computed intraday. Each bar's
volume is split evenly across every bin its [low, high] range touches, and
profiles accumulate bar-by-bar within a session so every value is a genuine
"as of this bar" snapshot (no look-ahead) except the `vp_prior_*` columns,
which are deliberately the *previous* completed day's finalized profile.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _distribute_volume(low: float, high: float, volume: float, bin_size: float) -> dict[float, float]:
    lo_bin = int(np.floor(low / bin_size))
    hi_bin = int(np.floor(high / bin_size))
    if hi_bin < lo_bin:
        hi_bin = lo_bin
    n_bins = hi_bin - lo_bin + 1
    vol_per_bin = volume / n_bins
    return {(lo_bin + i) * bin_size + bin_size / 2: vol_per_bin for i in range(n_bins)}


def _summarize_profile(profile: dict[float, float], value_area_pct: float) -> tuple[float | None, float | None, float | None]:
    if not profile:
        return None, None, None
    prices = np.array(sorted(profile.keys()))
    vols = np.array([profile[p] for p in prices])

    poc_idx = int(np.argmax(vols))
    poc = float(prices[poc_idx])

    total = float(vols.sum())
    target = total * value_area_pct
    lo_idx = hi_idx = poc_idx
    covered = float(vols[poc_idx])
    while covered < target and (lo_idx > 0 or hi_idx < len(prices) - 1):
        vol_below = vols[lo_idx - 1] if lo_idx > 0 else -1.0
        vol_above = vols[hi_idx + 1] if hi_idx < len(prices) - 1 else -1.0
        if vol_below >= vol_above:
            lo_idx -= 1
            covered += vols[lo_idx]
        else:
            hi_idx += 1
            covered += vols[hi_idx]

    return poc, float(prices[hi_idx]), float(prices[lo_idx])


def _hvn_lvn_counts(profile: dict[float, float], z_threshold: float) -> tuple[int, int]:
    if len(profile) < 3:
        return 0, 0
    vols = np.array(list(profile.values()))
    std = vols.std()
    if std == 0:
        return 0, 0
    z = (vols - vols.mean()) / std
    return int((z > z_threshold).sum()), int((z < -z_threshold).sum())


def add_volume_profile_features(
    df: pd.DataFrame,
    tick_size: float = 0.25,
    bin_ticks: int = 10,
    value_area_pct: float = 0.70,
    hvn_lvn_z_threshold: float = 1.0,
    session_timezone: str = "America/New_York",
) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    bin_size = bin_ticks * tick_size
    day = df["timestamp"].dt.tz_convert(session_timezone).dt.date.to_numpy()

    n = len(df)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    width = np.full(n, np.nan)
    hvn = np.full(n, np.nan)
    lvn = np.full(n, np.nan)
    prior_poc = np.full(n, np.nan)
    prior_vah = np.full(n, np.nan)
    prior_val = np.full(n, np.nan)

    current_day = None
    running_profile: dict[float, float] = {}
    prior_summary: tuple[float, float, float] | None = None

    lows = df["low"].to_numpy()
    highs = df["high"].to_numpy()
    volumes = df["volume"].to_numpy()

    for i in range(n):
        if day[i] != current_day:
            if current_day is not None and running_profile:
                p, h, l = _summarize_profile(running_profile, value_area_pct)
                if p is not None:
                    prior_summary = (p, h, l)
            current_day = day[i]
            running_profile = {}

        bar_profile = _distribute_volume(lows[i], highs[i], volumes[i], bin_size)
        for price, vol in bar_profile.items():
            running_profile[price] = running_profile.get(price, 0.0) + vol

        p, h, l = _summarize_profile(running_profile, value_area_pct)
        poc[i], vah[i], val[i] = p, h, l
        width[i] = (h - l) if (h is not None and l is not None) else np.nan
        hvn[i], lvn[i] = _hvn_lvn_counts(running_profile, hvn_lvn_z_threshold)

        if prior_summary is not None:
            prior_poc[i], prior_vah[i], prior_val[i] = prior_summary

    df["vp_poc"] = poc
    df["vp_vah"] = vah
    df["vp_val"] = val
    df["vp_width"] = width
    df["vp_hvn_count"] = hvn
    df["vp_lvn_count"] = lvn
    df["vp_prior_poc"] = prior_poc
    df["vp_prior_vah"] = prior_vah
    df["vp_prior_val"] = prior_val
    df["vp_dist_to_prior_poc"] = df["close"] - df["vp_prior_poc"]
    df["vp_dist_to_prior_vah"] = df["close"] - df["vp_prior_vah"]
    df["vp_dist_to_prior_val"] = df["close"] - df["vp_prior_val"]
    return df
