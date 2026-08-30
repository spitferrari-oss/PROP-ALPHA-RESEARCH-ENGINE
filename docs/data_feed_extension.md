# Data Feed + Options Intelligence Layer (Extension)

This tracks the separate "PROP ALPHA RESEARCH ENGINE — Production Extension:
Data Feed + Options Intelligence Layer" specification (v1.0, 2026-08-30),
which **extends** — does not replace — the main Production Specification
and the Research Constitution. It adds real historical/live market data
(Databento) and options intelligence (GEXBOT) infrastructure around the
existing 10-phase research core, kept strictly separate per its own §1:

```text
MARKET DATA | OPTIONS DATA | ALPHA ENGINE | RISK ENGINE | EXECUTION ENGINE
```

Implementation follows the extension's own phase order (§152, Phase A
through Phase P) with the same discipline as the main spec: one phase at a
time, tests before moving on, nothing claimed as done that isn't tested.
**This extension does not activate live orders** (§132, §162) — it stops at
data, market state, signals, and paper/shadow simulation.

## What's implemented

**Phase A — Provider Abstraction (extension §1-5)**
- `providers/base.py`: `FuturesDataProvider` and `OptionsDataProvider`
  abstract base classes (extension §2) — the PARE core is meant to import
  only these, never a vendor SDK directly. Every abstract method
  (`get_historical`, `subscribe_live`, `get_instrument_definition`,
  `get_trading_calendar` for futures; the options equivalents plus
  `get_levels`/`get_orderflow`/`get_instrument_state`) is enforced by
  Python's `ABC` — a subclass missing one raises `TypeError` at
  instantiation, not silently at call time.
- `DataLevel` enum (extension §5): `L1` (OHLCV) through `L4` (MBO/full
  order book), with `DataLevel.satisfies(minimum)` as the comparison an
  eventual Alpha Eligibility Matrix (extension §123, a later phase) will
  use to decide whether a provider/instrument/schema can serve what an
  alpha declares it needs.
- `InstrumentDefinition` / `TradingCalendar` dataclasses: vendor-agnostic
  contract metadata and per-instrument trading calendars (extension §18 —
  not every instrument shares one calendar), so `get_instrument_definition`/
  `get_trading_calendar` never leak a provider's raw payload shape into
  the rest of the engine.
- `providers/databento/` and `providers/gexbot/` package skeletons
  (extension §3) — empty except for a docstring naming which later phase
  fills each in. No adapter code, no vendor SDK dependency, no network
  calls: extension §3 explicitly says prepare the architecture, not code
  nobody can use yet ("Non implementare provider aggiuntivi solo per
  completezza").
- `get_snapshot`/`get_levels`/`get_instrument_state` on
  `OptionsDataProvider` return plain `dict`s in this phase rather than a
  fixed `OptionsSnapshot`/`OptionsLevel` model — extension §26 explicitly
  warns against assuming a metric's shape/availability before a real
  provider exists to model it against; that formalization is Phase I/K.
- 7 tests (`tests/test_providers_base.py`): both ABCs reject direct
  instantiation and an incomplete subclass, `DataLevel.satisfies` ordering,
  `TradingCalendar.is_trading_day` (weekend + holiday), and a minimal stub
  provider proving the full interface is actually implementable.

**Phase B — Databento Historical Adapter (extension §152 Phase B)**
- `providers/databento/symbology.py`: the only place Databento-specific
  vendor knowledge lives — a `DatabentoInstrumentMapping` per instrument
  (dataset, raw continuous-contract symbol, `stype_in`, tick size, point
  value, currency, exchange, timezone), pre-seeded for the extension §4
  instrument list (NQ, MNQ, ES, MES, DAX/FDAX/FDXM, YM, MYM) against CME
  Globex (`GLBX.MDP3`) and Eurex (`XEUR.EOBI`). These are best-effort
  defaults, not guaranteed current against Databento's live catalog — an
  unmapped or since-changed symbol fails with a `DATASET_REQUIRED`-style
  `ValueError` rather than guessing, and `register_mapping()` adds/overrides
  an instrument without touching this module's code (extension §4). A
  `DataLevel -> default Databento schema` table (`ohlcv-1m`/`trades`/
  `mbp-10`/`mbo` for L1-L4) supplies a sensible default when `get_historical`
  isn't given an explicit `schema=`.
- `providers/databento/historical.py`: `DatabentoHistoricalMixin` implements
  `get_historical`/`get_instrument_definition`/`get_trading_calendar` — the
  historical two-thirds of `FuturesDataProvider`. `client` is
  dependency-injected (any object shaped like Databento's
  `Historical().timeseries.get_range(...).to_df()`), so every test runs
  without network access or an API key (extension §134/§136); the real
  `databento` package is imported lazily, only when no client is supplied,
  with a clear `RuntimeError` (not a stack trace) when it's missing or no
  `DATABENTO_API_KEY` is set.
  - `get_historical`'s normalization is deliberately scoped: an `ohlcv-*`
    pull is aliased fully onto `data/schema.py`'s canonical
    `REQUIRED_COLUMNS`/`OPTIONAL_COLUMNS` (a drop-in replacement for the
    synthetic generator's output), while L2-L4 schemas (trades, MBP-10,
    MBO) keep their native Databento columns plus a normalized UTC
    `timestamp` — full cross-level normalization into one canonical schema
    is explicitly extension Phase D's job, not this one.
  - `get_trading_calendar` is a documented stub: it returns the correct
    exchange/timezone from symbology but an empty holiday set — a real
    exchange holiday calendar (extension §18) isn't wired in yet.
  - `subscribe_live` (Phase C) is deliberately absent: `DatabentoHistoricalMixin`
    is a plain mixin, not a `FuturesDataProvider` subclass, until Phase C's
    live mixin exists to combine with it — this phase never presents a
    provider with a missing live capability as if it were complete.
- New optional dependency group `databento` in `pyproject.toml`
  (`pip install 'prop-alpha-engine[databento]'`) — the base install stays
  vendor-free, matching extension §2's "core must not depend directly on
  Databento or GEXBOT."
- 22 new tests (`tests/test_databento_symbology.py`,
  `tests/test_databento_historical.py`): every extension §4 instrument
  resolves, unknown/registered-mapping behavior, OHLCV normalization
  (columns, tz-aware timestamp, attrs `source`/`symbol`/`schema`/`dataset`),
  explicit `schema=` override, non-OHLCV passthrough, a missing-column
  error, instrument-definition/trading-calendar metadata, and the two
  "package not installed" / "no API key" failure paths (the latter via a
  fake `databento` module injected into `sys.modules`, since the real
  package genuinely isn't installed in this environment).

**Phase C — Databento Live Adapter (extension §152 Phase C, §12-16)**
- `data/live/` — the provider-agnostic Live Data Engine extension §12
  names, so a future vendor's live adapter reuses these instead of
  reimplementing connection management per vendor:
  - `connection_manager.py`: `ConnectionManager` drives any `Connectable`
    (connect/disconnect) through `DISCONNECTED -> CONNECTING -> CONNECTED
    -> STALE/RECONNECTING -> ...` (extension §13). `BackoffPolicy` gives
    exponential backoff capped at a max delay; `heartbeat_timeout_seconds`
    plus `is_stale()`/`check_health()` implement stale-feed detection —
    any live message counts as a heartbeat (`on_heartbeat()`), not just an
    explicit heartbeat frame. `clock`/`sleep_fn` are injectable so tests
    never depend on real time.
  - `subscription_manager.py`: `SubscriptionManager` keyed on
    `(provider, instrument, schema)` — a second `subscribe_live` for an
    already-active key raises `DuplicateSubscriptionError` rather than
    silently opening a second connection (extension §13's "Non deve
    creare connessioni multiple accidentalmente").
  - `recorder.py`: `LiveMessageEnvelope` carries `timestamp_exchange`,
    `timestamp_provider`, `timestamp_received`, and `timestamp_normalized`
    as four distinct fields — `build_envelope` derives `normalized` as
    exchange -> provider -> received (in that priority) and computes
    `latency_ms` against whichever of exchange/provider is available,
    never overwriting the exchange timestamp with the local one (§15).
    Every timestamp field must be timezone-aware or construction raises
    (§16/§17: UTC is the canonical internal reference). `LiveRecorder`
    records through a pluggable, append-only sink — the default JSONL
    sink mirrors the Hypothesis Ledger/Audit Trail pattern; a Parquet/
    DuckDB sink is Phase G's job.
  - `event_router.py`: `EventRouter` is deliberately in-process, not a
    message broker (extension §126 explicitly says prepare for one later,
    don't add one now) — handlers register for an exact
    `(provider, instrument, schema)` or any wildcard left `None`, and a
    handler matching more than one key still fires once per event.
  - `buffer.py` / `health.py`: `MessageBuffer` is a bounded ring buffer
    computing `messages_per_second`/`sequence_gaps`; `compute_feed_health`
    combines a `ConnectionManager` + `MessageBuffer` into the `FeedHealth`
    snapshot the eventual Data Center dashboard (Phase M) will render —
    one source of truth, not tracked twice.
- `providers/databento/live.py`: `DatabentoLiveMixin` implements
  `subscribe_live` on top of the Live Data Engine above. `live_client` is
  dependency-injected exactly like the historical adapter's `client`, so
  every test runs without network access (extension §134/§136); the real
  `databento.Live` client is imported lazily. Its exact call shape
  (`subscribe`/`add_callback`/`start`/`stop`) follows `databento-python`'s
  documented callback-based usage as best known when this was written —
  flagged in the module docstring as needing verification against the
  installed SDK before real use, since this environment has no network
  access to check it live. `_coerce_timestamp` accepts either a decoded
  `datetime` or a raw nanosecond-epoch int for `ts_event`/`ts_recv`,
  since which one Databento's SDK hands back depends on version/decoding
  options.
- `providers/databento/__init__.py`: `DatabentoProvider` combines
  `DatabentoHistoricalMixin` (Phase B) and `DatabentoLiveMixin` (Phase C)
  into the first genuinely complete `FuturesDataProvider` in this repo —
  confirmed by a test that it satisfies `isinstance(provider, FuturesDataProvider)`.
- 45 new tests across `tests/test_live_*.py` (connection manager, dedup,
  buffer rate/gap math, recorder timestamp policy + JSONL sink, event
  router dispatch/dedup, health snapshot) and
  `tests/test_databento_live.py`/`test_databento_provider.py` (subscribe/
  record/route/duplicate-reject/close via a fake live client, both
  provider-unavailable failure paths, and the combined provider).

**Phase D — Data Normalization (extension §152 Phase D, §6-9)**
- `data/lake.py`: `DataLakePaths` — the extension §6 tier structure
  (`raw`/`normalized`/`curated`/`features`/`outcomes`/`snapshots`/`metadata`),
  each partitioned per extension §11
  (`<tier>/<provider>/<instrument>/<schema>/<date>.parquet` via
  `partition_path`). Defaults to its own `data/lake/` root rather than the
  core pipeline's existing `data/raw`/`data/features` (used by the
  synthetic-data backtester, Phases 1-10) — real-provider ingestion can
  never collide with that pipeline's files. This also supersedes the
  `bronze`/`silver`/`gold` tier names `docs/data.md` reserved back in
  Phase 1 "for later phases once a real ingestion pipeline exists"; those
  directories remain as unused placeholders, and `docs/data.md` now points
  here.
- `data/manifest.py`: `DatasetManifest` — exactly extension §9's YAML
  fields (id/provider/instrument/venue/start/end/timezone/schema/
  granularity/created_at/source_version/sha256), `.build()` computes the
  real SHA-256 of the written file, `.to_yaml()`/`.from_yaml()` round-trip.
- `data/immutable_store.py`: `write_versioned_parquet` refuses to
  overwrite an existing partition file (`DataImmutabilityError`, extension
  §7-8's "Una volta registrato... non deve essere modificato") and appends
  every write to an append-only `dataset_ledger.jsonl` under `metadata/`
  (mirroring the Hypothesis Ledger/Audit Trail pattern) alongside the
  manifest's own YAML file. `next_version_path` names a correction's file
  `*.v2.parquet`, `*.v3.parquet`, ... — chosen explicitly by the caller,
  never automatically.
- `data/normalize.py`: `normalize_frame` is where every provider's
  OHLCV/trade output converges onto one shared schema — bars alias fully
  onto `data/schema.py`'s canonical columns, trades onto a
  `timestamp`/`price`/`size`/`side` schema (extra native columns kept
  alongside), and multi-level book data (MBP-N/MBO, L3/L4) passes through
  unchanged except for the normalized timestamp — collapsing a variable
  number of book levels into one fixed schema is a real design decision
  not yet made, documented as a gap rather than guessed at. Requires the
  timestamp column to already be timezone-aware UTC (extension §16/§17).
- `providers/databento/historical.py` refactored: `_normalize` now only
  does the Databento-specific `ts_event` -> UTC `timestamp` decoding, then
  delegates all column-schema unification to `data.normalize.normalize_frame`
  — fulfilling the promise made in Phase B's docstring that full
  cross-level normalization was Phase D's job. All existing Phase B/C
  tests still pass unchanged (same normalized output).
- 23 new tests (`tests/test_data_lake.py`, `tests/test_dataset_manifest.py`,
  `tests/test_immutable_store.py`, `tests/test_data_normalize.py`):
  directory/partition-path structure, manifest build/round-trip/SHA-256
  correctness, write-once + append-only-ledger + version-bump behavior,
  and bars/trades/book normalization including the timestamp-policy
  validation.

**Phase E — Data Quality Engine (extension §152 Phase E, §19-20)**
- `data/quality_engine.py`: `evaluate_batch_quality` runs the full
  extension §19 checklist against any historical/batch frame (bars,
  trades, or quotes) and returns a graduated 0-100 `DATA_QUALITY_SCORE`
  (§20) instead of a bare pass/fail — a handful of glitches in a large
  dataset costs a small, proportional penalty rather than failing the
  whole dataset outright. Distinct from `data.quality.validate_ohlcv`
  (the original Phase 1 gate the core synthetic-data pipeline still uses
  as a strict must-pass check before any backtest) — this module is for
  the extension's real-provider data and covers checks Phase 1 never
  needed: crossed/locked book, impossible spreads, sequence gaps,
  abnormal timestamp jumps, contract mismatch. Every check is
  column-presence-aware (`CheckResult.applicable`) — a check that doesn't
  apply to the frame it's given (e.g. crossed-book on a bars-only frame)
  contributes nothing to the score rather than fabricating a result for
  data that was never there (§51-52).
  - `evaluate_live_quality` folds Phase C's already-computed
    `data.live.health.FeedHealth` (stale-feed signal) and a
    malformed-payload count into a batch-style report over the same
    window's buffered messages — no live-specific logic is duplicated
    from the Live Data Engine.
  - `is_blocked` implements extension §103's `blocked_on` flags as hard
    stops, independent of the graduated score: a single sequence gap (say)
    blocks regardless of how good the overall score still looks, matching
    the spec's own semantics for that field.
- `data/quality_config.py`: `DataQualityConfig` — exactly extension §103's
  fields (`minimum_score_for_research/paper/live`, `stale_thresholds`,
  `blocked_on`), kept out of the engine module per spec §80/§116, same
  discipline as `config.PaperTradingConfig`/`AgentsConfig`.
- 28 new tests (`tests/test_quality_config.py`, `tests/test_quality_engine.py`):
  every check individually (duplicate/out-of-order/missing timestamps,
  invalid prices, negative volume, crossed/locked book, impossible
  spreads, sequence gaps, abnormal jumps, contract mismatch), severity
  bands at their exact boundaries, not-applicable behavior when required
  columns are absent, live quality folding in stale-feed/malformed-payload,
  and `is_blocked`'s independence from the score.

**Phase F — Local Recorder (extension §152 Phase F, §14/§101)**
- `data/recording_config.py`: `RecordingConfig` — exactly extension §101's
  fields (`enabled`, `canonical_timezone`, `futures_snapshot_frequency`,
  `options_snapshot_frequency`, `outcome_horizons`), with YAML round-trip
  matching `DatasetManifest`'s pattern from Phase D. "Questi sono valori
  iniziali, non dogmi" (§101) — every field is meant to be overridden.
- `data/live/session.py`: `record_live_session` is the piece that was
  missing after Phase C — something that actually drives a bounded
  recording window against a provider's `subscribe_live`, rather than
  only being exercised directly by unit tests. It builds the `LiveRecorder`
  (Phase C) pointed at the correct data-lake `raw` partition (Phase D's
  `DataLakePaths.partition_path`), hands it to a caller-supplied
  `provider_factory` (so this module stays provider-agnostic — the caller
  decides *which* `FuturesDataProvider` gets the recorder), subscribes,
  waits for `duration_seconds` via an injectable `sleep_fn`, and closes
  the subscription in a `finally` block so a `KeyboardInterrupt` mid-sleep
  still leaves the connection cleanly closed. `config.enabled=False` is a
  legitimate no-op — no subscription opened, no file created.
- New CLI command `pae data record` (extension §104): wraps
  `record_live_session` with `DatabentoProvider`. Requires
  `DATABENTO_API_KEY` and the `databento` package to actually run — not
  exercised by the test suite for that reason (§134/§136); verified
  manually end-to-end that it fails with the same clear `RuntimeError`
  Phase B/C already produce when the package/key is missing, rather than
  a bare traceback from deep inside the provider.
- 7 new tests (`tests/test_recording_config.py`, `tests/test_live_session.py`):
  config defaults/YAML round-trip, a fake-provider recording session
  writing the correct partitioned JSONL and message count, handle-close-on-
  interrupt via a raising `sleep_fn`, the non-positive-duration guard, and
  the disabled-config no-op.

## What's not built yet

Everything from Phase G onward. Concretely, per the extension's own §152
order: what remains of the storage layer (Phase G, §6/§10-11) now that
Phase D built the directory structure, manifests, and write-once
enforcement — the DuckDB query layer over the data lake, `pae data ingest`
CLI orchestration (incremental download/resume/retry/dedup), compression
tuning, and actually wiring the `curated`/`features`/`outcomes`/
`snapshots` tiers beyond `raw`/`normalized`; the
GEXBOT adapter (Phase H, §23-27) with `GEXBOT_API_KEY` via environment
variable only, options normalization and the options snapshot/level models
(Phase I, §28-29), futures/options timestamp synchronization (Phase J,
§35-36), the options feature engine including GEX regime classification
and the explicit No-Assumption Principle (Phase K, §29-34/§37/§67-70), the
cross-market `MarketState_t` vector (Phase L, §43-44), the Data Center
dashboard (Phase M, §21/§54/§105-109), the deterministic historical replay
engine (Phase N, §56-58), data-extension live shadow mode with trade
proposals and human feedback capture (Phase O, §59/§75-80), auto-generated
GEX/futures research experiment templates (Phase P, §111-114), and the
mock-provider/CI integration-test suite required to run all of the above
without real API keys or network access (§134-140). Also within Phase B's
own remit but not yet built: a real exchange holiday calendar for
`get_trading_calendar`, and a genuine Databento `Historical` client
integration test behind an opt-in marker (only the dependency-injected
fake-client tests exist today, per §134/§136's CI requirement). Also
within Phase F's own remit but not yet built: `pae options record`
(depends on Phase H's GEXBOT adapter existing first), deriving fixed-
frequency `snapshots`-tier bars from raw tick data at
`RecordingConfig.futures_snapshot_frequency` (the recorder today writes
every native message as-is, not resampled — a real design decision left
to Phase G/L once the data lake's `snapshots` tier is actually wired up),
and `pae data ingest`'s incremental-download/resume/retry semantics for
*historical* backfill (Phase G) as distinct from this phase's *live*
recording.

Do not assume any options-derived directional claim (e.g. "positive GEX is
bullish") is built in anywhere in this extension — extension §37/§160 are
explicit that such relationships must be empirically tested by the research
engine, never hardcoded.
