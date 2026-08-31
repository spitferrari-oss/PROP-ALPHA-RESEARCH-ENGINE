"""The replay driver itself (extension §58): deterministic dispatch of a
collection of `LiveMessageEnvelope`s to a handler, at either as-fast-as-
possible speed (backtesting/shadow-mode replay) or a real-time-scaled
pace (`speed=1.0` reproduces the original wall-clock cadence, `speed=2.0`
plays it back twice as fast, and so on).

`replay_envelopes` — not the caller — owns imposing a deterministic
order: it sorts by `(timestamp_normalized, original position)` regardless
of what order the input arrived in, so two callers handing it the same
envelopes in a different collection order still get the identical replay
sequence. This is what makes the replay "deterministic historical
replay," not just "playback."
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from prop_alpha.data.live.recorder import LiveMessageEnvelope

OnEnvelope = Callable[[LiveMessageEnvelope], None]


@dataclass(frozen=True)
class ReplayResult:
    n_events: int
    start_timestamp: dt.datetime | None
    end_timestamp: dt.datetime | None
    wall_clock_seconds: float


def replay_envelopes(
    envelopes: Iterable[LiveMessageEnvelope],
    on_envelope: OnEnvelope,
    speed: float | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ReplayResult:
    """`speed=None` (the default) or `speed<=0` dispatches every envelope
    immediately, one after another, with no pacing — the right mode for
    backtesting/shadow-mode research where only the *order* of events
    matters, not real elapsed time. `speed>0` sleeps between dispatches
    proportional to the gap between consecutive envelopes'
    `timestamp_normalized`, divided by `speed` — `speed=1.0` reproduces
    the original cadence; a negative gap (out-of-order source data) is
    clamped to zero rather than raising, since replay's job is to play
    back what's there, not validate it (that's `data.quality_engine`'s
    job on the way in).
    """
    ordered = [envelope for _, envelope in sorted(
        enumerate(envelopes), key=lambda pair: (pair[1].timestamp_normalized, pair[0]),
    )]

    wall_clock_start = time.monotonic()
    previous_timestamp: dt.datetime | None = None
    for envelope in ordered:
        if speed and speed > 0 and previous_timestamp is not None:
            gap_seconds = (envelope.timestamp_normalized - previous_timestamp).total_seconds()
            if gap_seconds > 0:
                sleep_fn(gap_seconds / speed)
        on_envelope(envelope)
        previous_timestamp = envelope.timestamp_normalized
    wall_clock_seconds = time.monotonic() - wall_clock_start

    return ReplayResult(
        n_events=len(ordered),
        start_timestamp=ordered[0].timestamp_normalized if ordered else None,
        end_timestamp=ordered[-1].timestamp_normalized if ordered else None,
        wall_clock_seconds=wall_clock_seconds,
    )
