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

**Phase G — DuckDB/Parquet Storage Layer (extension §152 Phase G, §6/§10-11)**
- `data/lake_query.py`: `query_tier` runs arbitrary SQL over every parquet
  file in a tier/provider/instrument/schema as one DuckDB view (`lake`) —
  a day-partitioned dataset queries exactly like a single file, without a
  caller enumerating files. `list_partitions`/`tier_glob` back the ingest
  resume logic below and are usable standalone (e.g. a future `pae data
  status`). Caught and fixed a real bug while writing this module's own
  tests: DuckDB rejects a prepared parameter inside `CREATE VIEW`
  ("Unexpected prepared parameter. This type of statement can't be
  prepared!") — `query_tier` inlines its (self-constructed, not
  externally supplied) glob pattern as an escaped string literal instead.
  `data.loader.query` (Phase 1, untested and uncalled anywhere in this
  repo) carried the exact same latent bug — fixed there too, with a new
  regression test (`tests/test_loader.py`) now covering a module that
  previously had none.
- `data/ingest.py`: `ingest_historical` implements extension §10's
  incremental historical download — one day at a time via
  `FuturesDataProvider.get_historical`, **resumable** (a day whose raw
  partition already exists is skipped — Phase D's immutability makes
  "already written" unambiguous), **retried** (linear backoff, configurable
  `max_retries`), and **quality-gated**: each day's frame is scored by
  Phase E's `evaluate_batch_quality`/`is_blocked` before being written
  through Phase D's `write_dataset`. A day that trips extension §103's
  `blocked_on` flags is still written — raw data is never silently
  dropped (§7) — but flagged `quality_blocked=True` with its
  `blocked_reasons` for the caller to act on. A day with no data at all
  (holiday/weekend) is `SKIPPED_EMPTY` and nothing is written for it —
  documented as a real, not-yet-closed gap: a re-run currently re-checks
  that day every time rather than remembering it was already confirmed
  empty.
- `data/immutable_store.py` gained `write_dataset` (write-then-hash-then-
  manifest in one call) alongside Phase D's `write_versioned_parquet`
  (which requires a manifest, and therefore a file to hash, to already
  exist) — refactored to share a `_record_manifest` helper; existing
  Phase D tests pass unchanged.
- New CLI command `pae data ingest` (extension §104) wraps
  `ingest_historical` with `DatabentoProvider`. Same "not exercised by the
  automated suite, requires real credentials" caveat as `pae data record`
  — the orchestration logic is tested via a scripted fake provider.
- 19 new tests (`tests/test_lake_query.py`, `tests/test_ingest.py`,
  `tests/test_loader.py`, plus two added to `tests/test_immutable_store.py`):
  glob/partition listing, cross-partition SQL queries (including a custom
  aggregate query and an unfiltered cross-instrument union), the
  no-match error, resume/retry/failure/empty-day/quality-blocked ingest
  scenarios, `write_dataset`'s real-bytes hashing, and the `loader.query`
  regression.
- Deliberately still out of scope: compression tuning, and actually
  populating the `curated`/`features`/`outcomes`/`snapshots` tiers beyond
  `raw`/`normalized` (there's no consumer for them yet — building storage
  for tiers nothing writes to would be exactly the "codice inutile" §3
  warns against elsewhere in this spec).

**Phase H — GEXBOT Adapter (extension §152 Phase H, §23-27)**
- The extension names two different directories for GEXBOT (§3's
  `providers/gexbot/` and §24's `options/gexbot/`, with overlapping file
  names) — resolved the same way earlier phase-boundary overlaps were
  (Phase C/F, D/G): `options/gexbot/` holds the actual GEXBOT-specific
  client/auth/parsing/model/health layer (§24's file list), and
  `providers/gexbot/` holds `GexbotOptionsProvider`, the thin
  `OptionsDataProvider` implementation (extension §2) that composes it —
  the only thing the rest of PARE should ever import from this adapter.
- `options/gexbot/auth.py`: `resolve_api_key` — `GEXBOT_API_KEY` env var
  or an explicit override, never hardcoded (§25), mirroring
  `providers.databento.historical`'s `DATABENTO_API_KEY` pattern exactly.
- `options/gexbot/models.py`: `GexSnapshot` pairs every extension §26
  metric (GEX, DEX, gamma flip, major positive/negative gamma, Vanna,
  Charm, Vomma, skew, options volume, open interest) with its own
  `MetricAvailability` (`AVAILABLE`/`UNAVAILABLE`/`STALE`/`PARTIAL`,
  §26) carrying timestamp/source/freshness — per §27, tracked per metric,
  not once for the whole snapshot.
- `options/gexbot/parser.py`: `parse_snapshot` looks up each metric under
  several plausible field-name aliases (GEXBOT's exact schema isn't
  independently verified in this environment — see `client.py`'s
  docstring) and marks a metric `UNAVAILABLE` (`value=None`) rather than
  guessing when nothing matches — never conflating a genuinely-reported
  `0` with a missing metric (§51-52). A metric older than
  `stale_after_seconds` is `STALE`, not silently treated as live (§27:
  "Non utilizzare dati options vecchi come se fossero real-time").
- `options/gexbot/client.py`: `GexbotClient` wraps GEXBOT's (best-effort,
  unverified) REST API — `session` is dependency-injected exactly like
  Databento's historical/live clients, so every test runs without network
  access (§134/§136); the real `requests` session is imported lazily.
  `start_polling` runs a background daemon thread calling back on an
  interval — GEXBOT's plan/API tier this targets is REST/polling rather
  than websocket push, per this module's own documented best guess; a
  single failed poll doesn't kill the loop.
- `options/gexbot/health.py`: `compute_health` mirrors
  `data.live.health.FeedHealth`'s role for the options side —
  connected/authenticated/last_update/latency/error_rate/data_age/
  available_metrics (extension §90).
- `providers/gexbot/GexbotOptionsProvider`: implements `get_snapshot`
  (parse + return as `dict`, matching Phase A's interface contract),
  `subscribe_live` (delegates straight to `client.start_polling`), and
  `get_instrument_state` (which metrics are currently available). Scope
  discipline (§3's "don't write code nobody can use yet"):
  `get_historical` raises `NotImplementedError` citing §62's own
  acknowledgment that GEXBOT's historical retention is provider-limited;
  `get_levels`/`get_orderflow` raise `NotImplementedError` since parsing
  them into real objects is explicitly Phase K's job (§29-34) — the raw
  client methods exist (`client.get_levels`/`get_orderflow`), only the
  parsing layer is deferred.
- New optional dependency group `gexbot` in `pyproject.toml`
  (`pip install 'prop-alpha-engine[gexbot]'`) — base install stays
  vendor-free, matching Databento's `[databento]` extra.
- 27 new tests (`tests/test_gexbot_{auth,parser,client,health,provider}.py`):
  auth resolution, every metric alias/missing/stale/zero-value case,
  client URL/header construction and error handling, the real (short,
  network-free) polling-thread smoke test, health computation, and the
  provider's ABC conformance plus its three deliberate
  `NotImplementedError`s.

**Phase I — Options Normalization + Snapshot Model (extension §152 Phase I, §28-29)**
- Promoted `AvailabilityStatus`/`MetricAvailability`/`Metric` out of
  `options.gexbot.models` (Phase H) into a new vendor-agnostic
  `options/models.py` — they were already provider-agnostic in spirit
  (every options provider needs per-metric availability, not just
  GEXBOT); `options.gexbot.models` now re-exports them for backward
  compatibility rather than defining a duplicate copy.
- `options/models.py` also adds the extension §28/§29 shapes:
  `OptionsSnapshot` (`timestamp`, `underlying`, every §26 metric, plus
  `orderflow_state` and an `extra: dict[str, Metric] | None` field for
  the "il modello deve essere estensibile" requirement) and
  `OptionsLevel`/`LevelType` (§29's `level` object and its seven type
  values: `GAMMA_FLIP`/`POSITIVE_GAMMA`/`NEGATIVE_GAMMA`/`MAJOR_GAMMA`/
  `DEX_LEVEL`/`VANNA_LEVEL`/`CHARM_LEVEL`).
- `options/normalize.py`: `normalize_gex_snapshot` converts GEXBOT's own
  `GexSnapshot` (Phase H) into the vendor-agnostic `OptionsSnapshot` —
  the same role `data.normalize` plays for futures data (Phase D). The
  snapshot-level `timestamp` (distinct from each metric's own
  `MetricAvailability.timestamp`) defaults to the freshest available
  per-metric timestamp, or `now()` if nothing is available — never left
  unset.
- `options/levels.py`: `extract_levels` turns the level-shaped metrics
  already in a normalized snapshot (gamma flip, major positive/negative
  gamma) into `OptionsLevel` objects, with `distance_from_spot` computed
  against the snapshot's *own* reported spot price — explicitly
  documented as a convenience distance, not the ATR/volatility-normalized,
  futures-price-synced distance extension §30 wants (that needs Phase J's
  synchronization first, and is Phase K's job). `strength` (also named in
  §29) has no defined derivation yet and stays `None` rather than guessed
  at. `DEX_LEVEL`/`VANNA_LEVEL`/`CHARM_LEVEL` extraction is also deferred
  to Phase K.
- `providers/gexbot/GexbotOptionsProvider` updated to route `get_snapshot`
  through the new normalization (so its `dict` output now matches
  `OptionsSnapshot`'s shape, fulfilling the promise made in Phase A's
  `providers/base.py` docstring that this was deferred "until a real
  provider exists to model it against"), and `get_levels` now actually
  works instead of raising `NotImplementedError` (only for
  `GAMMA_FLIP`/`MAJOR_GAMMA` — the rest is still Phase K).
- New CLI command `pae options snapshot` (extension §104): fetches,
  normalizes, and prints one GEXBOT snapshot's metrics and their
  availability status. Same "not exercised by the automated suite,
  requires real credentials" caveat as `pae data record`/`pae data
  ingest` — verified manually that it fails at the expected `No GEXBOT
  API key` boundary rather than a bare traceback.
- 16 new tests (`tests/test_options_models.py`, `test_options_normalize.py`,
  `test_options_levels.py`) plus one existing GEXBOT provider test
  updated from "raises NotImplementedError" to actually verifying
  `get_levels`' new output.

**Phase J — Futures/Options Synchronization (extension §152 Phase J, §35-36)**
- `sync/config.py`: `SyncConfig.max_time_difference_ms` — extension §35's
  own worked example (500ms) as the default, not a hardcoded assumption.
- `sync/cross_market.py`: `find_nearest_snapshot` does the actual
  nearest-neighbor timestamp matching a single futures moment needs,
  returning `(None, None)` — not the nearest snapshot regardless of
  distance — when nothing falls inside the tolerance (§35 says associate
  *within a window*, not unconditionally). `synchronize_snapshot` wraps
  it into `CrossMarketState` (§36's object) for the online/live shape —
  one futures bar paired with the freshest options context (Phase O's
  eventual shadow mode). `synchronize_frame` is the historical/research
  shape Phase K's conditional-EV-by-options-state work needs: a vectorized
  `pandas.merge_asof` nearest-as-of join of a whole futures bar frame
  against a list of options snapshots, adding `options_*` columns plus a
  `sync_time_difference_ms` column so how well-aligned each match actually
  was is never hidden; a futures row with nothing in tolerance gets `NaN`
  in the `options_*` columns, never a fabricated pairing.
- `CrossMarketState.regime` is passed straight through from whatever the
  futures bar's own already-computed `regime_rule` column says (the core
  Regime Engine, Phases 1-10) — not re-derived here. `market_state` (the
  full `MarketState_t` vector) stays `None`; that's Phase L's job.
- Both timestamp inputs are required to be timezone-aware UTC (extension
  §16/§17) — a naive datetime raises rather than being silently assumed
  UTC.
- 11 new tests (`tests/test_sync_cross_market.py`): nearest-match
  selection, the outside-tolerance/empty-list/naive-timestamp cases for
  both the single-pairing and frame-level APIs, `regime` pass-through, and
  the reported time-difference values.

**Phase K — Options Feature Engine (extension §152 Phase K, §29-34/§37/§67-70)**
- `options/features.py`: `classify_gex_regime`/`classify_gex_regime_series`
  (§31) label GEX state — `STRONG_POSITIVE_GAMMA` through
  `STRONG_NEGATIVE_GAMMA`/`UNKNOWN` — strictly from a *normalized* (z-score,
  via `normalize_gex_series`) value, never a raw GEX number, per §67's
  warning that GEX's scale is instrument/notional-dependent. No-Assumption
  Principle (§37): these are state labels only — nothing here claims what
  a regime means for price direction; `options.conditional_ev` is where
  that gets tested empirically, not assumed. `compute_dex_state` (§32)
  gives magnitude/sign/change/acceleration; `dex_concentration` (also
  named in §32) is left as an honest all-`NaN` column — it needs a
  per-strike DEX breakdown GEXBOT's snapshot endpoint doesn't provide.
  `compute_gex_dynamics` (§33) is plain ΔGEX/Δ²GEX differencing, no
  interpretation attached.
- `options/distance.py`: `compute_distance_features`/`compute_level_distances`
  complete extension §30's distance-to-level features (absolute/
  percentage/ATR-normalized/volatility-normalized) against the *synced
  futures price* (Phase J) — the proper version of the "convenience
  distance" `options.levels.extract_levels` (Phase I) deliberately left
  as a placeholder, computed only against the options snapshot's own spot.
- `options/conditional_ev.py`: `conditional_ev_by_gex_regime` is the
  options-side twin of `regimes.conditional_ev.conditional_ev_by_regime`
  (core spec §14) — same join/aggregate pattern exactly, over a
  `sync.cross_market.synchronize_frame` output instead of the futures
  feature frame, answering extension §69's "EV(alpha|GEXState)."
- `options/incremental_value.py`: `compute_incremental_value_score`
  implements extension §70's Options Incremental Alpha Score — rewards
  OOS EV/stability/calibration/drawdown/Payout Utility improvement,
  penalizes complexity/data/latency/provider dependency, and is explicit
  in its own docstring that it's a transparent first-pass heuristic, not
  a fitted or validated model (there's no labeled "was this worth it"
  dataset to calibrate against). A non-positive EV delta always resolves
  to `NON_ESSENTIAL` regardless of every other signal, matching §40's
  "Does it add value? If not: FEATURE = NON-ESSENTIAL."
- 26 new tests (`tests/test_options_{features,distance,conditional_ev,
  incremental_value}.py`): z-score normalization edge cases (too few
  observations, zero variance), every regime boundary, DEX
  magnitude/sign/change/acceleration and the honest `NaN` concentration
  column, GEX delta/delta², all four distance normalizations including
  the zero-price/zero-ATR/zero-vol guards, conditional-EV grouping/
  sorting/empty/missing-column/unmatched-trade cases, and the incremental
  value score's recommendation logic including the "positive EV but high
  penalty still marginal" and "improvements everywhere but negative EV
  still non-essential" cases.

**Phase L — Cross-market Market State Vector (extension §152 Phase L, §43-44)**
- `market_state/location.py`: the Location Engine (§43). `build_market_location`
  computes, for a given price/timestamp, the distance to every relevant
  futures-side coordinate present on the futures bar (VWAP, volume-profile
  POC/VAH/VAL, prior-day volume-profile POC/VAH/VAL, prior-day high/low,
  opening-range high/low) plus every options level passed in (typically
  `options.levels.extract_levels`'s output for the synced snapshot). Reuses
  `options.distance.compute_distance_features` (Phase K) for both sides —
  that function only needs a price and a level value, so despite living in
  the `options` package it's the correct shared primitive rather than a
  duplicated formula. A level whose futures-bar column is missing or
  `None`/`NaN` is simply absent from `MarketLocation.distances`, never a
  fabricated distance. `MarketLocation.as_dict()` prefers ATR-normalized
  distance, falling back to percentage distance when no ATR was supplied.
- `market_state/vector.py`: the Market State vector itself (§44).
  `build_market_state` assembles the 10-component `MarketState` dataclass —
  price/volume/volatility/liquidity/orderflow/profile/session/regime/
  options/event state — by extracting known column names from a
  `futures_bar` dict (a column that isn't present, or is `None`/`NaN`, is
  simply omitted from that component); folding a `MarketLocation`'s
  futures-category distances into `profile_state` and options-category
  distances into `options_state`; flattening an `OptionsSnapshot`'s 12
  metrics (value when available, plus an always-present `_status` key) into
  `options_state`; and passing `event_state` through as-is, defaulting to
  `{}` — no Event Engine exists anywhere in this codebase yet, an honest,
  documented gap rather than an invented one. `build_market_state_from_cross_market`
  is a convenience wrapper pulling `.futures`/`.options`/`.timestamp` off a
  Phase J `CrossMarketState`; `attach_market_state` returns a *new*
  `CrossMarketState` (via `dataclasses.replace`, since it's frozen) with
  `.market_state` populated from `MarketState.as_flat_dict()`
  (`"{component}.{key}"` namespaced). This is deliberately one-directional:
  `market_state` imports `sync`, `sync` never imports `market_state` — so
  `CrossMarketState.market_state` (added in Phase J) stays `None` until a
  caller explicitly calls `attach_market_state`; nothing upstream fabricates
  a state vector on its own. `MarketState.completeness` is a coarse,
  honestly-labeled "fraction of the 10 components with at least one value"
  signal, not a data-quality claim.
- 19 new tests (`tests/test_market_state_{location,vector}.py`): present vs.
  missing/NaN futures columns, options levels included/skipped by value,
  ATR-normalized vs. percentage-fallback distance, `as_dict()`/`get()`
  behavior, per-component extraction from a futures bar including the
  unrelated-column-is-ignored case, NaN exclusion, options-snapshot
  flattening (available value + status, unavailable metric has no value key
  but keeps its status key), location-distance category splitting into
  `profile_state` vs. `options_state`, `completeness`, `as_flat_dict()`
  namespacing, and `attach_market_state` producing a new instance without
  mutating the original `CrossMarketState`.

**Phase M — Data Center Dashboard (extension §152 Phase M, §21/§54/§105-109)**
- `data_center/config.py`: `DataCenterConfig` — the two GEXBOT-health
  thresholds (`options_error_rate_warning`, `options_data_age_warning_
  seconds`) nothing else in the codebase already owns; futures staleness
  reuses `data.quality_config.StaleThresholds.futures_seconds` and sync
  tolerance reuses `sync.config.SyncConfig.max_time_difference_ms` rather
  than duplicating either.
- `data_center/status.py`: `DataCenterStatus` + `assemble_data_center_status`
  — a pure aggregator combining whatever health/status objects a caller
  already has: `data.live.health.FeedHealth` (§19-21, futures feed),
  `options.gexbot.health.GexbotHealth` (§90, options feed),
  `data.quality_engine.DataQualityReport` (§19-20/§54), `market_state.
  vector.MarketState.completeness` (§44), and a sync time-difference in
  ms (§35-36). Every input is independently optional; an input that
  wasn't supplied contributes no severity to `overall_status` at all —
  never assumed healthy, never assumed broken. `overall_status` is the
  worst of `UNKNOWN`/`OK`/`DEGRADED`/`CRITICAL` found across whatever was
  actually supplied: a disconnected/failed futures feed, an unauthenticated
  options feed, or a `CRITICAL`-severity quality report each force
  `CRITICAL`; reconnecting/stale connection states, elevated sequence
  gaps or message age, elevated options error rate/data age/no available
  metrics, `WARNING`-severity quality, or a sync gap beyond
  `SyncConfig.max_time_difference_ms` each force `DEGRADED`. Each
  contributing condition is recorded verbatim in `issues` so the rendered
  report never just says "something's wrong" without saying what.
- `data_center/render.py`: `render_status_markdown` renders a
  `DataCenterStatus` as plain markdown — the same convention `reporting/`
  already uses for the core engine's reports, not a separate web
  dashboard dependency (no web framework is in `pyproject.toml`, and none
  was added for this). A component that is `None` prints "not available"
  rather than fabricating a section.
- `pae data-center status [--underlying TICKER]`: assembles and prints the
  status. Honest about what a single CLI invocation can actually compute:
  the futures feed and data quality sections always print "not
  available" here, since they need state from a separate long-running
  process (`pae data record`'s `ConnectionManager`/`MessageBuffer`, or a
  `DataQualityReport` already produced by `pae data ingest`) that this
  one-shot command doesn't have access to — only the options feed (a
  single synchronous GEXBOT poll) is actually populated. Requires
  `GEXBOT_API_KEY`/`requests` when `--underlying` is given.
- 23 new tests (`tests/test_data_center_{status,render}.py`): every
  severity-triggering condition on both feeds and on quality individually
  and combined (worst-status-wins), sync gap within/beyond tolerance, the
  all-`None`/`UNKNOWN` case, and the markdown renderer's per-section
  content including the not-available fallback, failed-checks listing,
  and issues listing.

**Phase N — Deterministic Historical Replay Engine (extension §152 Phase N, §56-58)**
- `replay/reader.py`: two sources converging on the same
  `data.live.recorder.LiveMessageEnvelope` shape used by the Live Data
  Engine (Phase C). `read_jsonl_envelopes` is the exact inverse of
  `data.live.recorder._jsonl_sink` — replays a recorded live session
  (`pae data record`, Phase F) back as envelopes. `dataframe_to_envelopes`
  wraps an already-ingested historical bar frame (e.g. `data.lake_query.
  query_tier`'s output, Phase G) as envelopes instead, so a handler
  written once against the live envelope/`EventRouter` shape works
  unmodified against real historical bars too — no second, historical-only
  code path. There is no real "received at" moment for a historical bar,
  so `timestamp_exchange`/`timestamp_received`/`timestamp_normalized` are
  all honestly set to the bar's own timestamp (not a fabricated arrival
  time) and `latency_ms` stays `None` (nothing to measure it against);
  `sequence` is the row's position, giving replay a deterministic
  tie-break for same-timestamp rows. Naive timestamps raise, per extension
  §16-17.
- `replay/engine.py`: `replay_envelopes` is the actual replay driver.
  Determinism is its job, not the caller's — it sorts by
  `(timestamp_normalized, original position)` regardless of input order,
  so the same envelope collection replays identically no matter what
  order it arrived in (the whole point of "deterministic" replay, not
  just playback). `speed=None`/`<=0` (the default) dispatches every
  envelope immediately with no pacing — the right mode for backtesting/
  shadow-mode research where only event *order* matters; `speed=1.0`
  reproduces the original wall-clock cadence between consecutive
  envelopes, `speed=2.0` plays it back twice as fast, and so on. A
  negative inter-event gap (out-of-order source data) is clamped to zero
  rather than raising — replay plays back what's there; validating it is
  `data.quality_engine`'s job on the way in, not this module's.
- `pae replay run [--tier raw] [--speed 0]`: replays an ingested lake
  partition through `dataframe_to_envelopes` + `replay_envelopes`,
  dispatched via a real `data.live.event_router.EventRouter` bound to a
  print handler. Needs a real ingested lake partition (`pae data
  ingest`), so it isn't exercised by the test suite itself; the
  reader/engine logic it calls into is (smoke-tested manually against a
  `write_dataset`-written partition during development).
- 20 new tests (`tests/test_replay_{reader,engine}.py`): JSONL round-trip
  through a real `LiveRecorder`, file-order preservation, blank-line
  skipping, DataFrame-to-envelope conversion including the missing-column
  and naive-timestamp error cases and the empty-frame case,
  order-independent deterministic dispatch, position tie-break for
  identical timestamps, every `speed` pacing case (`None`/`0`/`1.0`/`2.0`,
  first-envelope-never-sleeps, negative-gap-clamped), and `ReplayResult`'s
  event count/timestamp bounds for both populated and empty input.

**Phase O — Live Shadow Mode (extension §152 Phase O, §59/§75-80)**
- `live_shadow/proposal.py`: `TradeProposal` — a logged, human-reviewable
  record of what the system would propose, never an executed or
  executable order (extension §132/§162, already the top-level scope
  statement this whole doc opens with). `make_proposal` is the only
  constructor; it stamps a deterministic `proposal_id` (`utils.hashing.
  hash_dict` over the fields that make a proposal unique) and, when given
  a `market_state.vector.MarketState`, attaches its flattened snapshot
  (`as_flat_dict()`) for later audit — otherwise an empty dict, never a
  fabricated one. `proposal_from_record` is the inverse of
  `dataclasses.asdict`, reconstructing a real `TradeProposal` from a
  ledger row (needed anywhere a caller reads proposals back out to act on
  them, e.g. the CLI review command below).
- `live_shadow/feedback.py`: `apply_feedback` is the single place a
  proposal moves out of `PENDING` — always through an explicit,
  attributed human decision (`reviewer`, optional `rationale`). It
  refuses to move a proposal that's already been decided (extension §76:
  a recorded decision is never silently revised); a reviewer who wants to
  change their mind reviews a new proposal instead.
- `live_shadow/ledger.py`: `LiveShadowLedger`, an append-only JSONL store
  mirroring `discovery.hypothesis.HypothesisLedger`/`agents.audit.
  AuditTrail`'s exact pattern (extension §76-80: never rewrites or
  deletes a prior entry). Both proposals and feedback share one file,
  tagged by a `"kind"` field, so the ledger reads back as a single
  chronological log of everything that happened to a proposal.
- `live_shadow/engine.py`: `run_live_shadow_session` ties a market-state
  stream — fed by a live subscription (Phase C) or Phase N's
  deterministic replay, via `market_state.vector.build_market_state` — to
  a caller-supplied `proposal_generator` and the ledger. It owns none of
  the trading logic itself (no strategy is wired in here, and none is
  claimed to be); it only guarantees every non-`None` proposal a
  generator returns gets logged before the session moves on, so nothing
  proposed goes unrecorded.
- `pae live-shadow list [--status ...]` / `pae live-shadow decide
  --proposal-id ... --decision APPROVED|REJECTED --reviewer ...`: the
  human review loop over the ledger. `decide` re-checks the ledger's own
  feedback records (not just the in-memory proposal) before applying a
  decision, since a `PROPOSAL` row is never rewritten in place — the
  ledger's feedback history is the actual source of truth for whether a
  proposal has already been decided.
- 33 new tests (`tests/test_live_shadow_{proposal,feedback,ledger,
  engine}.py`): deterministic/differentiated proposal IDs, naive-timestamp
  and invalid-direction rejection, market-state snapshot attachment
  (present and absent), the full ledger round-trip (`asdict`/`json.dumps`/
  `json.loads`/`proposal_from_record`), feedback's already-decided guard
  and non-mutation of the original proposal, append-only behavior across
  separate `LiveShadowLedger` instances pointed at the same file, and the
  session engine's counting/logging/empty-stream behavior.

**Phase P — GEX/Futures Research Experiment Templates (extension §152 Phase P, §111-114)**
- `research_templates/gex_market_frame.py`: `enrich_synced_frame_with_gex_features`
  attaches the GEX/DEX state columns the condition library below needs —
  `options.features.classify_gex_regime_series`/`compute_dex_state`
  (Phase K) applied to a `sync.cross_market.synchronize_frame` output's
  `options_gex`/`options_dex` columns. An unsynced bar (already `NaN` in
  every `options_*` column by `synchronize_frame`'s own contract, Phase J)
  classifies honestly as GEX regime `UNKNOWN` and `NaN` DEX state — both
  functions already handle that, so no extra handling is needed here.
- `research_templates/conditions.py`: `GEX_CONDITION_LIBRARY`, built on
  the exact same `discovery.conditions.Condition` shape the core
  Discovery Engine's `CONDITION_LIBRARY` uses (Phase 7). Every condition
  is a state label only, never a directional claim (extension §37's
  No-Assumption Principle, still binding: "GEX regime is currently
  POSITIVE_GAMMA" is not "price will therefore move up"). DEX conditions
  use sign only (`dex_sign_positive`/`_negative`), not a raw magnitude
  threshold — DEX has no established normalization the way GEX does
  (`options.features.normalize_gex_series`), and an arbitrary magnitude
  cutoff would be exactly the scale-dependent absolute threshold
  extension §67 warns against.
- `research_templates/templates.py`: `generate_gex_futures_templates`
  reuses `discovery.setup_generator.GeneratedStrategy` unmodified — it
  only needs a `list[Condition]` and a direction, and has no idea one of
  its two conditions reads options-derived columns. Deliberately a cross
  product (every futures condition paired with every GEX/DEX condition,
  both directions), not the core engine's flat combinatorial pool
  (`generate_candidate_setups`, which would also produce futures-only or
  GEX-only pairs from a merged library) — Phase P's whole point is a
  futures setup explicitly conditioned on GEX/DEX state.
- `research_templates/discovery.py`: `hypothesis_from_gex_template` +
  `run_gex_futures_discovery` mirror `discovery.pipeline._hypothesis_from_
  candidate`/`run_discovery`'s exact shape (extension §20's "no backtest
  without a logged hypothesis" applies here too) but narrower —
  no symbolic-regression scan, since that stays the core Discovery
  Engine's own concern over the futures feature set, not duplicated here.
  Every candidate is logged to the same `discovery.hypothesis.
  HypothesisLedger` used by the core engine, survivor or not.
- `pae research gex-templates --enriched-frame-path ... --oos-start-day
  ...`: generates, screens, and logs cross-market templates from an
  already-prepared enriched frame. Honestly scoped to what this repo
  currently has: there is no built pipeline that produces a synced,
  enriched futures+options frame end-to-end on its own yet — GEXBOT has
  no historical endpoint (extension §62's limitation, Phase H) and no
  options-side recorder exists (Phase F's own noted gap below), so
  building that frame today means combining `pae data ingest`'s output
  with independently-accumulated options snapshot history via
  `sync.cross_market.synchronize_frame` + `enrich_synced_frame_with_gex_
  features` yourself. Not exercised by the test suite for that reason;
  the condition library, template generator, and discovery orchestration
  it calls into are.
- 29 new tests (`tests/test_research_templates_{gex_market_frame,
  conditions,templates,discovery}.py`): enrichment's required-column
  errors and column preservation/non-mutation, every GEX/DEX condition's
  firing behavior against a hand-built frame, cross-product coverage
  (every candidate has exactly one futures + one GEX condition, both
  directions, deterministic per seed, `max_candidates` cap respected),
  and the discovery orchestration's hypothesis auto-fill (including the
  zero-trade/RETIRED case) plus its full pipeline over a synthetic-OHLCV-
  derived feature frame with seeded synthetic options columns standing in
  for real synced data (never presented as real market evidence, same
  discipline `paper.shadow`'s docstring already commits to for the core
  engine's own shadow mode).

**Mock Providers + CI Integration Tests (extension §134-140, the roadmap's final item)**
- `providers/mocks.py`: `MockFuturesDataProvider`/`MockOptionsDataProvider`,
  full implementations of `FuturesDataProvider`/`OptionsDataProvider` — no
  API keys, no `databento`/`requests` packages, no real network calls.
  Every real adapter already accepted an injected client/session so its
  own unit tests never needed these; what was missing was a *shared*,
  importable pair usable across phases instead of each test file
  hand-rolling its own narrow local fake. `MockOptionsDataProvider`
  deliberately routes through the real GEXBOT parsing pipeline
  (`options.gexbot.parser.parse_snapshot`, `options.normalize.
  normalize_gex_snapshot`, `options.levels.extract_levels`) rather than
  building `OptionsSnapshot` objects directly, so a test using it
  exercises the same parsing/normalization code a real payload would.
  `get_orderflow` still raises `NotImplementedError`, matching
  `GexbotOptionsProvider`'s own honesty — order-flow parsing isn't built
  anywhere in this repo, so the mock doesn't fabricate data for a feature
  that doesn't exist. `subscribe_live` on both mocks pushes a
  deterministic, finite burst of messages synchronously rather than
  spinning a background thread — a mock exists to be fast and
  deterministic in CI, not to simulate real-time timing. Everything both
  mocks produce is seeded, reproducible, and clearly synthetic — never
  presented as real market evidence, the same discipline `data.synthetic.
  generate_synthetic_ohlcv`/`paper.shadow` already commit to elsewhere.
- `tests/test_mock_providers.py` (18 tests): ABC compliance, schema/
  timezone correctness, determinism per seed, `subscribe_live` delivery,
  `get_levels`/`get_instrument_state`/`get_orderflow`'s honest
  `NotImplementedError`, and `generate_snapshot_sequence`'s time-ordering.
- `tests/test_integration_data_extension.py` (6 tests): wires the mocks
  through the real cross-phase pipeline end to end — ingest (Phase G) ->
  sync (Phase J) -> GEX/DEX enrichment (Phase P) -> market state (Phase
  L) -> live shadow proposals logged to a real ledger (Phase O) ->
  record-then-deterministically-replay a live session (Phases C/F/N) ->
  a full GEX/futures discovery run logging every candidate to the
  Hypothesis Ledger (Phase P). This is deliberately not a re-test of any
  single phase's own unit behavior (each already has one) — it exists to
  catch what per-phase unit tests can't: that the pieces actually connect
  (matching column names, matching timestamp conventions, no
  silently-dropped data) end to end. Building it caught one real bug: the
  futures mock's live payload originally leaked a raw `pandas.Timestamp`
  into the message payload, which failed at `LiveRecorder`'s JSONL sink
  (`json.dumps` doesn't serialize pandas/`datetime` objects) — fixed by
  isoformat-stringifying the payload's timestamp field, matching what a
  real wire-format JSON message would actually carry.
- `.github/workflows/ci.yml`: runs the full test suite (`pytest -q`) on
  every push and pull request, on Python 3.11 and 3.12 — nothing in it
  needs a secret or external service, since every real-network-requiring
  path in this repo (`pae data record`/`ingest`, `pae options snapshot`,
  `pae data-center status`, `pae replay run`) is already dependency-
  injectable and covered by unit tests with fakes, not exercised directly
  by CI.
- 627 tests passing total. This closes out the extension's entire §152
  roadmap — Phase A through Phase P, plus this final mock-provider/CI
  phase.

## What's not built yet

Everything the extension's own phase order (§152) doesn't cover, plus a
few gaps each phase's own writeup above already flagged as it went. Also
within Phase B's own remit but not yet built: a real exchange holiday calendar for
`get_trading_calendar`, and a genuine Databento `Historical` client
integration test behind an opt-in marker (only the dependency-injected
fake-client tests exist today, per §134/§136's CI requirement). Also
within Phase F's own remit but not yet built: `pae options record`
(Phase H's GEXBOT adapter now exists to build it against, but the CLI
command itself isn't wired up), deriving fixed-
frequency `snapshots`-tier bars from raw tick data at
`RecordingConfig.futures_snapshot_frequency` (the recorder today writes
every native message as-is, not resampled — a real design decision left
to a future pass once the data lake's `snapshots` tier is actually wired up),
and `pae data ingest`'s incremental-download/resume/retry semantics for
*historical* backfill (Phase G) as distinct from this phase's *live*
recording.

Do not assume any options-derived directional claim (e.g. "positive GEX is
bullish") is built in anywhere in this extension — extension §37/§160 are
explicit that such relationships must be empirically tested by the research
engine, never hardcoded.
