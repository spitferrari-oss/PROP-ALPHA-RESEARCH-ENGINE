"""Realistic execution cost model (spec §22, §23, §24)."""
from __future__ import annotations

from dataclasses import dataclass

COST_PROFILES = {
    "optimistic": {"slippage_mult": 0.0, "spread_mult": 0.5},
    "base": {"slippage_mult": 1.0, "spread_mult": 1.0},
    "conservative": {"slippage_mult": 2.0, "spread_mult": 1.5},
    "stress": {"slippage_mult": 4.0, "spread_mult": 2.0},
    "extreme": {"slippage_mult": 8.0, "spread_mult": 3.0},
}


@dataclass
class CostModel:
    tick_size: float
    tick_value: float
    commission_per_round_turn: float
    slippage_ticks: float
    spread_ticks: float

    def scaled(self, profile: str = "base") -> "CostModel":
        mult = COST_PROFILES[profile]
        return CostModel(
            tick_size=self.tick_size,
            tick_value=self.tick_value,
            commission_per_round_turn=self.commission_per_round_turn,
            slippage_ticks=self.slippage_ticks * mult["slippage_mult"],
            spread_ticks=self.spread_ticks * mult["spread_mult"],
        )

    def entry_slippage_price(self) -> float:
        return (self.slippage_ticks + self.spread_ticks / 2) * self.tick_size

    def exit_slippage_price(self) -> float:
        return (self.slippage_ticks + self.spread_ticks / 2) * self.tick_size

    def commission_dollars(self) -> float:
        return self.commission_per_round_turn
