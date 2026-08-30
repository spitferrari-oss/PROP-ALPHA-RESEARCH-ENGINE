"""Provider interfaces (extension spec §2, §5): the contract every futures
or options data source must satisfy. This module fixes the *shape* of the
contract only — no vendor logic, no network calls, no concrete adapter.
Concrete implementations (`providers.databento.*`, `providers.gexbot.*`)
are later extension phases (§152 Phase B/C/H); tests here use a minimal
in-file stub to prove the ABCs are well-formed, not a real provider.

`get_snapshot`/`get_levels`/`get_instrument_state` on `OptionsDataProvider`
return plain `dict`s in this phase — the extension formalizes them into a
proper `OptionsSnapshot`/`OptionsLevel` model in Phase I/K (§28-29), once
there's a concrete provider's actual field set to model against. Fixing
that shape now, before GEXBOT is wired in, would be guessing at a schema
the spec explicitly warns against assuming ("Non assumere che ogni metrica
sia disponibile con la stessa frequenza o sullo stesso endpoint," §26).
"""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol, runtime_checkable

import pandas as pd

_LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}


class DataLevel(str, Enum):
    """Futures market data granularity (extension spec §5). Every alpha
    declares the minimum level it needs (`alpha_requirements.<id>.minimum_data_level`
    in config); a provider/instrument/schema combination that can't serve
    at least that level makes the alpha ineligible (§75, §123 Alpha
    Eligibility Matrix — built in a later phase, this enum is its unit of
    comparison).
    """
    L1 = "L1"  # OHLCV
    L2 = "L2"  # trades, bid/ask, trade direction, volume, delta-capable info
    L3 = "L3"  # market depth, multi-level book (MBP)
    L4 = "L4"  # MBO / full order book, queue-level information

    def satisfies(self, minimum: "DataLevel") -> bool:
        """True if this level is at least as rich as `minimum` — e.g. an
        L3 feed satisfies an alpha that only requires L2.
        """
        return _LEVEL_ORDER[self.value] >= _LEVEL_ORDER[minimum.value]


@dataclass(frozen=True)
class InstrumentDefinition:
    """Vendor-agnostic instrument metadata — every futures provider's
    `get_instrument_definition` must return one of these, not a raw vendor
    payload, so `cli.py`/`config.py` never need to know which provider
    supplied it.
    """
    symbol: str
    exchange: str
    asset_class: str
    currency: str
    tick_size: float
    point_value: float
    multiplier: float = 1.0
    continuous: bool = True
    expiry: dt.date | None = None


@dataclass(frozen=True)
class TradingCalendar:
    """Per-instrument trading calendar (extension spec §18): not every
    instrument follows the same holiday/DST/early-close calendar, so this
    is requested per-instrument from the provider, not assumed globally.
    """
    exchange: str
    timezone: str
    holidays: frozenset[dt.date] = field(default_factory=frozenset)
    early_closes: dict[dt.date, dt.time] = field(default_factory=dict)

    def is_trading_day(self, day: dt.date) -> bool:
        return day.weekday() < 5 and day not in self.holidays


@runtime_checkable
class LiveSubscriptionHandle(Protocol):
    """Returned by `subscribe_live`; the caller owns closing it. Concrete
    adapters (Phase C) back this with a real connection — this phase only
    fixes what a caller can rely on regardless of vendor.
    """
    @property
    def is_active(self) -> bool: ...

    def close(self) -> None: ...


class FuturesDataProvider(ABC):
    """extension spec §2: futures market data provider interface. The PARE
    core imports only this ABC, never Databento (or any other vendor SDK)
    directly.
    """
    name: str

    @abstractmethod
    def get_historical(
        self,
        instrument: str,
        start: dt.date,
        end: dt.date,
        level: DataLevel,
        schema: str | None = None,
    ) -> pd.DataFrame:
        """Returns bars/trades covering `[start, end]` at least at `level`
        (raises if this provider/instrument can't serve that level). The
        returned frame's schema is normalized (see `data/schema.py`), not
        the vendor's raw wire format — normalization is the provider
        adapter's job, not something downstream code repeats per provider.
        """

    @abstractmethod
    def subscribe_live(
        self,
        instrument: str,
        level: DataLevel,
        on_message: Callable[[dict], None],
    ) -> LiveSubscriptionHandle:
        """Streams live messages to `on_message`. Each message carries the
        provider's payload plus the timestamp fields the extension's
        timestamp policy (§15) requires — normalization into feature-ready
        rows happens downstream (`data/live/event_router.py`, a later
        phase), not inside the provider adapter.
        """

    @abstractmethod
    def get_instrument_definition(self, instrument: str) -> InstrumentDefinition:
        """Vendor-agnostic contract metadata — see `InstrumentDefinition`."""

    @abstractmethod
    def get_trading_calendar(self, instrument: str) -> TradingCalendar:
        """Per-instrument calendar — see `TradingCalendar`."""


class OptionsDataProvider(ABC):
    """extension spec §2: options data provider interface (e.g. GEXBOT).
    The function of an options provider in PARE is state/context
    information, never a direct trading signal (§23, §37-38) — that
    constraint belongs to how callers use this interface, not to the
    interface's shape.
    """
    name: str

    @abstractmethod
    def get_historical(
        self,
        underlying: str,
        start: dt.date,
        end: dt.date,
        metrics: list[str] | None = None,
    ) -> pd.DataFrame:
        """Historical options-state metrics for `underlying` over
        `[start, end]`. `metrics=None` means "whatever this provider can
        serve" — callers must not assume every metric is available at
        every point in that range (§26).
        """

    @abstractmethod
    def get_snapshot(self, underlying: str) -> dict:
        """The current options state for `underlying`. Returns a plain
        dict in this phase (see module docstring) — a metric this provider
        cannot currently serve must be absent or `None`, never silently
        replaced with `0` (§51-52: zero and missing are never the same
        thing)."""

    @abstractmethod
    def subscribe_live(
        self,
        underlying: str,
        on_message: Callable[[dict], None],
    ) -> LiveSubscriptionHandle:
        """Streams live options-state updates to `on_message`."""

    @abstractmethod
    def get_levels(self, underlying: str) -> list[dict]:
        """Currently-relevant options levels (gamma flip, major gamma,
        etc. — see extension §29) for `underlying`."""

    @abstractmethod
    def get_orderflow(self, underlying: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        """Options order flow for `underlying` over `[start, end]`, when
        the provider's plan/API exposes it (extension §34)."""

    @abstractmethod
    def get_instrument_state(self, underlying: str) -> dict:
        """Provider-reported state for `underlying` beyond the snapshot
        metrics themselves (e.g. which metrics are currently available) —
        distinct from `get_snapshot`'s market data."""
