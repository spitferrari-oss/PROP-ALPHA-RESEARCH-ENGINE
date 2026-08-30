"""Canonical normalization across futures data levels (extension spec §6:
"Provider -> RAW -> Normalization -> Curated -> Features"). Phase B/C's
provider adapters decode a vendor's raw payload into that vendor's own
column names; this module is where every provider's OHLCV/trade output
converges onto one shared schema, so a downstream curated/feature step
never needs to know which provider or vendor schema a row came from.
`providers.databento.historical.DatabentoHistoricalMixin` delegates its
OHLCV/trade normalization here rather than aliasing columns itself.

Only OHLCV bars (DataLevel.L1) and trade-level events (L2) get a fully
unified schema. Multi-level book data (MBP-N/MBO, L3/L4) keeps its native
provider columns plus the normalized timestamp — collapsing a variable
number of price levels into one fixed schema is a real design decision
(how many levels? padded how? which provider's level-numbering wins?)
that hasn't been made yet; this is a documented gap, not a silent guess.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.data.schema import OPTIONAL_COLUMNS, REQUIRED_COLUMNS

TRADE_COLUMNS = ["timestamp", "price", "size", "side"]


def normalize_frame(raw_df: pd.DataFrame, schema: str, timestamp_column: str = "timestamp") -> pd.DataFrame:
    """`raw_df` must already carry a timezone-aware UTC `timestamp_column`
    (provider-specific raw-column decoding, e.g. Databento's `ts_event`,
    happens in the provider adapter before this is called — extension
    §16/§17's canonical-UTC discipline is enforced here, not assumed).
    """
    if timestamp_column not in raw_df.columns:
        raise ValueError(
            f"normalize_frame: '{timestamp_column}' column not found — the provider adapter must "
            f"normalize its own raw timestamp column before calling this."
        )
    df = raw_df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_column]):
        raise ValueError(f"normalize_frame: '{timestamp_column}' must already be a datetime column.")
    if df[timestamp_column].dt.tz is None:
        raise ValueError(
            "normalize_frame: timestamps must be timezone-aware UTC (extension §16/§17) — "
            "never store core data without a timezone."
        )

    if schema.startswith("ohlcv"):
        return _normalize_bars(df)
    if schema == "trades":
        return _normalize_trades(df)
    return df  # mbp-*/mbo/etc. — see module docstring


def _normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c != "timestamp" and c not in df.columns]
    if missing:
        raise ValueError(f"normalize_frame: bar data missing expected column(s) {missing}.")
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = float("nan")
    return df[REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in df.columns]]


def _normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ("price", "size") if c not in df.columns]
    if missing:
        raise ValueError(f"normalize_frame: trade data missing expected column(s) {missing}.")
    if "side" not in df.columns:
        df["side"] = None
    extra = [c for c in df.columns if c not in TRADE_COLUMNS]
    return df[TRADE_COLUMNS + extra]
