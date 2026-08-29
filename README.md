# Prop Alpha Research Engine

An autonomous quantitative research laboratory for discovering, testing,
falsifying, and validating intraday trading strategies under real prop-firm
account constraints — optimizing for **Expected Payout**, not raw backtest
return. See `docs/architecture.md` for the full design and `docs/data.md`
for the data policy.

This repository implements **Phase 1 (Foundation)** and **Phase 2 (Core
Features)** of the production specification: a working, reproducible,
tested vertical slice through the whole pipeline — data → session/feature
engines → strategy → backtest → costs → OOS split → bootstrap/Monte Carlo →
prop account simulation → ranked report — using a clearly-labeled
**synthetic** dataset. It is deliberately not the full 10-phase system (no
regime engine, ML meta-alpha, or agentic discovery yet) — see "What's not
built yet" below and §137 of the spec for the phased plan.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the whole pipeline in one command: generates a synthetic demo
# dataset, validates it, builds features, backtests the baseline
# strategies, runs OOS/bootstrap/Monte Carlo, simulates the prop account,
# ranks alphas, and writes a markdown report.
pae research full-run --config configs/example.yaml

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
- Alpha object + 3 of the 12 baseline strategies (Intraday Momentum, Opening Range Breakout, VWAP Mean Reversion)
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

32 unit/property tests, all passing (21 from Phase 1 + 11 new for the
session/volume-profile engines); two full pipeline runs with the same
config/seed still produce byte-identical reports (spec §75).

## What's not built yet

Regime detection, the No-Trade engine, position sizing (currently fixed
1-contract per trade — §37 is not yet wired in), alpha portfolio/allocation,
overfitting/multiple-testing controls (DSR, PBO), walk-forward analysis,
ML meta-alpha layer, symbolic regression, the multi-agent research loop, and
live/paper execution are all future phases per §137 of the spec. Do not
treat current EV/payout numbers as anything other than a pipeline
correctness check on synthetic data — see `docs/data.md`.
