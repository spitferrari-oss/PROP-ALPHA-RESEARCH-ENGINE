"""Mock providers (extension spec §134/§136): deterministic, in-memory,
network-free implementations of `FuturesDataProvider`/`OptionsDataProvider`
for tests and CI — no API keys, no `databento`/`requests` packages, no
real network calls.

Every real adapter in this repo (`providers.databento.*`,
`providers.gexbot.*`) already accepts an injected client/session
specifically so unit tests never need these; what was still missing is a
*shared*, importable pair of mocks that exercises the whole pipeline
end-to-end (ingest -> sync -> market state -> replay -> live shadow ->
research templates) the way a real provider would, instead of each test
file hand-rolling its own narrow local fake. Everything these mocks
produce is clearly synthetic, seeded, and reproducible — never presented
as real market data (the same discipline `data.synthetic.
generate_synthetic_ohlcv` and `paper.shadow`'s docstring already commit
to elsewhere in this repo).

The options mock deliberately routes through the *real* GEXBOT parsing
pipeline (`options.gexbot.parser.parse_snapshot`, `options.normalize.
normalize_gex_snapshot`, `options.levels.extract_levels`) rather than
building `OptionsSnapshot` objects directly — so an integration test using
this mock exercises the same parsing/normalization code a real GEXBOT
payload would go through, not a parallel path that could silently drift
from it. `get_orderflow` still raises `NotImplementedError`, mirroring
`GexbotOptionsProvider`'s own honesty: order-flow parsing isn't built
anywhere in this repo (extension §34), so the mock doesn't fabricate data
for a feature that doesn't exist.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict

import numpy as np
import pandas as pd

from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.options.gexbot.parser import parse_snapshot
from prop_alpha.options.levels import extract_levels
from prop_alpha.options.models import AvailabilityStatus, OptionsSnapshot
from prop_alpha.options.normalize import normalize_gex_snapshot
from prop_alpha.providers.base import (
    FuturesDataProvider,
    InstrumentDefinition,
    LiveSubscriptionHandle,
    OptionsDataProvider,
    TradingCalendar,
)


class _ImmediateHandle:
    """`subscribe_live` on both mocks pushes a deterministic, finite burst
    of messages synchronously (no background thread, no real streaming —
    a mock exists to be fast and deterministic in CI, not to simulate
    real-time timing), so by the time a caller has this handle, delivery
    is already finished — `is_active` is `False` from the start and
    `close()` is a no-op.
    """

    @property
    def is_active(self) -> bool:
        return False

    def close(self) -> None:
        return None


class MockFuturesDataProvider(FuturesDataProvider):
    name = "mock"

    def __init__(
        self,
        seed: int = 42,
        tick_size: float = 0.25,
        point_value: float = 20.0,
        exchange: str = "CME",
        timezone: str = "America/New_York",
    ):
        self._seed = seed
        self._tick_size = tick_size
        self._point_value = point_value
        self._exchange = exchange
        self._timezone = timezone

    def get_historical(self, instrument, start, end, level, schema=None) -> pd.DataFrame:
        n_bdays = max(len(pd.bdate_range(start=start, end=end)), 1)
        df = generate_synthetic_ohlcv(n_days=n_bdays, start_date=start.isoformat(), seed=self._seed)
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
        mask = (df["timestamp"].dt.date >= start) & (df["timestamp"].dt.date <= end)
        return df.loc[mask].reset_index(drop=True)

    def subscribe_live(self, instrument, level, on_message) -> LiveSubscriptionHandle:
        # A real wire payload's timestamp field is a string or epoch number,
        # never a live Python/pandas datetime object -- isoformat() here
        # matches that rather than leaking a pandas Timestamp downstream.
        df = generate_synthetic_ohlcv(n_days=1, bars_per_day=5, seed=self._seed)
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
        for _, row in df.iterrows():
            payload = row.to_dict()
            payload["timestamp"] = payload["timestamp"].isoformat()
            on_message(payload)
        return _ImmediateHandle()

    def get_instrument_definition(self, instrument: str) -> InstrumentDefinition:
        return InstrumentDefinition(
            symbol=instrument, exchange=self._exchange, asset_class="FUTURE", currency="USD",
            tick_size=self._tick_size, point_value=self._point_value,
        )

    def get_trading_calendar(self, instrument: str) -> TradingCalendar:
        return TradingCalendar(exchange=self._exchange, timezone=self._timezone)


class MockOptionsDataProvider(OptionsDataProvider):
    name = "mock"

    def __init__(self, seed: int = 42, stale_after_seconds: float = 60.0):
        self._seed = seed
        self._stale_after_seconds = stale_after_seconds

    def _raw_snapshot(self, underlying: str, index: int = 0, timestamp: dt.datetime | None = None) -> dict:
        rng = np.random.default_rng(self._seed + index)
        timestamp = timestamp or dt.datetime.now(dt.timezone.utc)
        spot = 4500.0 + float(rng.normal(0, 10))
        return {
            "timestamp": timestamp.isoformat(),
            "spot": spot,
            "gex": float(rng.normal(0, 1)) * 1e9,
            "dex": float(rng.normal(0, 1)) * 1e8,
            "gamma_flip": spot + float(rng.normal(0, 5)),
            "major_positive_gamma": spot + 20.0,
            "major_negative_gamma": spot - 20.0,
            "vanna": float(rng.normal(0, 1)) * 1e6,
            "charm": float(rng.normal(0, 1)) * 1e6,
            "vomma": float(rng.normal(0, 1)) * 1e6,
            "skew": float(rng.normal(0, 0.1)),
            "options_volume": abs(float(rng.normal(100_000, 20_000))),
            "open_interest": abs(float(rng.normal(500_000, 50_000))),
        }

    def get_historical(self, underlying, start, end, metrics=None) -> pd.DataFrame:
        days = pd.bdate_range(start=start, end=end)
        rows = [
            self._raw_snapshot(underlying, index=i, timestamp=pd.Timestamp(day, tz="UTC").to_pydatetime())
            for i, day in enumerate(days)
        ]
        df = pd.DataFrame(rows)
        if metrics:
            keep = ["timestamp"] + [m for m in metrics if m in df.columns]
            df = df[keep]
        return df

    def get_snapshot(self, underlying: str) -> dict:
        raw = self._raw_snapshot(underlying)
        gex_snapshot = parse_snapshot(raw, underlying, stale_after_seconds=self._stale_after_seconds)
        return asdict(normalize_gex_snapshot(gex_snapshot))

    def subscribe_live(self, underlying, on_message) -> LiveSubscriptionHandle:
        on_message(self.get_snapshot(underlying))
        return _ImmediateHandle()

    def get_levels(self, underlying: str) -> list[dict]:
        raw = self._raw_snapshot(underlying)
        gex_snapshot = parse_snapshot(raw, underlying, stale_after_seconds=self._stale_after_seconds)
        snapshot = normalize_gex_snapshot(gex_snapshot)
        return [asdict(level) for level in extract_levels(snapshot, source=self.name)]

    def get_orderflow(self, underlying: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        raise NotImplementedError(
            "Options order flow parsing is not built anywhere in this repo yet (extension §34) — "
            "the mock provider stays honest about that rather than fabricating data for a feature "
            "that doesn't exist, mirroring GexbotOptionsProvider.get_orderflow's own limitation."
        )

    def get_instrument_state(self, underlying: str) -> dict:
        snapshot_dict = self.get_snapshot(underlying)
        available = [
            name for name, value in snapshot_dict.items()
            if isinstance(value, dict) and value.get("availability", {}).get("status")
            in (AvailabilityStatus.AVAILABLE.value, AvailabilityStatus.STALE.value)
        ]
        return {"underlying": underlying, "available_metrics": available}

    def generate_snapshot_sequence(
        self, underlying: str, start_timestamp: dt.datetime, n: int, interval_seconds: float = 60.0,
    ) -> list[OptionsSnapshot]:
        """Not part of the `OptionsDataProvider` ABC — a convenience for
        integration tests that need a real, time-ordered sequence of
        `OptionsSnapshot` objects (e.g. to feed `sync.cross_market.
        synchronize_frame`) built through the same real parse/normalize
        pipeline `get_snapshot` uses, not a parallel shortcut.
        """
        snapshots = []
        for i in range(n):
            timestamp = start_timestamp + dt.timedelta(seconds=interval_seconds * i)
            raw = self._raw_snapshot(underlying, index=i, timestamp=timestamp)
            gex_snapshot = parse_snapshot(
                raw, underlying, received_at=timestamp, stale_after_seconds=self._stale_after_seconds,
            )
            snapshots.append(normalize_gex_snapshot(gex_snapshot, timestamp=timestamp))
        return snapshots
