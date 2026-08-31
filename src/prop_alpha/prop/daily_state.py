"""Explicit daily account/day state machine (hardening pass Step 6).

`prop/simulator.py` already tracks account state (equity, drawdown, rule
breaches) and `risk/stop_trading.py` already decides which historical
trades a stop-trading policy would have skipped — this module doesn't
duplicate either. It adds the missing *named* abstraction: which of a
small, explicit set of states the trading day is currently in, and which
transitions between them are legal. `evaluate_daily_state` is a real
decision function that derives the next state from account/eligibility
facts (an `AccountState`/`TradeEligibility` from elsewhere in this
codebase feed into it); `DailyStateMachine.transition` is the lower-level
primitive that enforces the transition graph regardless of what decided
the target state.

`DAILY_STOP` and `TARGET_REACHED` are terminal for the day — no
transition out of either is legal until a new day resets the machine
(`DailyStateMachine()` with no arguments starts a fresh `PRE_MARKET` day).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum


class DailyState(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    READY = "READY"
    TRADE_ALLOWED = "TRADE_ALLOWED"
    TRADE_ACTIVE = "TRADE_ACTIVE"
    PROFIT_PROTECTED = "PROFIT_PROTECTED"
    LOSS_CONTROL = "LOSS_CONTROL"
    NO_TRADE = "NO_TRADE"
    DAILY_STOP = "DAILY_STOP"
    TARGET_REACHED = "TARGET_REACHED"


class DailyStateError(RuntimeError):
    """Raised on an illegal transition — never silently ignored or
    clamped to the nearest legal state.
    """


_TERMINAL_STATES = frozenset({DailyState.DAILY_STOP, DailyState.TARGET_REACHED})

_ALLOWED_TRANSITIONS: dict[DailyState, frozenset[DailyState]] = {
    DailyState.PRE_MARKET: frozenset({DailyState.READY}),
    DailyState.READY: frozenset({DailyState.TRADE_ALLOWED, DailyState.NO_TRADE}),
    DailyState.TRADE_ALLOWED: frozenset({
        DailyState.TRADE_ACTIVE, DailyState.NO_TRADE, DailyState.PROFIT_PROTECTED,
        DailyState.LOSS_CONTROL, DailyState.DAILY_STOP, DailyState.TARGET_REACHED,
    }),
    DailyState.TRADE_ACTIVE: frozenset({
        DailyState.TRADE_ALLOWED, DailyState.PROFIT_PROTECTED, DailyState.LOSS_CONTROL,
        DailyState.DAILY_STOP, DailyState.TARGET_REACHED,
    }),
    DailyState.PROFIT_PROTECTED: frozenset({
        DailyState.TRADE_ALLOWED, DailyState.NO_TRADE, DailyState.TARGET_REACHED, DailyState.DAILY_STOP,
    }),
    DailyState.LOSS_CONTROL: frozenset({
        DailyState.TRADE_ALLOWED, DailyState.NO_TRADE, DailyState.DAILY_STOP,
    }),
    DailyState.NO_TRADE: frozenset({DailyState.TRADE_ALLOWED, DailyState.DAILY_STOP}),
    DailyState.DAILY_STOP: frozenset(),
    DailyState.TARGET_REACHED: frozenset(),
}


@dataclass(frozen=True)
class DailyStateMachine:
    state: DailyState = DailyState.PRE_MARKET
    history: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    @property
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    @property
    def can_trade(self) -> bool:
        return self.state in (DailyState.TRADE_ALLOWED, DailyState.TRADE_ACTIVE)

    def allowed_next_states(self) -> frozenset[DailyState]:
        return _ALLOWED_TRANSITIONS[self.state]

    def transition(self, new_state: DailyState, reason: str = "") -> "DailyStateMachine":
        if self.is_terminal:
            raise DailyStateError(
                f"{self.state.value} is terminal for the trading day — cannot transition to "
                f"{new_state.value}. Start a new DailyStateMachine() for the next day."
            )
        allowed = self.allowed_next_states()
        if new_state not in allowed:
            raise DailyStateError(
                f"Illegal transition {self.state.value} -> {new_state.value}. "
                f"Allowed from {self.state.value}: {sorted(s.value for s in allowed) or 'none (terminal)'}."
            )
        return replace(
            self, state=new_state,
            history=self.history + ((self.state.value, new_state.value, reason),),
        )


def evaluate_daily_state(
    machine: DailyStateMachine,
    eligible: bool,
    position_open: bool,
    daily_pnl_r: float | None = None,
    target_r: float | None = None,
    stop_r: float | None = None,
    profit_protect_r: float | None = None,
    loss_control_r: float | None = None,
) -> DailyStateMachine:
    """Derives and applies the next state from account/eligibility facts.
    Every threshold (`target_r`, `stop_r`, `profit_protect_r`,
    `loss_control_r`) is caller-supplied — never hardcoded here — and
    `None` means "this boundary isn't configured, don't evaluate it,"
    never "assume zero."
    """
    if machine.state == DailyState.PRE_MARKET:
        return machine.transition(DailyState.READY, "session opened")

    if target_r is not None and daily_pnl_r is not None and daily_pnl_r >= target_r:
        if machine.state != DailyState.TARGET_REACHED:
            return machine.transition(DailyState.TARGET_REACHED, f"daily_pnl_r={daily_pnl_r} >= target_r={target_r}")
        return machine

    if stop_r is not None and daily_pnl_r is not None and daily_pnl_r <= -stop_r:
        if machine.state != DailyState.DAILY_STOP:
            return machine.transition(DailyState.DAILY_STOP, f"daily_pnl_r={daily_pnl_r} <= -stop_r={stop_r}")
        return machine

    if machine.is_terminal:
        return machine

    if position_open:
        if machine.state != DailyState.TRADE_ACTIVE:
            return machine.transition(DailyState.TRADE_ACTIVE, "position opened")
        return machine

    if loss_control_r is not None and daily_pnl_r is not None and daily_pnl_r <= -loss_control_r:
        target = DailyState.LOSS_CONTROL
    elif profit_protect_r is not None and daily_pnl_r is not None and daily_pnl_r >= profit_protect_r:
        target = DailyState.PROFIT_PROTECTED
    elif eligible:
        target = DailyState.TRADE_ALLOWED
    else:
        target = DailyState.NO_TRADE

    if machine.state == target:
        return machine
    if target not in machine.allowed_next_states():
        # Not every state can jump directly to every other -- e.g.
        # LOSS_CONTROL -> PROFIT_PROTECTED isn't a legal direct edge.
        # Route through TRADE_ALLOWED first, which every non-terminal
        # state can reach, rather than silently refusing to update.
        machine = machine.transition(DailyState.TRADE_ALLOWED, "routing through TRADE_ALLOWED")
        if target == DailyState.TRADE_ALLOWED:
            return machine
    return machine.transition(target, reason=f"daily_pnl_r={daily_pnl_r}, eligible={eligible}")
