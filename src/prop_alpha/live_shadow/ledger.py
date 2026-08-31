"""Append-only JSON-Lines store for proposals and feedback (extension
§76-80), mirroring `discovery.hypothesis.HypothesisLedger`/`agents.audit.
AuditTrail`'s exact pattern: never rewrites or deletes a prior entry.
Both record kinds share one file, tagged by `"kind"`, so the ledger reads
back as a single chronological log of everything that happened to a
proposal — logged, then (eventually) decided.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from prop_alpha.live_shadow.feedback import FeedbackRecord
from prop_alpha.live_shadow.proposal import TradeProposal

DEFAULT_LEDGER_PATH = "research_memory/live_shadow/proposals.jsonl"


class LiveShadowLedger:
    def __init__(self, path: str | Path = DEFAULT_LEDGER_PATH):
        self.path = Path(path)

    def _append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def record_proposal(self, proposal: TradeProposal) -> None:
        self._append({"kind": "PROPOSAL", **asdict(proposal)})

    def record_feedback(self, feedback: FeedbackRecord) -> None:
        self._append({"kind": "FEEDBACK", **asdict(feedback)})

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def read_proposals(self) -> list[dict]:
        return [r for r in self.read_all() if r["kind"] == "PROPOSAL"]

    def read_feedback(self) -> list[dict]:
        return [r for r in self.read_all() if r["kind"] == "FEEDBACK"]
