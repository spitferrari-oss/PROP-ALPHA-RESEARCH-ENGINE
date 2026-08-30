"""Data quality thresholds (extension spec §103) — kept out of the
quality-engine module itself, following the same discipline as
`config.PaperTradingConfig`/`AgentsConfig` (spec §80/§116: never hardcode
a threshold in the module that checks against it).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StaleThresholds:
    futures_seconds: float = 3.0
    # None means "provider_defined" (extension §103's literal value for
    # options staleness — GEXBOT's own update cadence decides it, not a
    # fixed number this repo can pick ahead of Phase H).
    options_seconds: float | None = None


@dataclass(frozen=True)
class BlockedOnFlags:
    sequence_gap: bool = True
    timestamp_error: bool = True
    malformed_payload: bool = True


@dataclass(frozen=True)
class DataQualityConfig:
    minimum_score_for_research: float = 95.0
    minimum_score_for_paper: float = 97.0
    minimum_score_for_live: float = 99.0
    stale_thresholds: StaleThresholds = field(default_factory=StaleThresholds)
    blocked_on: BlockedOnFlags = field(default_factory=BlockedOnFlags)

    def minimum_score_for_stage(self, stage: str) -> float:
        mapping = {
            "research": self.minimum_score_for_research,
            "paper": self.minimum_score_for_paper,
            "live": self.minimum_score_for_live,
        }
        try:
            return mapping[stage]
        except KeyError:
            raise ValueError(f"Unknown stage '{stage}' — must be one of {list(mapping)}") from None

    def is_acceptable_for(self, score: float, stage: str) -> bool:
        return score >= self.minimum_score_for_stage(stage)
