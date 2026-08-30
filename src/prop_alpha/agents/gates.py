"""Shared Gate/Finding types for the Multi-Agent Research Architecture
(spec §58-60). A Gate is a single mechanically-checked criterion from the
spec §60 Research Gates list; `NOT_EVALUATED` is a distinct status from
`FAIL` — it means no engine exists yet to check that gate (e.g. a
dedicated leakage engine, parameter-sensitivity sweep, or paper trading),
not that the alpha failed it. The Supervisor (spec §128) must never treat
a `NOT_EVALUATED` gate as passed.
"""
from __future__ import annotations

from dataclasses import dataclass

GATE_STATUSES = ("PASS", "FAIL", "NOT_EVALUATED")
FINDING_SEVERITIES = ("LOW", "MEDIUM", "HIGH")


@dataclass
class Gate:
    name: str
    status: str
    detail: str

    def __post_init__(self):
        if self.status not in GATE_STATUSES:
            raise ValueError(f"Gate status must be one of {GATE_STATUSES}, got {self.status!r}")


@dataclass
class Finding:
    category: str
    severity: str
    description: str

    def __post_init__(self):
        if self.severity not in FINDING_SEVERITIES:
            raise ValueError(f"Finding severity must be one of {FINDING_SEVERITIES}, got {self.severity!r}")
