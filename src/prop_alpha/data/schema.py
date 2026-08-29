"""Canonical OHLCV bar schema (spec §6, §10)."""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
OPTIONAL_COLUMNS = ["buy_volume", "sell_volume"]


def validate_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"DATASET_REQUIRED: missing required columns {missing}")
