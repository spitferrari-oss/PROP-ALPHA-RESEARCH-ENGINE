"""Recording configuration (extension spec §101): snapshot frequencies and
outcome-label horizons for the local recorder. "Questi sono valori
iniziali, non dogmi" (§101) — every field here is meant to be overridden,
not treated as fixed, so it lives in its own config class rather than
hardcoded into `data.live.session`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

DEFAULT_OUTCOME_HORIZONS = ("1m", "3m", "5m", "15m", "30m", "60m")


@dataclass(frozen=True)
class RecordingConfig:
    enabled: bool = True
    canonical_timezone: str = "UTC"
    futures_snapshot_frequency: str = "1s"
    options_snapshot_frequency: str = "provider_native"
    outcome_horizons: tuple[str, ...] = DEFAULT_OUTCOME_HORIZONS

    def to_yaml(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.safe_dump({"recording": {**asdict(self), "outcome_horizons": list(self.outcome_horizons)}}, f, sort_keys=False)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RecordingConfig":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        data = raw.get("recording", {})
        if "outcome_horizons" in data:
            data["outcome_horizons"] = tuple(data["outcome_horizons"])
        return cls(**data)
