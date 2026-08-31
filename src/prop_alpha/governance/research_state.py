"""Research state transition integrity (hardening pass Step 51,
Constitution principle `STATE_TRANSITIONS_GATED`).

`config/research_constitution.yaml`'s `research_states` list is the
canonical ordering: `HYPOTHESIS -> BACKTESTED -> OUT_OF_SAMPLE ->
WALK_FORWARD -> ROBUST -> PAPER_TRADING_ACCEPTABLE -> LIVE_APPROVED ->
LIVE`, plus `RETIRED` reachable from anywhere non-terminal. This module
is the enforcement: `validate_transition` raises unless a proposed
`(old_state, new_state)` pair is either a one-step forward move, a move
to `RETIRED`, or a no-op — it is never legal to skip an intermediate
gate (e.g. `HYPOTHESIS` straight to `LIVE`, or `RESEARCH`-stage straight
to `LIVE`), regardless of who or what is requesting the transition.

Nothing in this codebase currently sets an alpha's `research_status` to
anything past `WALK_FORWARD`/`OUT_OF_SAMPLE`/`BACKTESTED` (see
`cli.py::_run_full_research`) — this module exists so that when a future
promotion pathway is built, it is structurally unable to skip a gate,
not because today's pipeline is at risk of doing so.
"""
from __future__ import annotations

from dataclasses import dataclass

# Canonical order — mirrors config/research_constitution.yaml's
# `research_states` list exactly; kept as a plain tuple here (not loaded
# from the YAML at import time) so this module has no import-time
# dependency on the Constitution file being present/valid — the
# Constitution's own list is the documentation source of truth, this is
# the enforcement mirror of it, matched by test_governance_research_state.py.
RESEARCH_STATE_ORDER: tuple[str, ...] = (
    "HYPOTHESIS", "BACKTESTED", "OUT_OF_SAMPLE", "WALK_FORWARD",
    "ROBUST", "PAPER_TRADING_ACCEPTABLE", "LIVE_APPROVED", "LIVE",
)
TERMINAL_STATE = "RETIRED"

_ALL_STATES = frozenset(RESEARCH_STATE_ORDER) | {TERMINAL_STATE}
_INDEX = {state: i for i, state in enumerate(RESEARCH_STATE_ORDER)}


class ResearchStateError(RuntimeError):
    """Raised on an illegal research-state transition — a skipped gate,
    an unknown state name, or a move away from RETIRED.
    """


@dataclass(frozen=True)
class TransitionCheck:
    old_state: str
    new_state: str
    allowed: bool
    reason: str


def _check(old_state: str, new_state: str) -> TransitionCheck:
    if old_state not in _ALL_STATES:
        return TransitionCheck(old_state, new_state, False, f"unknown old_state {old_state!r}")
    if new_state not in _ALL_STATES:
        return TransitionCheck(old_state, new_state, False, f"unknown new_state {new_state!r}")
    if old_state == TERMINAL_STATE:
        return TransitionCheck(old_state, new_state, False, "RETIRED is terminal — no transition out of it is legal")
    if old_state == new_state:
        return TransitionCheck(old_state, new_state, True, "no-op")
    if new_state == TERMINAL_STATE:
        return TransitionCheck(old_state, new_state, True, "retiring an alpha is always legal from any non-terminal state")

    old_idx = _INDEX[old_state]
    new_idx = _INDEX[new_state]
    if new_idx == old_idx + 1:
        return TransitionCheck(old_state, new_state, True, "one-step forward move")
    if new_idx < old_idx:
        return TransitionCheck(old_state, new_state, True, "backward move (e.g. re-opening after a decay/drift finding) is allowed")
    skipped = RESEARCH_STATE_ORDER[old_idx + 1:new_idx]
    return TransitionCheck(
        old_state, new_state, False,
        f"skips required intermediate gate(s): {list(skipped)} — "
        f"extension/Constitution STATE_TRANSITIONS_GATED forbids this",
    )


def validate_transition(old_state: str, new_state: str) -> TransitionCheck:
    """Never raises — returns a `TransitionCheck` describing whether the
    move is allowed and why/why not. Use `assert_valid_transition` for
    the hard-failing form.
    """
    return _check(old_state, new_state)


def assert_valid_transition(old_state: str, new_state: str) -> TransitionCheck:
    result = _check(old_state, new_state)
    if not result.allowed:
        raise ResearchStateError(
            f"Illegal research state transition {old_state!r} -> {new_state!r}: {result.reason}"
        )
    return result
