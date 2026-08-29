"""Synthetic OHLCV data generator.

SPEC §123 DATA POLICY: synthetic data must never be presented as real market
data. It exists solely for unit tests, pipeline tests, and prototyping the
research engine before a real, licensed dataset is wired in. Every frame
produced here carries `source="SYNTHETIC"` in its attrs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_ohlcv(
    n_days: int = 250,
    bars_per_day: int = 26,  # M15 bars in a 09:30-16:00 session
    start_date: str = "2024-01-02",
    timeframe: str = "15m",
    start_price: float = 17000.0,
    seed: int = 42,
    session_start: str = "09:30",
) -> pd.DataFrame:
    """Generate a synthetic M15 OHLCV series with alternating trend/range
    regimes and a buy/sell volume split, so downstream momentum and
    mean-reversion strategies have a non-trivial (but entirely synthetic)
    signal to discover.
    """
    rng = np.random.default_rng(seed)

    dates = pd.bdate_range(start=start_date, periods=n_days, tz="America/New_York")
    session_h, session_m = (int(x) for x in session_start.split(":"))

    rows = []
    price = start_price
    for day in dates:
        day_open = pd.Timestamp(
            year=day.year, month=day.month, day=day.day,
            hour=session_h, minute=session_m, tz="America/New_York",
        )
        # Regime: trend day (drift) vs range day (mean-reverting), chosen randomly
        is_trend_day = rng.random() < 0.4
        drift = rng.normal(0, 1) * 0.0012 if is_trend_day else 0.0
        vol = rng.uniform(0.0006, 0.0018)

        day_prices = [price]
        for _ in range(bars_per_day):
            shock = rng.normal(drift, vol)
            if not is_trend_day:
                # mean revert toward the day's opening price
                shock += (price - day_prices[0]) * -0.05 / max(price, 1)
            price = max(price * (1 + shock), 1.0)
            day_prices.append(price)

        for i in range(bars_per_day):
            o = day_prices[i]
            c = day_prices[i + 1]
            wiggle = abs(o - c) * rng.uniform(0.2, 0.8) + o * vol * rng.uniform(0.1, 0.5)
            h = max(o, c) + wiggle
            l = min(o, c) - wiggle
            base_volume = rng.lognormal(mean=7.5, sigma=0.5)
            buy_ratio = 0.5 + np.clip((c - o) / max(o * vol, 1e-9), -0.4, 0.4) * 0.3
            buy_ratio = float(np.clip(buy_ratio, 0.05, 0.95))
            volume = float(base_volume)
            rows.append(
                {
                    "timestamp": day_open + pd.Timedelta(minutes=15 * i),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": volume,
                    "buy_volume": volume * buy_ratio,
                    "sell_volume": volume * (1 - buy_ratio),
                }
            )

    df = pd.DataFrame(rows)
    df.attrs["source"] = "SYNTHETIC"
    df.attrs["symbol"] = "NQ"
    df.attrs["timeframe"] = timeframe
    return df
