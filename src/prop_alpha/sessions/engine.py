"""Session Engine (spec §7): an independent module for sessions and market
hours, decoupled from feature/strategy code so a window can be redefined in
config without touching either.

Supports arbitrary named windows (each with its own timezone), windows that
wrap past midnight (e.g. an overnight Asia session), a holiday calendar, and
per-date half-day close overrides.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from prop_alpha.config import EngineConfig, SessionWindowConfig


def _parse_hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(hour=int(h), minute=int(m))


@dataclass
class SessionWindow:
    name: str
    start: str
    end: str
    timezone: str = "America/New_York"

    @property
    def start_time(self) -> dt.time:
        return _parse_hhmm(self.start)

    @property
    def end_time(self) -> dt.time:
        return _parse_hhmm(self.end)

    @property
    def wraps_midnight(self) -> bool:
        return self.start_time > self.end_time


class SessionEngine:
    def __init__(
        self,
        windows: list[SessionWindow],
        holidays: list[str] | None = None,
        half_days: dict[str, str] | None = None,
        calendar_timezone: str = "America/New_York",
    ):
        self.windows = windows
        self.holidays = {pd.Timestamp(d).date() for d in (holidays or [])}
        self.half_days = {pd.Timestamp(d).date(): t for d, t in (half_days or {}).items()}
        self.calendar_timezone = calendar_timezone

    @classmethod
    def from_config(cls, config: EngineConfig) -> "SessionEngine":
        windows = [
            SessionWindow(name=w.name, start=w.start, end=w.end, timezone=w.timezone)
            for w in config.sessions
        ]
        return cls(
            windows=windows,
            holidays=config.holidays,
            half_days=config.half_days,
            calendar_timezone=config.session.timezone,
        )

    def is_holiday(self, ts: pd.Timestamp) -> bool:
        local_date = ts.tz_convert(self.calendar_timezone).date()
        return local_date in self.holidays

    def is_trading_day(self, ts: pd.Timestamp) -> bool:
        local = ts.tz_convert(self.calendar_timezone)
        return local.weekday() < 5 and not self.is_holiday(ts)

    def _effective_end_time(self, window: SessionWindow, local_date: dt.date) -> dt.time:
        if window.timezone != self.calendar_timezone:
            return window.end_time
        override = self.half_days.get(local_date)
        if override is None:
            return window.end_time
        override_time = _parse_hhmm(override)
        return min(window.end_time, override_time)

    def active_windows(self, ts: pd.Timestamp) -> list[str]:
        active = []
        for w in self.windows:
            local = ts.tz_convert(w.timezone)
            t = local.time()
            start_t = w.start_time
            end_t = self._effective_end_time(w, local.date())
            if start_t <= end_t:
                is_active = start_t <= t < end_t
            else:
                is_active = t >= start_t or t < end_t
            if is_active:
                active.append(w.name)
        return active

    def primary_session(self, ts: pd.Timestamp) -> str:
        active = self.active_windows(ts)
        return active[0] if active else "NONE"

    def minutes_since_open(self, ts: pd.Timestamp, window_name: str) -> float | None:
        window = next((w for w in self.windows if w.name == window_name), None)
        if window is None:
            return None
        local = ts.tz_convert(window.timezone)
        start_dt = local.replace(
            hour=window.start_time.hour, minute=window.start_time.minute, second=0, microsecond=0
        )
        if window.wraps_midnight and local.time() < window.start_time:
            start_dt -= pd.Timedelta(days=1)
        return (local - start_dt).total_seconds() / 60.0

    def annotate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach session columns using only each bar's own timestamp — no
        look-ahead is possible since these are pure calendar computations.
        """
        df = df.copy()
        ts = df["timestamp"]
        active_lists = ts.apply(self.active_windows)

        for w in self.windows:
            df[f"in_session_{w.name.lower()}"] = active_lists.apply(lambda active, n=w.name: n in active)

        df["session"] = active_lists.apply(lambda active: active[0] if active else "NONE")
        df["minutes_since_session_open"] = [
            self.minutes_since_open(t, s) if s != "NONE" else np.nan
            for t, s in zip(ts, df["session"])
        ]
        df["is_holiday"] = ts.apply(self.is_holiday)
        df["is_trading_day"] = ts.apply(self.is_trading_day)
        return df
