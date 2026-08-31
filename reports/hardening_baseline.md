# PARE Hardening Pass — Baseline Audit

Recorded before any hardening-pass code changes, per the hardening task's
Step 1 requirement. This is a factual snapshot, not an aspirational one —
statuses below are `PASS` / `FAIL` / `BLOCKED_BY_ENVIRONMENT` /
`NOT_IMPLEMENTED` / `NOT_VERIFIED` only.

## Repository state

- Commit: `362ffa9cdc9dce9e3d4550e17456071ceb4c3238`
- Branch: `claude/prop-alpha-research-engine-ycwng9`
- Remote: `https://github.com/spitferrari-oss/PROP-ALPHA-RESEARCH-ENGINE`

## Environment

- Python: 3.11.15 (`main, Mar 3 2026`, GCC 13.3.0)
- OS: Linux (container)

## Installed package versions (`pip freeze`, relevant subset)

| Package | Version | Declared in pyproject | Status |
|---|---|---|---|
| pandas | 3.0.5 | core (`>=2.1`) | PASS |
| numpy | 2.4.6 | core (`>=1.26`) | PASS |
| scipy | 1.17.1 | core (`>=1.11`) | PASS |
| pyarrow | 25.0.1 | core (`>=14.0`) | PASS |
| duckdb | 1.5.5 | core (`>=0.10`) | PASS |
| PyYAML | 6.0.3 | core (`>=6.0`) | PASS |
| pydantic | 2.13.5 | core (`>=2.5`) | PASS |
| typer | 0.27.2 | core (`>=0.9`) | PASS |
| scikit-learn | 1.9.0 | core (`>=1.3`) | PASS |
| pytest | 9.1.1 | dev (`>=7.4`) | PASS |
| databento | — | optional (`>=0.30`) | **NOT INSTALLED** |
| requests | — | optional (`>=2.31`) | **NOT INSTALLED** |

`duckdb` and `pyarrow` are already core (non-optional) dependencies — they
are required for `data/lake_query.py`, `data/loader.py`, and
`data/immutable_store.py`'s parquet round-trip, all of which the core
research pipeline and the Data Feed extension both depend on. They are
not optional in this repository today; Blocker F in the hardening task
asks this to be represented clearly, which it already is in
`pyproject.toml`'s `dependencies` list — this baseline just confirms that
classification is accurate and not something the hardening pass should
silently change (per the hardening task's own rule: "do not silently
change dependency classification just to make tests pass").

## Test command attempted

```bash
pytest -q
```

## Result

```
627 passed in 62.17s
```

- Tests passed: **627**
- Tests failed: **0**
- Collection errors: **0**
- Skipped: **0** (no `network`/`live`/`provider` markers existed yet at
  this baseline — every test in the suite runs fully offline using
  dependency-injected fakes/mocks, which is why nothing needed to be
  skipped even without `databento`/`requests` installed)

Status: **PASS** (offline, deterministic, no network/credentials used).

## Known unimplemented components (grep for `NotImplementedError`, pre-hardening)

| Location | What raises | Why |
|---|---|---|
| `providers/gexbot/__init__.py` — `GexbotOptionsProvider.get_historical` | Always | GEXBOT's own historical retention is provider-limited (extension §62); never verified against a real account |
| `providers/gexbot/__init__.py` — `GexbotOptionsProvider.get_orderflow` | Always | Options order-flow parsing was never built (extension §34) |
| `providers/mocks.py` — `MockOptionsDataProvider.get_orderflow` | Always | Mirrors the real adapter's own honesty — no orderflow parsing exists anywhere in this repo, so the mock doesn't fabricate one |
| `strategies/base.py` | `Strategy.generate_signals` (abstract) | Base class contract, not a gap |

## Provider integrations that are only provisional (pre-hardening)

- **Databento** (`providers/databento/`): historical + live adapters exist
  and are unit-tested via a fully injected fake client
  (`tests/test_databento_historical.py`, `tests/test_databento_live.py`).
  The adapters' exact call shape against the real `databento-python` SDK
  (`Historical`/`Live` client method names/kwargs) is flagged in the
  module docstrings as "best known when this was written — needs
  verification against the installed SDK," because this environment has
  no network access to check it live and the `databento` package itself
  is not installed. **Status: NOT_VERIFIED against the real provider.**
- **GEXBOT** (`providers/gexbot/`, `options/gexbot/`): client, parser,
  auth, health, and the `GexbotOptionsProvider` adapter exist and are
  unit-tested via an injected fake client
  (`tests/test_gexbot_client.py`, `tests/test_gexbot_provider.py`). The
  raw field-name aliases the parser accepts (`options/gexbot/parser.py`'s
  `_FIELD_ALIASES`) are explicitly documented as "adjust once verified
  against a real GEXBOT account/plan" — they were never checked against
  a real response. **Status: NOT_VERIFIED against the real provider.**
- Neither adapter has ever made a real network call in this repository's
  history. No real API key has ever been used. `GEXBOT_API_KEY` /
  `DATABENTO_API_KEY` are read from the environment when present but are
  not set in this environment, and no `.env` file exists yet.

## Governance / enforcement gaps (pre-hardening)

- No machine-enforced Research Constitution exists anywhere in the repo.
  `docs/architecture.md` and `docs/data.md` describe governance-adjacent
  principles in prose (No-Assumption Principle, immutability, timestamp
  policy) but nothing computes or verifies a hash, and no command refuses
  to run on a governance failure.
- No explicit real-time `should_trade`/`TradeEligibility` gate exists.
  `risk/stop_trading.py`'s `StopTradingPolicy` is a **backtest trade
  filter** (decides, after the fact, which historical trades a
  hypothetical policy would have skipped) — not a real-time eligibility
  check. These are different things and the hardening pass must not
  conflate them.
- No explicit daily account/day state machine exists as its own module.
  `prop/simulator.py` tracks account state and rule breaches but has no
  named state enum (`PRE_MARKET`, `READY`, `TRADE_ALLOWED`, ...).
- No execution gateway interface exists at all — there is no code path
  anywhere in this repository that can send, would send, or simulates
  sending a real order to a broker/prop firm API. This is not a gap to
  "fix" so much as a fact to preserve: execution stays disabled through
  and after this hardening pass.
- `agents/audit.py`'s `AuditTrail`/`AuditEntry` exist and are wired into
  `pae research full-run` (one call site, `cli.py`), but entries do not
  yet carry `constitution_id`/`constitution_version`/`constitution_hash`/
  `git_commit` — `git_commit_hash()` already exists in `utils/hashing.py`
  and is already used elsewhere for experiment metadata, just not copied
  into the audit entry itself yet.
- No pytest markers exist (`unit`/`integration`/`network`/`provider`/
  `live`/`slow`) — every test currently runs in one undivided suite. This
  is not a correctness problem today (nothing needs real credentials to
  pass), but it means there is no way to *express* "only run what's safe
  offline" as a command, which the hardening task requires.
- `src/prop_alpha/statistics/` has walk-forward, PBO, DSR, and cost
  sensitivity, but no dedicated parameter-sensitivity module and no
  data-leakage checker.

## What already exists and should NOT be duplicated

- `data_center/status.py`/`render.py` (Phase M) already distinguishes
  "not available" from a fabricated healthy status per component
  (`FeedHealth`/`GexbotHealth`/`DataQualityReport`, each independently
  `None`-able) — the hardening pass should extend this with explicit
  REAL/REPLAY/SYNTHETIC/MOCK/NOT_CONNECTED source labeling, not replace
  it.
- `live_shadow/` (Phase O) already has `TradeProposal`/`apply_feedback`/
  `LiveShadowLedger`/`run_live_shadow_session` — a real, tested
  proposal-and-human-feedback pipeline. It currently only accepts an
  already-built `MarketState` iterable; it does not yet own subscribing
  to a live provider itself. The hardening pass extends this package with
  a session/orchestration layer, it does not replace the proposal/ledger
  machinery.
- `providers/mocks.py` (extension's final phase) already provides
  `MockFuturesDataProvider`/`MockOptionsDataProvider` — reused as-is by
  this hardening pass's provider-substitution tests, not rebuilt.
- `regimes/`, `statistics/{walk_forward,pbo,dsr,cost_sensitivity}.py`,
  `discovery/hypothesis.py` (Hypothesis Ledger), `agents/{statistician,
  critic,risk_agent,supervisor}.py` all already exist and are reused,
  not duplicated, by the governance/audit work in this pass.

## Missing optional dependencies confirmed

- `databento` — not installed, optional, only needed for real Databento
  network calls (none of which this repository ever makes today).
- `requests` — not installed, optional, only needed for real GEXBOT HTTP
  calls (same).

Both are lazily imported only inside the real adapter modules
(`providers/databento/*.py`, `options/gexbot/client.py`) specifically so
their absence never breaks anything else — confirmed still true at this
baseline (`pytest -q` passes with neither installed).
