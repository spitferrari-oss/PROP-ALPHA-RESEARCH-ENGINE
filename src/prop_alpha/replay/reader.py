"""Two sources of historical envelopes, converging on the same
`LiveMessageEnvelope` shape (extension §56-57):

- `read_jsonl_envelopes`: the exact inverse of `data.live.recorder.
  _jsonl_sink` — replays back a session `pae data record` (Phase F) wrote.
- `dataframe_to_envelopes`: wraps an already-ingested historical bar frame
  (e.g. from `data.lake_query.query_tier`, Phase G) as envelopes, so the
  replay engine can drive a handler off real historical bars, not just
  recorded live sessions.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from prop_alpha.data.live.recorder import LiveMessageEnvelope


def _parse_ts(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if value is not None else None


def read_jsonl_envelopes(path: str) -> list[LiveMessageEnvelope]:
    """Reads back a JSONL file written by `data.live.recorder._jsonl_sink`.
    Returns envelopes in file order (whatever order they were originally
    recorded in) — `engine.replay_envelopes` is responsible for imposing
    deterministic timestamp order, not this reader.
    """
    envelopes = []
    with open(Path(path)) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            envelopes.append(
                LiveMessageEnvelope(
                    timestamp_exchange=_parse_ts(record["timestamp_exchange"]),
                    timestamp_provider=_parse_ts(record["timestamp_provider"]),
                    timestamp_received=_parse_ts(record["timestamp_received"]),
                    timestamp_normalized=_parse_ts(record["timestamp_normalized"]),
                    provider=record["provider"],
                    instrument=record["instrument"],
                    schema=record["schema"],
                    payload=record["payload"],
                    sequence=record.get("sequence"),
                    latency_ms=record.get("latency_ms"),
                )
            )
    return envelopes


def dataframe_to_envelopes(
    df: pd.DataFrame,
    provider: str,
    instrument: str,
    schema: str,
    timestamp_column: str = "timestamp",
) -> list[LiveMessageEnvelope]:
    """Wraps each row of a historical bar frame as a `LiveMessageEnvelope`.

    There is no real "received at" moment for a historical bar the way
    there is for a live message — using the bar's own timestamp for
    `timestamp_received` (as well as `timestamp_exchange`/
    `timestamp_normalized`) is the honest choice here, not a fabricated
    arrival time; `latency_ms` is left `None` for the same reason (there
    is nothing to measure latency against). `sequence` is the row's
    position in `df`, giving replay a deterministic tie-break for rows
    that share a timestamp.
    """
    if timestamp_column not in df.columns:
        raise ValueError(f"'{timestamp_column}' column not found in frame (columns: {list(df.columns)})")

    envelopes = []
    for position, row in enumerate(df.to_dict("records")):
        timestamp = row[timestamp_column]
        if not isinstance(timestamp, dt.datetime):
            timestamp = pd.Timestamp(timestamp).to_pydatetime()
        if timestamp.tzinfo is None:
            raise ValueError(
                f"row {position}'s '{timestamp_column}' is timezone-naive — extension §16/§17 "
                f"require UTC-aware timestamps throughout."
            )
        payload = {k: v for k, v in row.items() if k != timestamp_column}
        envelopes.append(
            LiveMessageEnvelope(
                timestamp_exchange=timestamp,
                timestamp_provider=None,
                timestamp_received=timestamp,
                timestamp_normalized=timestamp,
                provider=provider,
                instrument=instrument,
                schema=schema,
                payload=payload,
                sequence=position,
                latency_ms=None,
            )
        )
    return envelopes
