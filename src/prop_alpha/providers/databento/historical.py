"""Databento historical adapter (extension spec §152 Phase B): the
historical two-thirds of `FuturesDataProvider` (`get_historical`,
`get_instrument_definition`, `get_trading_calendar`), backed by
Databento's `Historical` client.

`subscribe_live` (extension §152 Phase C) is deliberately not implemented
here. `DatabentoHistoricalMixin` is a plain mixin, not a `FuturesDataProvider`
subclass — it gets combined with a live-data mixin into the actual
`FuturesDataProvider` implementation only once Phase C exists, so this
phase never presents a provider with a missing live capability as if it
were complete.

Fully testable without network access or an API key (extension §134/§136):
`client` is dependency-injected — any object exposing
`.timeseries.get_range(...).to_df()` works, including a test fake. The real
`databento` package is imported lazily, only inside `_get_client`, when no
client was supplied.
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd

from prop_alpha.data.schema import OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from prop_alpha.providers.base import DataLevel, InstrumentDefinition, TradingCalendar
from prop_alpha.providers.databento.symbology import DEFAULT_SCHEMA_BY_LEVEL, resolve

DATABENTO_API_KEY_ENV = "DATABENTO_API_KEY"


def _normalize(raw_df: pd.DataFrame, schema: str, generic_symbol: str, dataset: str) -> pd.DataFrame:
    """Databento's DBN schemas index rows by `ts_event` (a tz-aware or
    nanosecond-epoch timestamp); every schema here becomes a frame with an
    explicit UTC `timestamp` column so downstream code never has to know
    whether it came from an index or a column.

    Full cross-level normalization into one canonical schema (bars vs.
    trades vs. book updates) is extension Phase D's job, not this one —
    this function only does the OHLCV case fully (aliasing straight onto
    `data/schema.py`'s `REQUIRED_COLUMNS`/`OPTIONAL_COLUMNS` so an
    `ohlcv-*` pull is a drop-in replacement for the synthetic generator's
    output); L2-L4 schemas keep their native Databento columns plus the
    normalized `timestamp`.
    """
    df = raw_df.reset_index() if raw_df.index.name in ("ts_event", "ts_recv") else raw_df.copy()
    ts_col = "ts_event" if "ts_event" in df.columns else df.columns[0]
    df["timestamp"] = pd.to_datetime(df[ts_col], utc=True)
    df = df[["timestamp"] + [c for c in df.columns if c not in ("timestamp", ts_col)]]

    if schema.startswith("ohlcv"):
        missing = [c for c in REQUIRED_COLUMNS if c != "timestamp" and c not in df.columns]
        if missing:
            raise ValueError(
                f"Databento schema '{schema}' response is missing expected column(s) {missing} "
                f"— cannot normalize into the canonical OHLCV schema."
            )
        for col in OPTIONAL_COLUMNS:
            if col not in df.columns:
                df[col] = float("nan")
        df = df[REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in df.columns]]

    df.attrs["source"] = "DATABENTO"
    df.attrs["symbol"] = generic_symbol
    df.attrs["schema"] = schema
    df.attrs["dataset"] = dataset
    return df


class DatabentoHistoricalMixin:
    name = "databento"

    def __init__(self, client=None, api_key: str | None = None):
        self._client = client
        self._api_key = api_key

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import databento
        except ImportError as exc:
            raise RuntimeError(
                "The 'databento' package is not installed (pip install "
                "'prop-alpha-engine[databento]'), and no client= was injected for testing."
            ) from exc
        api_key = self._api_key or os.environ.get(DATABENTO_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"No Databento API key: pass api_key= or set the {DATABENTO_API_KEY_ENV} "
                "environment variable. Never hardcode it in config or code (extension §25/§98)."
            )
        self._client = databento.Historical(key=api_key)
        return self._client

    def get_historical(
        self,
        instrument: str,
        start: dt.date,
        end: dt.date,
        level: DataLevel,
        schema: str | None = None,
    ) -> pd.DataFrame:
        mapping = resolve(instrument)
        resolved_schema = schema or DEFAULT_SCHEMA_BY_LEVEL[level]
        client = self._get_client()
        store = client.timeseries.get_range(
            dataset=mapping.dataset,
            symbols=[mapping.raw_symbol],
            schema=resolved_schema,
            stype_in=mapping.stype_in,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        raw_df = store.to_df()
        return _normalize(raw_df, resolved_schema, mapping.generic_symbol, mapping.dataset)

    def get_instrument_definition(self, instrument: str) -> InstrumentDefinition:
        mapping = resolve(instrument)
        return InstrumentDefinition(
            symbol=mapping.generic_symbol,
            exchange=mapping.exchange,
            asset_class=mapping.asset_class,
            currency=mapping.currency,
            tick_size=mapping.tick_size,
            point_value=mapping.point_value,
            multiplier=mapping.multiplier,
            continuous=True,
        )

    def get_trading_calendar(self, instrument: str) -> TradingCalendar:
        # Stub (extension §18 names a full exchange holiday/DST calendar as
        # its own requirement, not yet built): only the weekday check in
        # `TradingCalendar.is_trading_day` applies until a real holiday set
        # is wired in. Do not treat this as a complete calendar.
        mapping = resolve(instrument)
        return TradingCalendar(exchange=mapping.exchange, timezone=mapping.timezone)
