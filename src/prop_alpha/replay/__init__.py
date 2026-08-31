"""Deterministic Historical Replay Engine (extension spec §56-58, Phase N).

The point of the replay engine is that a handler written against the Live
Data Engine's `LiveMessageEnvelope`/`EventRouter` shape (Phase C) never
needs a second, historical-only code path: `reader.read_jsonl_envelopes`
replays a recorded live session (Phase F's `LiveRecorder` output) back as
envelopes, and `reader.dataframe_to_envelopes` converts an ingested
historical bar frame (Phase G's lake) into the same envelope shape, so
`engine.replay_envelopes` can dispatch either — or both merged together —
through the exact same `on_envelope` callback a live subscription would
use. Phase O's shadow mode is the first consumer of this.

Determinism means: given the same input envelopes, replay dispatches them
in the exact same order every time. Ordering is `(timestamp_normalized,
original position)` — the position tie-break matters because two
envelopes can legitimately share a timestamp (e.g. a historical bar and
an options snapshot synced to the same second), and without a defined
tie-break rule "the same order every time" wouldn't actually hold.
"""
