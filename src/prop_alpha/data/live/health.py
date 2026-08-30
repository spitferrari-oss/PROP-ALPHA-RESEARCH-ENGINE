"""Feed/connection health snapshot (extension spec §19-21): what the
eventual Data Center dashboard (Phase M) renders per feed. Derived from a
`ConnectionManager` + `MessageBuffer` rather than tracked separately, so
there is exactly one source of truth for "is this feed OK."
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from prop_alpha.data.live.buffer import MessageBuffer
from prop_alpha.data.live.connection_manager import ConnectionManager, ConnectionState


@dataclass(frozen=True)
class FeedHealth:
    provider: str
    instrument: str
    connection_state: ConnectionState
    messages_received: int
    messages_per_second: float
    sequence_gaps: int
    last_message_age_seconds: float | None


def compute_feed_health(
    provider: str,
    instrument: str,
    connection: ConnectionManager,
    buffer: MessageBuffer,
    now: dt.datetime | None = None,
) -> FeedHealth:
    now = now or dt.datetime.now(dt.timezone.utc)
    last = buffer.last()
    age_seconds = (now - last.received_at).total_seconds() if last else None
    return FeedHealth(
        provider=provider,
        instrument=instrument,
        connection_state=connection.check_health(),
        messages_received=len(buffer),
        messages_per_second=buffer.messages_per_second(),
        sequence_gaps=buffer.sequence_gaps(),
        last_message_age_seconds=age_seconds,
    )
