# Prop Alpha Research Engine

An autonomous quantitative research laboratory for discovering, testing,
falsifying, and validating intraday trading strategies under real prop-firm
account constraints — optimizing for **Expected Payout**, not raw backtest
return. See `docs/architecture.md` for the full design and `docs/data.md`
for the data policy.

This repository implements **Phase 1 (Foundation)**, **Phase 2 (Core
Features)**, **Phase 3 (Strategy Library)**, **Phase 4 (Statistical
Validation)**, and **Phase 5 (Prop Engine)** of the production
specification: a working, reproducible, tested vertical slice through the
whole pipeline — data → session/feature engines → 12 baseline strategies
(+ 6 no-edge comparators) → backtest → costs → OOS split → walk-forward →
bootstrap/Monte Carlo → PBO/DSR overfitting control → cost-sensitivity
stress test → prop account simulation → position sizing & payout-policy
optimization → ranked report — using a clearly-labeled **synthetic**
dataset. It is deliberately not the full 10-phase system (no regime engine,
ML meta-alpha, or agentic discovery yet) — see "What's not built yet" below
and §137 of the spec for the phased plan.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the whole pipeline in one command: generates a synthetic demo
# dataset, validates it, builds features, backtests the baseline
# strategies, runs OOS/bootstrap/Monte Carlo, simulates the prop account,
# ranks alphas, and writes a markdown report.
pae research full-run --config configs/example.yaml

# Faster iteration: skips walk-forward analysis and cost-sensitivity
# stress testing (still runs OOS/bootstrap/Monte Carlo/PBO/DSR).
pae research full-run --config configs/example.yaml --fast

# Run tests
pytest -q
```

Individual pipeline stages are also available:

```bash
pae data generate-demo --n-days 250   # SYNTHETIC data only — see docs/data.md
pae data validate
pae data features
```

## What's implemented

**Phase 1 — Foundation**
- Config-driven market/session/risk/cost/prop parameters (`configs/*.yaml`, no hardcoded magic numbers)
- Parquet + DuckDB data layer, with a synthetic OHLCV generator clearly marked `source=SYNTHETIC`
- Data quality gate (duplicate/non-monotonic timestamps, NaNs, invalid OHLC bounds)
- Alpha object base class (`strategies/base.py`)
- Event-driven bar backtester: next-bar-open entries (no look-ahead), intrabar stop/target checks, end-of-day flatten, configurable commission/slippage/spread
- In-sample/out-of-sample day split
- Stationary block bootstrap for EV/Sharpe/drawdown confidence intervals
- Monte Carlo resampling of daily P&L into simulated account paths
- Configurable Prop Firm engine: daily loss limit, trailing/static drawdown, profit target, minimum trading days, payout threshold — computes P(Breach), P(Payout), Expected Payout
- Ranked markdown research report (Expected Payout → P(Breach) → EV/day) with a reproducibility header (git commit, config hash, dataset hash, seed)

**Phase 2 — Core Features**
- Feature engine: price, volume, volatility, VWAP, order-flow (delta/delta-change) features
- Volume Profile engine: developing (intraday, no-look-ahead) POC/VAH/VAL, HVN/LVN node counts, profile width, plus prior-completed-day POC/VAH/VAL and distance-to-level features, on a fixed price ladder (spec §10)
- Session Engine (spec §7): independent, config-driven named windows (US_OPEN, US_LUNCH, US_POWER_HOUR, US_PREMARKET, LONDON, FRANKFURT, ASIA, OVERNIGHT, US_RTH by default), overnight/midnight-wrapping windows, holiday calendar, per-date half-day close overrides, `minutes_since_session_open`
- Market structure features: prior-completed-day high/low, prior-bar swing high/low, z-scored delta acceleration

**Phase 3 — Strategy Library**
- All 12 MVP baseline strategies (spec §89): Intraday Momentum, Opening Range Breakout, VWAP Mean Reversion, Volume Profile Mean Reversion, Volume Profile Breakout, Previous Day High/Low Reversal, Previous Day High/Low Breakout, Delta Acceleration Momentum, Absorption Reversal, Liquidity Sweep Reversal, Compression→Expansion, Opening Drive Continuation
- 6 trivial no-edge baseline comparators (spec §90): Buy & Hold, Random Entry, Random Direction, Simple MA Crossover, Simple Breakout, Simple Mean Reversion — reported separately, since the point is what every alpha must beat, not to compete for rank
- Report now splits "Top Alpha Ranking" from "Baseline Comparators" and prints the incremental EV/day of the best alpha over the best baseline

**Phase 4 — Statistical Validation**
- Walk-Forward Analysis (spec §26): each alpha is re-backtested independently within 5 sequential, non-overlapping out-of-time folds; reports per-fold EV/day, the fraction of profitable folds, and the worst fold — a strategy whose full-sample edge came from one lucky stretch shows up here
- Probability of Backtest Overfitting via Combinatorially Symmetric Cross-Validation (spec §30): computed once across the 12-alpha trial pool, not per-strategy — asks how often an in-sample "winner" would have ranked below the out-of-sample median
- Deflated Sharpe Ratio (spec §30): per-alpha, against the expected-maximum-Sharpe-under-the-null benchmark implied by the size of the trial pool — a high raw Sharpe with a low DSR is a multiple-testing red flag, not a promotion
- Cost sensitivity / slippage stress test (spec §23/§24): each alpha re-backtested across optimistic → base → conservative → stress → extreme cost profiles, reporting the EV/day degradation curve and the most expensive profile it still survives
- `research_status` now progresses to `WALK_FORWARD` (not just `OUT_OF_SAMPLE`) once ≥60% of walk-forward folds are EV/day-positive, following the Alpha lifecycle states in spec §9
- New `pae research full-run --fast` flag skips walk-forward/cost-sensitivity for quick iteration (OOS/bootstrap/Monte Carlo/PBO/DSR still run)

**Phase 5 — Prop Engine**
- Position Sizing Engine (spec §37, `risk/position_sizing.py`): a composable layer applied to a strategy's already-backtested 1-contract trade sequence — `fixed_contracts` or `fixed_risk` (risk_per_trade % of current equity) sizing, an optional dynamic rule (scale risk up after an intraday profit / down after a loss), and prop-aware capping so a single stop-out can never by itself exceed the account's remaining daily-loss budget
- Stop-Trading Policy Engine (spec §39, `risk/stop_trading.py`): day-level policies — stop after +NR, stop after -NR, stop after N losses — that drop a strategy's later same-day trades once triggered
- Payout Optimizer (spec §38, `risk/payout_optimizer.py`): runs the #1-ranked alpha's trade sequence through 5 named policies (the spec's own worked examples — constant risk, risk-up-after-profit, risk-down-after-loss, profit lock, stop-after-+2R) and ranks them by **Expected Payout**, not raw EV/day — on this synthetic dataset, the profit-lock policy has *lower* EV/day than constant risk but a much lower breach probability and a *higher* Expected Payout, which is exactly the distinction §38 exists to surface
- New report section: "Payout Optimizer — Risk & Stop-Trading Policies for `<top alpha>`"; when the fixed-risk budget can't afford even 1 contract at the account/instrument's configured size, the report says so explicitly rather than showing a misleading empty table

128 unit/property tests, all passing; two full `pae research full-run`
executions (18 strategies) with the same config/seed still produce
byte-identical reports (spec §75). A full run over 250 synthetic days with
all 18 strategies takes ~40s with `--fast`, ~3 minutes with the full
Phase 4 walk-forward + cost-sensitivity gates enabled (default).

## What's not built yet

Regime detection, the No-Trade engine, the Daily State Machine (§109 —
today's stop-trading policies achieve the same effect without the separate
state-machine abstraction), alpha portfolio/allocation across multiple
alphas at once (§41-44 — the Payout Optimizer sizes and sequences one
alpha's own trades, not a multi-alpha portfolio), account-size/risk-percent
sweeps as a dedicated CLI report (§106/§107 — the mechanism is there in
`SizingConfig`/`PropFirmConfig`, just not wired into a sweep command),
purged/embargoed cross-validation for overlapping labels (§27), a dedicated
data-leakage engine (§28) beyond the no-look-ahead discipline already built
into the feature/backtest code, parameter-sensitivity surfaces (§70,
distinct from the cost-sensitivity sweep that *is* built), ML meta-alpha
layer, symbolic regression, the multi-agent research loop, and live/paper
execution are all future phases per §137 of the spec. Do not treat current
EV/payout numbers as anything other than a pipeline
correctness check on synthetic data — see `docs/data.md`.
