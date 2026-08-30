"""Live data recorder (extension spec §14-15): every relevant live message
becomes a `LiveMessageEnvelope` carrying the exchange timestamp, the
provider's own timestamp, the local receive timestamp, and a normalized
timestamp — four distinct fields, never collapsed into one, and the
exchange timestamp is never overwritten by the local one (§15: "NON
sostituire il timestamp dell'exchange con quello locale").
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class LiveMessageEnvelope:
    timestamp_exchange: dt.datetime | None
    timestamp_provider: dt.datetime | None
    timestamp_received: dt.datetime
    timestamp_normalized: dt.datetime
    provider: str
    instrument: str
    schema: str
    payload: dict
    sequence: int | None = None
    latency_ms: float | None = None

    def __post_init__(self):
        for name in ("timestamp_exchange", "timestamp_provider", "timestamp_received", "timestamp_normalized"):
            ts = getattr(self, name)
            if ts is not None and ts.tzinfo is None:
                raise ValueError(
                    f"{name} must be timezone-aware — internal logic uses UTC as the canonical "
                    f"reference (extension §16/§17)."
                )


def build_envelope(
    *,
    provider: str,
    instrument: str,
    schema: str,
    payload: dict,
    timestamp_exchange: dt.datetime | None = None,
    timestamp_provider: dt.datetime | None = None,
    sequence: int | None = None,
    received_at: dt.datetime | None = None,
) -> LiveMessageEnvelope:
    """`timestamp_normalized` falls back exchange -> provider -> received,
    in that priority order, per extension §15's timestamp policy — the
    exchange timestamp is authoritative whenever the provider supplies one.
    `latency_ms` is measured against whichever of those two is available,
    since local receive time vs. exchange/provider time is the latency
    that matters, not the normalized value's own definition.
    """
    received = received_at or dt.datetime.now(dt.timezone.utc)
    reference = timestamp_exchange or timestamp_provider
    normalized = reference or received
    latency_ms = (received - reference).total_seconds() * 1000.0 if reference is not None else None
    return LiveMessageEnvelope(
        timestamp_exchange=timestamp_exchange,
        timestamp_provider=timestamp_provider,
        timestamp_received=received,
        timestamp_normalized=normalized,
        provider=provider,
        instrument=instrument,
        schema=schema,
        payload=payload,
        sequence=sequence,
        latency_ms=latency_ms,
    )


def _jsonl_sink(path: str) -> Callable[[LiveMessageEnvelope], None]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def sink(envelope: LiveMessageEnvelope) -> None:
        record = {
            "timestamp_exchange": envelope.timestamp_exchange.isoformat() if envelope.timestamp_exchange else None,
            "timestamp_provider": envelope.timestamp_provider.isoformat() if envelope.timestamp_provider else None,
            "timestamp_received": envelope.timestamp_received.isoformat(),
            "timestamp_normalized": envelope.timestamp_normalized.isoformat(),
            "provider": envelope.provider,
            "instrument": envelope.instrument,
            "schema": envelope.schema,
            "payload": envelope.payload,
            "sequence": envelope.sequence,
            "latency_ms": envelope.latency_ms,
        }
        with open(p, "a") as f:
            f.write(json.dumps(record) + "\n")

    return sink


class LiveRecorder:
    """Records every envelope handed to it via a pluggable, append-only
    sink (extension §8's data-immutability principle applies to live
    recordings too — a sink must never overwrite a prior record). The
    default JSONL sink mirrors this repo's existing HypothesisLedger/
    AuditTrail append-only pattern; a partitioned Parquet/DuckDB sink is
    extension Phase G's job, not this one.
    """

    def __init__(
        self,
        sink: Callable[[LiveMessageEnvelope], None] | None = None,
        path: str | None = None,
    ):
        if sink is not None and path is not None:
            raise ValueError("Pass either sink= or path=, not both.")
        if path is not None:
            sink = _jsonl_sink(path)
        self._sink = sink or (lambda envelope: None)
        self._count = 0

    def record(self, envelope: LiveMessageEnvelope) -> None:
        self._sink(envelope)
        self._count += 1

    @property
    def message_count(self) -> int:
        return self._count
