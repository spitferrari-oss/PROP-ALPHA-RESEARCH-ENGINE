"""Hypothesis Ledger (spec §20): "Non deve essere consentito creare un
backtest senza registrare almeno: ipotesi; data della formulazione;
dataset utilizzato; configurazione; motivazione economica/statistica."

Every candidate the discovery engine backtests — survivor or not — gets an
append-only entry here, so a rejected idea is retired, not silently
forgotten (spec §96 Failed Strategy Database).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_LEDGER_PATH = "research_memory/hypotheses/ledger.jsonl"


@dataclass
class Hypothesis:
    hypothesis_id: str
    date: str
    author: str
    market: str
    mechanism: str
    hypothesis: str
    economic_rationale: str
    expected_behavior: str
    features: list[str] = field(default_factory=list)
    expected_regimes: list[str] = field(default_factory=list)
    expected_failure_modes: list[str] = field(default_factory=list)
    test_plan: str = ""
    result: str = ""
    status: str = "HYPOTHESIS"


class HypothesisLedger:
    """Append-only JSON-Lines store. Never rewrites or deletes a prior
    entry — a superseded hypothesis stays in the file with its original
    result, matching spec §76 "non modificare silenziosamente i risultati
    precedenti."
    """

    def __init__(self, path: str | Path = DEFAULT_LEDGER_PATH):
        self.path = Path(path)

    def append(self, hypothesis: Hypothesis) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(hypothesis)) + "\n")

    def append_many(self, hypotheses: list[Hypothesis]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            for h in hypotheses:
                f.write(json.dumps(asdict(h)) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path) as f:
            return [json.loads(line) for line in f if line.strip()]
