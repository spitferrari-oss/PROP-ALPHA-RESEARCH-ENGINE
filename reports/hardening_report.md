# PARE Hardening & Production Readiness Pass — Final Report

- Baseline commit: `362ffa9cdc9dce9e3d4550e17456071ceb4c3238`
- Final commit: `7fbdfd626bab4c0c6513b39e0b3bf90a5fc9da26`
- Branch: `claude/prop-alpha-research-engine-ycwng9`
- Baseline audit: `reports/hardening_baseline.md`

Classifications used throughout, exactly as specified: **READY**, **NOT
READY**, **BLOCKED**, **NOT VERIFIED**, **NOT IMPLEMENTED**.

## Executive Summary

This pass turned the repository from a broad, working vertical slice
into a governed one: every command that does real research work now
verifies a machine-readable Research Constitution before running; a
real-time no-trade gate and daily state machine exist as explicit,
tested abstractions distinct from the backtest-only stop-trading policy
that already existed; the GEXBOT and Databento adapters can no longer
silently imply they've been verified against a real provider — a
dedicated capability-check command exists and honestly reports
`NOT_VERIFIED`/`UNAVAILABLE` in this network-less environment rather
than a fabricated pass; a genuine live-shadow pipeline (provider → market
state → no-trade → alpha → ledger) exists alongside, not instead of, the
original OOS-replay shadow mode; execution stays structurally disabled
behind a single choke point; and the offline test suite (776 tests) is
reproducible, marker-partitioned, and was verified end to end, including
a deliberate Constitution-tampering test against temp-file fixtures (the
real Constitution files were never modified for testing).

No real network call was ever made. No real API key was ever used. No
real order was ever sent, simulated as live, or made possible. Every
claim below distinguishes what was built and tested offline from what
remains genuinely unverified because this environment has no network
access or provider credentials.

## What was fixed

- **Blocker A (machine-enforced Constitution)**: `config/
  research_constitution.yaml` + `.lock.yaml`, `governance/constitution.py`
  (load/hash/verify/assert API), `pae constitution show/hash/verify/
  status`, wired as a hard pre-check into `pae research
  full-run`/`discover`/`gex-templates` (the three commands in this
  repository that actually do research work — see the deviation note
  below).
- **Blocker E (no-trade gate)**: `trading/no_trade.py` —
  `TradeEligibility`/`evaluate_trade_eligibility`/`should_trade`, all 12
  named `NoTradeReason` values, configurable thresholds, foundational
  checks (`NO_EDGE`, `LOW_DATA_QUALITY`) fail closed on missing data.
- **Daily state machine**: `prop/daily_state.py` — an explicit
  `DailyState` enum and transition graph, distinct from `prop/
  simulator.py`'s account tracking and `risk/stop_trading.py`'s backtest
  filter.
- **Blocker G (GEXBOT honesty)**: `providers.base.ProviderContractState`,
  `options/gexbot/capability.py`'s real one-call contract check, `pae
  options verify-provider`/`pae options historical`, `config/
  providers.yaml` + `config/options_data.yaml`, `.env.example`.
- **Options recorder**: `options/recording/{collector,recorder,
  manifest}.py` — per-metric immutable records, append-only, missing ≠
  zero preserved end to end.
- **Blocker D scaffold (execution)**: `execution/{base,gateway,paper}.py`
  — `LIVE_EXECUTION_ENABLED = False`, a single choke point
  (`get_gateway`) that only ever returns the paper adapter.
- **Blocker C (genuine live shadow)**: `live_shadow/session.py` +
  `pae live-shadow start/status/stop`, wiring `providers.base.
  FuturesDataProvider` → `market_state.vector.build_market_state` →
  `trading.no_trade` → a caller-supplied alpha → `live_shadow.ledger` —
  distinct from, and does not replace, the existing OOS-replay
  `paper.shadow`.
- **Cross-market freshness**: `CrossMarketState` gained `sync_quality`/
  `freshness_seconds`/`data_quality` (all optional, backward compatible).
- **Data Center honesty**: `DataCenterStatus.data_source`
  (REAL/REPLAY/SYNTHETIC/MOCK/NOT_CONNECTED), visibly flagged whenever
  it isn't REAL.
- **Research state integrity**: `governance/research_state.py` — a
  `HYPOTHESIS`→...→`LIVE` transition graph that rejects any skipped gate.
- **Audit provenance**: `AuditEntry` gained
  `constitution_id`/`version`/`hash`/`git_commit`.
- **Statistics**: `statistics/parameter_sensitivity.py` (distinct from
  cost sensitivity) and `statistics/leakage.py` (structural checks,
  scoped honestly — see its own docstring for what it does and does not
  detect).
- **Test infrastructure**: `pae system doctor`/`pae system test`, pytest
  markers (`unit`/`integration`/`network`/`provider`/`live`/`slow`),
  `scripts/bootstrap_dev.{ps1,sh}`, `docs/development.md`.
- **Documentation**: `docs/constitution_amendment_process.md`, `docs/
  roadmap_live.md`, README capability table, this report.

## What was verified (actually run, not just written)

- `pytest -q`: **776 passed, 0 failed, 0 errors.**
- `pytest -m "not network and not live" -q`: **776 passed** — identical
  to the full suite, because zero tests currently carry `network`/`live`/
  `provider` markers (every provider adapter is dependency-injected and
  tested via fakes/mocks; see baseline report).
- `pae system doctor`: all 9 core dependencies report INSTALLED with
  real version numbers; both optional dependencies (`databento`,
  `requests`) correctly report NOT INSTALLED; overall PASS.
- `pae system test`: UNIT and INTEGRATION groups PASS; PROVIDER/NETWORK/
  LIVE groups correctly report BLOCKED (0 tests collected for those
  markers) rather than a fabricated PASS or an incorrect FAIL.
- **Constitution enforcement, end to end**: manually appended a line to
  `config/research_constitution.yaml`, ran `pae research full-run`, and
  confirmed it printed `STATUS: CONSTITUTION INVALID` / `RESEARCH
  EXECUTION BLOCKED` with the exact hash-mismatch reason and exited
  non-zero; restored the file immediately and re-verified clean
  (`pae constitution verify` → `CONSTITUTION VALID`). The real
  Constitution files were never left modified.
- **Constitution test isolation**: `tests/test_governance_constitution.py`
  exercises every tampering scenario (missing lock, hash mismatch,
  version mismatch, ID mismatch, malformed YAML) against `tmp_path`
  fixtures — never the real `config/research_constitution*.yaml`.
- **Reproducibility**: ran `pae research full-run --config
  configs/example.yaml --n-days 60 --fast` twice, independently, into
  separate output directories. The two generated reports are **byte-
  identical** after normalizing only the experiment ID and timestamp
  (which are expected to differ per invocation) — same seed, same
  config, same dataset, same code, same Constitution → same result.
- **Replay smoke test**: wrote a real 3-row partition via `data.
  immutable_store.write_dataset`, ran `pae replay run` against it, and
  confirmed all 3 events dispatched in correct, deterministic timestamp
  order.
- **Live shadow smoke test**: `pae live-shadow start` (mock provider) →
  `STOPPED`, `n_events=5`, `n_proposals=0` (correct — no alpha wired in
  by default, `NO_EDGE` blocks every bar); `pae live-shadow status`
  correctly read the persisted state back; `pae live-shadow stop`
  correctly marked it `STOPPED`.
- **Provider smoke test** (`pae options verify-provider`): run in this
  environment. Result: **NOT_RUN — provider credentials/network
  unavailable**, reported by the command itself as `Authentication: FAIL`
  / every metric `NOT_CHECKED` / `Provider status: UNAVAILABLE`, exactly
  the correct, expected outcome here — not simulated, not skipped
  silently, and not reported as a success.

## What remains unverified (honestly, and why)

- **Databento historical/live adapters**: real code, tested only via
  dependency-injected fakes. The adapters' exact call shape against the
  real `databento-python` SDK is flagged in their own module docstrings
  as unverified — this environment has no network access and does not
  have the `databento` package installed. **Status: NOT VERIFIED.**
- **GEXBOT adapter**: same reason. `options/gexbot/parser.py`'s
  `_FIELD_ALIASES` were never checked against a real GEXBOT response.
  `pae options verify-provider` exists specifically to close this gap
  the moment real credentials/network are available — it was not run
  successfully in this pass because neither exists here. **Status: NOT
  VERIFIED.**
- **Live shadow at sustained scale**: the pipeline wiring is real and
  tested against the mock provider; it has never run against a real,
  sustained live connection, and no real alpha is wired into the default
  CLI path. **Status: PARTIALLY IMPLEMENTED / NOT VERIFIED at scale.**
- **Options recorder against a real feed**: tested against synthetic
  `OptionsSnapshot` fixtures only. **Status: NOT VERIFIED against a real
  feed.**

## Known deviation from the literal task text

The hardening task names `pae strategy backtest/validate/discover`,
`pae portfolio optimize`, and `pae prop simulate` as the commands to
Constitution-gate. None of those exist as separate CLI commands in this
repository — backtesting, discovery, and prop simulation all happen
inline inside `pae research full-run`/`discover`/`gex-templates`, and no
standalone `strategy`/`portfolio`/`prop simulate` command was ever built
in the prior 10-phase + extension work. Per this task's own
non-negotiable rule ("avoid duplicating existing functionality"), the
Constitution pre-check was wired into the three commands that actually
perform that work, documented directly in `cli.py`'s
`_require_valid_constitution` docstring, rather than adding hollow stub
commands with no real functionality just to match names from the task
text that don't correspond to anything real here.

## Test results

```
pytest -q
776 passed in ~39s
```

- CORE TESTS: 776, all passing, all offline/deterministic.
- OPTIONAL PROVIDER TESTS: 0 exist yet — every provider path is
  dependency-injected and covered by the core suite via fakes/mocks.
- NETWORK TESTS: 0 exist — none are needed, since nothing in the tested
  code paths makes a real network call.
- INTEGRATION TESTS: 6 (`tests/test_integration_data_extension.py`,
  now marked `integration`), covering the cross-phase pipeline end to
  end with mock providers.

## Environment requirements

- Python 3.11+ (tested on 3.11.15).
- Core (non-optional) dependencies: pandas, numpy, scipy, pyarrow,
  duckdb, PyYAML, pydantic, typer, scikit-learn — `pae system doctor`
  verifies all of these are actually importable, not just declared.
- Optional: `databento` (real historical/live futures data),
  `requests` (real GEXBOT HTTP client) — neither installed in this
  environment; their absence never breaks the core pipeline or test
  suite.

## Provider requirements (for the next stage of work, not this one)

- `DATABENTO_API_KEY` + the `databento` package, for real historical/
  live futures data.
- `GEXBOT_API_KEY` + the `requests` package, for real options data —
  and, critically, an actual `pae options verify-provider` run against
  that real account before trusting anything the adapter reports.

## Current live-readiness level

See `docs/roadmap_live.md` for the full 13-stage breakdown. Summary: this
pass completes stage 1 (hardened offline engine). Every stage from 2
onward requires real network access and real provider credentials this
environment does not have, and none of them were attempted.

## Known risks

- The GEXBOT field-alias mapping (`_FIELD_ALIASES`) is a best-effort
  guess at the real API's response shape, documented as such since Phase
  H — `pae options verify-provider` is the mechanism to correct it, but
  it has never actually been run against a real account.
- The Databento adapter's exact SDK call shape (`subscribe`/`add_callback`/
  `start`/`stop` naming) is similarly a best-effort guess flagged for
  verification, never checked against the real `databento-python`
  package in this environment.
- `statistics/leakage.py` is explicitly scoped as a *structural* checker
  (timestamp ordering, split overlap, horizon crossing, a static-profile
  heuristic) — it cannot and does not claim to catch an arbitrary
  look-ahead bug hidden inside a feature's own formula.
- The live-shadow default CLI path proposes nothing (by design) — a real
  deployment needs a deliberately wired alpha and no-trade state builder,
  which is intentionally not a CLI flag (to prevent accidentally starting
  live proposal generation without an explicit, reviewed alpha behind
  it).

## Recommended next implementation

Per `docs/roadmap_live.md`, stages 2 (real historical data) and 4
(verified GEXBOT integration) are the correct next steps — both require
real network access and real credentials, and both have the tooling this
pass built (`pae data ingest`, `pae options verify-provider`) ready to
exercise the moment that access exists.

---

## PARE READINESS

```
OFFLINE RESEARCH:          READY
REAL HISTORICAL DATA:      NOT VERIFIED
REAL LIVE MARKET DATA:     NOT VERIFIED
GEXBOT LIVE:                NOT VERIFIED
LIVE DATA RECORDING:       NOT VERIFIED
LIVE SHADOW:                 PARTIALLY IMPLEMENTED / NOT VERIFIED AT SCALE
PAPER TRADING:               PARTIALLY IMPLEMENTED (simulated adapter only, no live feed behind it)
PROP EXECUTION:               NOT IMPLEMENTED
AUTOMATIC EXECUTION:      NOT IMPLEMENTED
```

Nothing above is stated more optimistically than what was actually built
and verified in this pass.
