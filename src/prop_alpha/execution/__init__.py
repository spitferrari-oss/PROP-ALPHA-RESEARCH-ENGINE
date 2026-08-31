"""Execution gateway (hardening pass Step 40-41, Blocker D) — SCAFFOLD
ONLY in this pass.

**LIVE EXECUTION: DISABLED.** No code path anywhere in this repository
sends, simulates-as-live, or otherwise routes a real order to a broker or
prop-firm execution API. `base.py` fixes the interface shape future
adapters will implement; `paper.py` is the only concrete adapter enabled;
`gateway.py`'s `get_gateway()` is the single choke point every caller
goes through, and it hands back the paper adapter regardless of what's
requested, raising `LiveExecutionDisabledError` for anything else. This
matches the Constitution's `EXECUTION_DISABLED_UNTIL_APPROVED` immutable
principle (`config/research_constitution.yaml`).
"""
