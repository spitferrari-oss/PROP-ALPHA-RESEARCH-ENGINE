"""GEXBOT adapter (extension spec §3, §23-27, options data provider,
Phase H + I).

`options.gexbot.*` holds the GEXBOT-specific client/auth/parsing/model/
health layer; `options.normalize`/`options.levels` (Phase I) hold the
vendor-agnostic snapshot/level conversion. `GexbotOptionsProvider` below
composes all of it into the `OptionsDataProvider` interface (extension
§2) — the core PARE engine imports only this class, never
`options.gexbot`/`options.normalize`/`options.levels` directly.

Scope discipline (extension §3: prepare the architecture, don't write
code nobody can use yet): `get_historical` and `get_orderflow` still
raise `NotImplementedError` with an explanation — historical retention on
GEXBOT's own API is provider-limited (extension §62, "GEXBOT HISTORICAL
LIMITATION HANDLING"), and order-flow parsing is the options feature
engine's job (Phase K, §34), not built yet. `get_levels` now works
(Phase I's Options Level Engine, §29) but only for the level types a
snapshot alone can produce (`GAMMA_FLIP`/`MAJOR_GAMMA`, with a spot-price
distance and no strength score yet) — `DEX_LEVEL`/`VANNA_LEVEL`/
`CHARM_LEVEL` and the ATR-normalized distance extension §30 wants remain
Phase K's job.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict

import pandas as pd

from prop_alpha.options.gexbot.client import GexbotClient
from prop_alpha.options.gexbot.parser import parse_snapshot
from prop_alpha.options.levels import extract_levels
from prop_alpha.options.models import AvailabilityStatus
from prop_alpha.options.normalize import normalize_gex_snapshot
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

    def _fetch_snapshot(self, underlying: str):
        raw = self._client.get_gex(underlying)
        gex_snapshot = parse_snapshot(raw, underlying, stale_after_seconds=self._stale_after_seconds)
        return normalize_gex_snapshot(gex_snapshot)

    def get_historical(
        self, underlying: str, start: dt.date, end: dt.date, metrics: list[str] | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "GEXBOT historical options data is not built in Phase H/I — GEXBOT's own historical "
            "retention is provider-limited (extension §62); PARE's proprietary options history "
            "only starts accumulating once live recording begins (a Phase F-style collector.py "
            "for options, not yet built)."
        )

    def get_snapshot(self, underlying: str) -> dict:
        return asdict(self._fetch_snapshot(underlying))

    def subscribe_live(self, underlying: str, on_message) -> LiveSubscriptionHandle:
        return self._client.start_polling(underlying, self._poll_interval_seconds, on_message)

    def get_levels(self, underlying: str) -> list[dict]:
        snapshot = self._fetch_snapshot(underlying)
        return [asdict(level) for level in extract_levels(snapshot, source=self.name)]

    def get_orderflow(self, underlying: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        raise NotImplementedError(
            "Options order flow parsing/history is Phase K's job (extension §34), not this "
            "adapter's — client.get_orderflow() returns raw GEXBOT JSON only so far."
        )

    def get_instrument_state(self, underlying: str) -> dict:
        snapshot = self._fetch_snapshot(underlying)
        available = [
            name for name, value in asdict(snapshot).items()
            if isinstance(value, dict) and value.get("availability", {}).get("status")
            in (AvailabilityStatus.AVAILABLE.value, AvailabilityStatus.STALE.value)
        ]
        return {"underlying": underlying, "available_metrics": available}
