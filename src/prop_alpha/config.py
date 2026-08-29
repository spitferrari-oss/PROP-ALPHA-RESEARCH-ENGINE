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
    name: str = "US_OPEN"
    timezone: str = "America/New_York"
    start: str = "09:30"
    end: str = "16:00"


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
