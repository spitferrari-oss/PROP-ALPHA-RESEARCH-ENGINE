"""Execution gateway interface (hardening pass Step 40) — the shape a
real broker/prop-firm adapter would eventually implement. Fixing this
now, while only `paper.py` implements it, means a future real adapter
slots in behind the same interface every caller already codes against —
the same "core imports only the ABC" discipline `providers.base`
established for market data.
"""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AccountState:
    account_id: str
    equity: float
    balance: float
    open_positions: int
    as_of: dt.datetime


@dataclass(frozen=True)
class Position:
    instrument: str
    quantity: float
    average_price: float
    unrealized_pnl: float


@dataclass(frozen=True)
class OrderRequest:
    instrument: str
    direction: str  # "LONG" | "SHORT"
    quantity: float
    order_type: str = "MARKET"
    limit_price: float | None = None
    stop_price: float | None = None


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    status: str  # e.g. "SIMULATED_FILLED" | "REJECTED" — a real adapter would add "SUBMITTED"/"FILLED"/"CANCELLED"
    filled_price: float | None = None
    filled_quantity: float | None = None
    message: str = ""


class ExecutionGateway(ABC):
    """`live_execution_enabled` exists as a required attribute so every
    concrete gateway must explicitly declare it — there is no default
    that could accidentally read as "enabled."
    """
    name: str
    live_execution_enabled: bool

    @abstractmethod
    def get_account_state(self) -> AccountState: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def modify_order(self, order_id: str, **changes) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResult: ...

    @abstractmethod
    def close_position(self, instrument: str) -> OrderResult: ...
