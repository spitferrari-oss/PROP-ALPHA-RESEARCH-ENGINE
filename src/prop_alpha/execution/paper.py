"""The only enabled execution adapter (hardening pass Step 40). Every
order is simulated — filled immediately at the caller-supplied price (or
`0.0` if none was given, which is itself a signal this wasn't a real
priced order), tracked in an in-memory ledger. No network call, no
broker/prop API, ever — `live_execution_enabled` is always `False`.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from prop_alpha.execution.base import AccountState, ExecutionGateway, OrderRequest, OrderResult, Position


def _new_order_id(counter: int) -> str:
    return f"PAPER-{counter:06d}-{uuid.uuid4().hex[:8]}"


@dataclass
class PaperExecutionGateway(ExecutionGateway):
    name: str = "paper"
    live_execution_enabled: bool = False
    starting_equity: float = 100_000.0
    _positions: dict[str, Position] = field(default_factory=dict)
    _cash_pnl: float = 0.0
    _order_counter: int = 0

    def get_account_state(self) -> AccountState:
        equity = self.starting_equity + self._cash_pnl + sum(p.unrealized_pnl for p in self._positions.values())
        return AccountState(
            account_id="PAPER", equity=equity, balance=self.starting_equity + self._cash_pnl,
            open_positions=len(self._positions), as_of=dt.datetime.now(dt.timezone.utc),
        )

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def submit_order(self, order: OrderRequest) -> OrderResult:
        self._order_counter += 1
        order_id = _new_order_id(self._order_counter)

        fill_price = order.limit_price if order.limit_price is not None else order.stop_price
        if fill_price is None:
            fill_price = 0.0

        signed_qty = order.quantity if order.direction == "LONG" else -order.quantity
        existing = self._positions.get(order.instrument)
        if existing is None:
            new_qty = signed_qty
        else:
            new_qty = existing.quantity + signed_qty

        if new_qty == 0:
            self._positions.pop(order.instrument, None)
        else:
            self._positions[order.instrument] = Position(
                instrument=order.instrument, quantity=new_qty, average_price=fill_price, unrealized_pnl=0.0,
            )

        return OrderResult(
            order_id=order_id, status="SIMULATED_FILLED", filled_price=fill_price,
            filled_quantity=order.quantity, message="Simulated fill — no real order was sent.",
        )

    def modify_order(self, order_id: str, **changes) -> OrderResult:
        return OrderResult(
            order_id=order_id, status="REJECTED",
            message="Paper gateway fills immediately; there is no pending order to modify.",
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(
            order_id=order_id, status="REJECTED",
            message="Paper gateway fills immediately; there is nothing pending to cancel.",
        )

    def close_position(self, instrument: str) -> OrderResult:
        existing = self._positions.pop(instrument, None)
        if existing is None:
            return OrderResult(order_id="NONE", status="REJECTED", message=f"No open position in {instrument}.")
        self._order_counter += 1
        order_id = _new_order_id(self._order_counter)
        return OrderResult(
            order_id=order_id, status="SIMULATED_FILLED", filled_price=existing.average_price,
            filled_quantity=abs(existing.quantity), message="Simulated close — no real order was sent.",
        )
