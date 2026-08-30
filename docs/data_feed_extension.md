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

## What's not built yet

Everything from Phase C onward. Concretely, per the extension's own §152
order: the Databento live adapter with connection management (Phase C,
§12-16), data normalization into the canonical schema with raw immutability
and dataset manifests (Phase D, §6-9), the data quality engine and 0-100
`DATA_QUALITY_SCORE` (Phase E, §19-20), the local live recorder (Phase F,
§14-15), the partitioned Parquet/DuckDB storage layer (Phase G, §6/§10-11),
the GEXBOT adapter (Phase H, §23-27) with `GEXBOT_API_KEY` via environment
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
fake-client tests exist today, per §134/§136's CI requirement).

Do not assume any options-derived directional claim (e.g. "positive GEX is
bullish") is built in anywhere in this extension — extension §37/§160 are
explicit that such relationships must be empirically tested by the research
engine, never hardcoded.
