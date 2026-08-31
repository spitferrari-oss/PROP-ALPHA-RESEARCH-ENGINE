"""Audit Trail (spec §129): every Supervisor decision is registered —
date, experiment ID, hypothesis, dataset, config, result, decision, and
reasons — append-only, so a decision is never silently revised (spec §76).
Mirrors the Hypothesis Ledger pattern from Phase 7's discovery engine.

Hardening pass (Step 17, "audit everything"/experiment provenance):
`constitution_id`/`constitution_version`/`constitution_hash`/`git_commit`
were added so every audit entry is traceable back to exactly which
Research Constitution and code revision it was decided under — not just
which dataset/config. They default to `""` so existing call sites and any
serialized entries from before this field existed keep working; `cli.py`'s
one real call site populates them from `governance.constitution.
get_constitution_status()` and `utils.hashing.git_commit_hash()`.
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
    constitution_id: str = ""
    constitution_version: str = ""
    constitution_hash: str = ""
    git_commit: str = ""


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
