"""Audit Trail (spec §129): every Supervisor decision is registered —
date, experiment ID, hypothesis, dataset, config, result, decision, and
reasons — append-only, so a decision is never silently revised (spec §76).
Mirrors the Hypothesis Ledger pattern from Phase 7's discovery engine.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_AUDIT_PATH = "research_memory/audit/audit_trail.jsonl"


@dataclass
class AuditEntry:
    date: str
    experiment_id: str
    alpha_id: str
    alpha_name: str
    hypothesis: str
    dataset_hash: str
    config_hash: str
    result_summary: str
    decision: str
    reasons: list[str] = field(default_factory=list)


class AuditTrail:
    def __init__(self, path: str | Path = DEFAULT_AUDIT_PATH):
        self.path = Path(path)

    def append(self, entry: AuditEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path) as f:
            return [json.loads(line) for line in f if line.strip()]
