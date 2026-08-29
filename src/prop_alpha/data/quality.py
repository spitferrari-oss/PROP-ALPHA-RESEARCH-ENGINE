"""Data quality engine (spec §2 DATA QUALITY, §28 leakage guardrails subset).

Raises on structural problems rather than silently repairing data, so a bad
dataset fails loudly instead of poisoning downstream research.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from prop_alpha.data.schema import validate_columns


@dataclass
class QualityReport:
    n_rows: int
    n_duplicate_timestamps: int
    n_non_monotonic: int
    n_nan: int
    n_negative_price: int
    n_negative_volume: int
    n_zero_range_violations: int
    issues: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.issues) == 0


def validate_ohlcv(df: pd.DataFrame) -> QualityReport:
    validate_columns(df)

    issues: list[str] = []

    n_dupes = int(df["timestamp"].duplicated().sum())
    if n_dupes:
        issues.append(f"{n_dupes} duplicate timestamps")

    ts = df["timestamp"]
    n_non_monotonic = int((ts.diff().dropna() <= pd.Timedelta(0)).sum())
    if n_non_monotonic:
        issues.append(f"{n_non_monotonic} non-monotonic timestamp steps")

    n_nan = int(df[["open", "high", "low", "close", "volume"]].isna().sum().sum())
    if n_nan:
        issues.append(f"{n_nan} NaN values in OHLCV columns")

    n_neg_price = int((df[["open", "high", "low", "close"]] <= 0).sum().sum())
    if n_neg_price:
        issues.append(f"{n_neg_price} non-positive price values")

    n_neg_vol = int((df["volume"] < 0).sum())
    if n_neg_vol:
        issues.append(f"{n_neg_vol} negative volume values")

    bad_range = ((df["high"] < df["low"]) | (df["high"] < df["open"]) | (df["high"] < df["close"]) |
                 (df["low"] > df["open"]) | (df["low"] > df["close"]))
    n_range = int(bad_range.sum())
    if n_range:
        issues.append(f"{n_range} bars where high/low do not bound open/close")

    return QualityReport(
        n_rows=len(df),
        n_duplicate_timestamps=n_dupes,
        n_non_monotonic=n_non_monotonic,
        n_nan=n_nan,
        n_negative_price=n_neg_price,
        n_negative_volume=n_neg_vol,
        n_zero_range_violations=n_range,
        issues=issues,
    )
