"""Dedicated options live recorder (hardening pass Step 27-28).

Mirrors `data.live.recorder`'s exact immutability discipline
(extension §7-8: a written record is never overwritten; a correction is
a new, distinct record) but for options snapshots specifically, at
per-metric granularity — a `GexbotOptionsProvider.get_snapshot()` call
produces one `OptionsSnapshot` with 12 metrics, each independently
available/stale/unavailable (extension §26); `collector.
collect_snapshot_records` turns that into 12 separate
`OptionsSnapshotRecord`s rather than one record that would flatten each
metric's own availability/freshness into a single snapshot-level status.
"""
