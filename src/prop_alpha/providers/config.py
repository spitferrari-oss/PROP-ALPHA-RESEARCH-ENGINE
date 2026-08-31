"""Provider configuration loader (hardening pass Step 19-20). Kept
separate from `config.EngineConfig` (core strategy/backtest parameters) —
`config/providers.yaml` is infrastructure configuration: which vendor to
talk to and how, never a research parameter, and never a secret (API
keys stay in environment variables, see `.env.example`).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_PROVIDERS_CONFIG_PATH = Path("config/providers.yaml")


class DatabentoProviderConfig(BaseModel):
    enabled: bool = False


class GexbotProviderConfig(BaseModel):
    enabled: bool = False
    base_url: str = "https://api.gexbot.com"
    underlyings: list[str] = Field(default_factory=lambda: ["SPX", "SPY", "QQQ", "NDX"])
    poll_interval_seconds: float = 5.0
    stale_after_seconds: float = 60.0


class ProvidersConfig(BaseModel):
    databento: DatabentoProviderConfig = Field(default_factory=DatabentoProviderConfig)
    gexbot: GexbotProviderConfig = Field(default_factory=GexbotProviderConfig)

    @classmethod
    def from_yaml(cls, path: str | Path = DEFAULT_PROVIDERS_CONFIG_PATH) -> "ProvidersConfig":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return cls.model_validate(raw)
