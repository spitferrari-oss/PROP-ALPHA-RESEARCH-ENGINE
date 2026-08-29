"""Prop account dynamic state (spec §35)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccountState:
    balance: float
    equity: float
    high_watermark: float
    daily_start_balance: float
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    trading_days: int = 0

    @property
    def distance_to_daily_breach(self) -> float:
        return self.daily_pnl

    @property
    def distance_to_trailing_breach(self) -> float:
        return self.balance - self.high_watermark
