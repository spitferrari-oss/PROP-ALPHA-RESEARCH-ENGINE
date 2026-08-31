"""GEXBOT adapter (extension spec §3, §23-27, options data provider,
Phase H).

`options.gexbot.*` holds the actual client/auth/parsing/model/health
layer; `GexbotOptionsProvider` below composes it into the
`OptionsDataProvider` interface (extension §2) — the core PARE engine
imports only this class, never `options.gexbot` directly.

Scope discipline (extension §3: prepare the architecture, don't write
code nobody can use yet): `get_historical`, `get_levels`, and
`get_orderflow` raise `NotImplementedError` with an explanation rather
than fabricating a result — historical retention on GEXBOT's own API is
provider-limited (extension §62, "GEXBOT HISTORICAL LIMITATION HANDLING"),
and level/order-flow *parsing* is the Options Level Engine and options
feature engine's job (Phase K, §29-34), not this adapter's.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict

import pandas as pd

from prop_alpha.options.gexbot.client import GexbotClient
from prop_alpha.options.gexbot.models import AvailabilityStatus
from prop_alpha.options.gexbot.parser import parse_snapshot
from prop_alpha.providers.base import LiveSubscriptionHandle, OptionsDataProvider


class GexbotOptionsProvider(OptionsDataProvider):
    name = "gexbot"

    def __init__(
        self,
        client: GexbotClient | None = None,
        api_key: str | None = None,
        poll_interval_seconds: float = 5.0,
        stale_after_seconds: float = 60.0,
    ):
        self._client = client or GexbotClient(api_key=api_key)
        self._poll_interval_seconds = poll_interval_seconds
        self._stale_after_seconds = stale_after_seconds

    def get_historical(
        self, underlying: str, start: dt.date, end: dt.date, metrics: list[str] | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "GEXBOT historical options data is not built in Phase H — GEXBOT's own historical "
            "retention is provider-limited (extension §62); PARE's proprietary options history "
            "only starts accumulating once live recording begins (a Phase F-style collector.py "
            "for options, not yet built)."
        )

    def get_snapshot(self, underlying: str) -> dict:
        raw = self._client.get_gex(underlying)
        snapshot = parse_snapshot(raw, underlying, stale_after_seconds=self._stale_after_seconds)
        return asdict(snapshot)

    def subscribe_live(self, underlying: str, on_message) -> LiveSubscriptionHandle:
        return self._client.start_polling(underlying, self._poll_interval_seconds, on_message)

    def get_levels(self, underlying: str) -> list[dict]:
        raise NotImplementedError(
            "Parsing raw GEXBOT levels into Options Level objects is the Options Level Engine's "
            "job (Phase K, extension §29), not this adapter's — client.get_levels() returns raw "
            "GEXBOT JSON only so far."
        )

    def get_orderflow(self, underlying: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        raise NotImplementedError(
            "Options order flow parsing/history is Phase K's job (extension §34), not this "
            "adapter's — client.get_orderflow() returns raw GEXBOT JSON only so far."
        )

    def get_instrument_state(self, underlying: str) -> dict:
        raw = self._client.get_gex(underlying)
        snapshot = parse_snapshot(raw, underlying, stale_after_seconds=self._stale_after_seconds)
        available = [
            name for name, value in asdict(snapshot).items()
            if isinstance(value, dict) and value.get("availability", {}).get("status")
            in (AvailabilityStatus.AVAILABLE.value, AvailabilityStatus.STALE.value)
        ]
        return {"underlying": underlying, "available_metrics": available}
