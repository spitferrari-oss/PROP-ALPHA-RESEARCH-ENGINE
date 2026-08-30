"""Supervisor Agent (spec §58/§60/§128): the sole component authorized to
declare a research verdict, and only on formalized criteria — the gates
and findings the other agents already produced, never a fresh judgment
call of its own. Its verdict is deliberately never phrased as "PASS"
alone: `PASSES_ALL_EVALUATED_GATES` is explicit that gates marked
NOT_EVALUATED (leakage engine, parameter sensitivity, paper trading) are
still outstanding and this is not a live-trading clearance (spec §128:
the system must never declare an alpha "real-money ready" by itself).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from prop_alpha.agents.gates import Finding, Gate

PASS_VERDICT = "PASSES_ALL_EVALUATED_GATES"
FAIL_VERDICT = "RESEARCH_FAIL"


@dataclass
class SupervisorVerdict:
    verdict: str
    gates: list[Gate]
    findings: list[Finding]
    blocking_reasons: list[str] = field(default_factory=list)
    not_evaluated_gates: list[str] = field(default_factory=list)
    disclaimer: str = ""


def review(gates: list[Gate], findings: list[Finding]) -> SupervisorVerdict:
    evaluated = [g for g in gates if g.status != "NOT_EVALUATED"]
    failed_gates = [g for g in evaluated if g.status == "FAIL"]
    high_findings = [f for f in findings if f.severity == "HIGH"]

    blocking_reasons = [f"Gate {g.name} FAILED: {g.detail}" for g in failed_gates]
    blocking_reasons += [f"Critic finding {f.category} (HIGH): {f.description}" for f in high_findings]

    verdict = FAIL_VERDICT if blocking_reasons else PASS_VERDICT
    not_evaluated = [g.name for g in gates if g.status == "NOT_EVALUATED"]

    disclaimer = (
        f"This verdict covers only the {len(evaluated)} gate(s) this system can mechanically "
        f"evaluate. {len(not_evaluated)} gate(s) were NOT_EVALUATED "
        f"({', '.join(not_evaluated) if not_evaluated else 'none'}) and require human review "
        f"before this alpha is treated as live-eligible — this system must never declare an "
        f"alpha \"real-money ready\" on its own (spec §128)."
    )

    return SupervisorVerdict(
        verdict=verdict, gates=gates, findings=findings,
        blocking_reasons=blocking_reasons, not_evaluated_gates=not_evaluated, disclaimer=disclaimer,
    )
