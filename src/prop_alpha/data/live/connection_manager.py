"""Live connection lifecycle management (extension spec §13): connect,
disconnect, reconnect with exponential backoff, and heartbeat/timeout-based
stale detection. Provider-agnostic — it drives any object implementing the
small `Connectable` protocol below, so a vendor's live client plugs in
without this module knowing anything about it. Preventing *duplicate*
connections for the same feed is `subscription_manager.SubscriptionManager`'s
job, not this class's — a `ConnectionManager` only manages the lifecycle of
one connection it already owns.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol


class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    STALE = "STALE"
    FAILED = "FAILED"


class Connectable(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...


@dataclass(frozen=True)
class BackoffPolicy:
    initial_seconds: float = 1.0
    max_seconds: float = 60.0
    multiplier: float = 2.0

    def delay_for_attempt(self, attempt: int) -> float:
        """`attempt` is 1-indexed (the first retry is attempt 1)."""
        return min(self.initial_seconds * (self.multiplier ** max(attempt - 1, 0)), self.max_seconds)


class ConnectionManager:
    """Owns exactly one live connection's lifecycle. `clock`/`sleep_fn` are
    injectable so tests never actually sleep or depend on wall-clock time
    (extension §134/§136: no real timing dependency in tests).
    """

    def __init__(
        self,
        connectable: Connectable,
        backoff: BackoffPolicy | None = None,
        heartbeat_timeout_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self._connectable = connectable
        self._backoff = backoff or BackoffPolicy()
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._clock = clock
        self._sleep_fn = sleep_fn
        self.state = ConnectionState.DISCONNECTED
        self._last_heartbeat: float | None = None
        self._attempt = 0

    def connect(self) -> None:
        self.state = ConnectionState.CONNECTING
        try:
            self._connectable.connect()
        except Exception:
            self.state = ConnectionState.FAILED
            raise
        self.state = ConnectionState.CONNECTED
        self._attempt = 0
        self._last_heartbeat = self._clock()

    def disconnect(self) -> None:
        self._connectable.disconnect()
        self.state = ConnectionState.DISCONNECTED
        self._last_heartbeat = None

    def on_heartbeat(self) -> None:
        """Called whenever any message (not just an explicit heartbeat
        frame) arrives — any live traffic counts as proof the feed is
        alive, per extension §13's "heartbeat; timeout; stale feed."
        """
        self._last_heartbeat = self._clock()
        if self.state in (ConnectionState.STALE, ConnectionState.RECONNECTING):
            self.state = ConnectionState.CONNECTED

    def is_stale(self) -> bool:
        if self._last_heartbeat is None:
            return False
        return (self._clock() - self._last_heartbeat) > self._heartbeat_timeout

    def check_health(self) -> ConnectionState:
        if self.state == ConnectionState.CONNECTED and self.is_stale():
            self.state = ConnectionState.STALE
        return self.state

    def reconnect(self) -> None:
        self._attempt += 1
        self.state = ConnectionState.RECONNECTING
        self._sleep_fn(self._backoff.delay_for_attempt(self._attempt))
        try:
            self._connectable.disconnect()
        except Exception:
            pass  # already disconnected/never connected — reconnect proceeds regardless
        self.connect()
