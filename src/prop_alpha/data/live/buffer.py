"""Fixed-capacity recent-message buffer (extension spec §19/§21): backs
stale-feed detection and health reporting without retaining unbounded
memory for a long-running live process.
"""
from __future__ import annotations

import datetime as dt
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class BufferedMessage:
    received_at: dt.datetime
    sequence: int | None
    payload: dict


class MessageBuffer:
    def __init__(self, maxlen: int = 1000):
        self._buffer: deque[BufferedMessage] = deque(maxlen=maxlen)

    def append(self, message: BufferedMessage) -> None:
        self._buffer.append(message)

    def __len__(self) -> int:
        return len(self._buffer)

    def last(self) -> BufferedMessage | None:
        return self._buffer[-1] if self._buffer else None

    def messages_per_second(self, window_seconds: float = 1.0) -> float:
        """Rate over the trailing `window_seconds`, measured against the
        buffer's own most recent message time (not wall-clock `now`) so
        this is deterministic in tests and meaningful during replay.
        """
        if not self._buffer:
            return 0.0
        now = self._buffer[-1].received_at
        cutoff = now - dt.timedelta(seconds=window_seconds)
        count = sum(1 for m in self._buffer if m.received_at >= cutoff)
        return count / window_seconds

    def sequence_gaps(self) -> int:
        """Counts breaks in a strictly-increasing-by-1 sequence among
        messages that carry one; messages without a `sequence` are ignored
        rather than treated as gaps (extension §19).
        """
        gaps = 0
        prev = None
        for m in self._buffer:
            if m.sequence is not None:
                if prev is not None and m.sequence != prev + 1:
                    gaps += 1
                prev = m.sequence
        return gaps
