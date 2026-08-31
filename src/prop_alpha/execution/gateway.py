"""**LIVE EXECUTION: DISABLED.** (hardening pass Step 41.)

`get_gateway()` is the single choke point every caller goes through to
obtain an `ExecutionGateway` — it only ever hands back `PaperExecutionGateway`,
regardless of what name is requested, and raises `LiveExecutionDisabledError`
for anything else. `LIVE_EXECUTION_ENABLED` is a hardcoded module constant,
deliberately not read from `config/providers.yaml` or any environment
variable — flipping it requires an actual code change and review, not a
config toggle a script or agent could silently set.
"""
from __future__ import annotations

from prop_alpha.execution.base import ExecutionGateway
from prop_alpha.execution.paper import PaperExecutionGateway

LIVE_EXECUTION_ENABLED = False


class LiveExecutionDisabledError(RuntimeError):
    pass


def get_gateway(name: str = "paper") -> ExecutionGateway:
    if name != "paper":
        raise LiveExecutionDisabledError(
            f"LIVE EXECUTION: DISABLED — gateway {name!r} is not available in this build. "
            f"Only the paper adapter (execution.paper.PaperExecutionGateway) is enabled."
        )
    assert LIVE_EXECUTION_ENABLED is False, "LIVE_EXECUTION_ENABLED must never be flipped in routine code."
    return PaperExecutionGateway()
