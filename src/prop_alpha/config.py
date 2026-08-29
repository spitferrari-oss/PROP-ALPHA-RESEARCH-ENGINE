"""Configuration schema and YAML loading (spec §80).

Critical parameters must never be hardcoded in strategy/engine code — they
flow in through validated YAML configs represented by these pydantic models.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class MarketConfig(BaseModel):
    symbol: str = "NQ"
    timeframe: str = "15m"
    tick_size: float = 0.25
    tick_value: float = 5.0
    point_value: float = 20.0


class SessionConfig(BaseModel):
    """Primary/operational session (spec §7) — the window the backtester
    treats as the trading day boundary for EOD flatten, daily P&L, etc.
    """
    name: str = "US_OPEN"
    timezone: str = "America/New_York"
    start: str = "09:30"
    end: str = "16:00"


class SessionWindowConfig(BaseModel):
    """One named window for the Session Engine (spec §7). Multiple windows
    may be active simultaneously (e.g. LONDON and US_PREMARKET overlap);
    `start`/`end` given in `timezone` wall-clock time. `start > end` is
    treated as a window that wraps past midnight (e.g. an overnight Asia
    session).
    """
    name: str
    start: str
    end: str
    timezone: str = "America/New_York"


DEFAULT_SESSION_WINDOWS: list[SessionWindowConfig] = [
    SessionWindowConfig(name="US_OPEN", start="09:30", end="11:30"),
    SessionWindowConfig(name="US_LUNCH", start="11:30", end="13:30"),
    SessionWindowConfig(name="US_POWER_HOUR", start="15:00", end="16:00"),
    SessionWindowConfig(name="US_PREMARKET", start="04:00", end="09:30"),
    SessionWindowConfig(name="LONDON", start="03:00", end="11:30"),
    SessionWindowConfig(name="FRANKFURT", start="02:00", end="03:30"),
    SessionWindowConfig(name="ASIA", start="19:00", end="03:00"),
    SessionWindowConfig(name="OVERNIGHT", start="16:00", end="19:00"),
    SessionWindowConfig(name="US_RTH", start="09:30", end="16:00"),
]


class VolumeProfileConfig(BaseModel):
    """Fixed-width price ladder for the Volume Profile engine (spec §10).
    A fixed bin size (in ticks) avoids using the day's full high/low range —
    which would only be known in hindsight — to build the price ladder.
    """
    bin_ticks: int = 10
    value_area_pct: float = 0.70
    hvn_lvn_z_threshold: float = 1.0


class RiskConfig(BaseModel):
    risk_per_trade: float = 0.005
    max_trades_day: int = 3
    daily_stop_r: float = 3.0


class CostConfig(BaseModel):
    commission_per_round_turn: float = 4.20
    slippage_ticks: float = 1.0
    spread_ticks: float = 1.0


class PropFirmConfig(BaseModel):
    name: str = "Generic Prop"
    account_size: float = 100_000.0
    profit_target: float = 8_000.0
    max_daily_loss: float = 5_000.0
    max_total_loss: float = 10_000.0
    trailing_drawdown: bool = True
    minimum_trading_days: int = 10
    payout_threshold: float = 8_000.0


class EngineConfig(BaseModel):
    market: MarketConfig = Field(default_factory=MarketConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    sessions: list[SessionWindowConfig] = Field(default_factory=lambda: list(DEFAULT_SESSION_WINDOWS))
    holidays: list[str] = Field(default_factory=list)
    half_days: dict[str, str] = Field(default_factory=dict)
    volume_profile: VolumeProfileConfig = Field(default_factory=VolumeProfileConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    prop: PropFirmConfig = Field(default_factory=PropFirmConfig)
    seed: int = 42

    @classmethod
    def from_yaml(cls, path: str | Path) -> "EngineConfig":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return cls.model_validate(raw)

    def to_yaml(self, path: str | Path) -> None:
        with open(path, "w") as f:
            yaml.safe_dump(self.model_dump(), f, sort_keys=False)
