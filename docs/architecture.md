# Architecture

## Pipeline (Phase 1 slice)

```text
RAW DATA (synthetic, spec §123)
    ↓
DATA QUALITY (prop_alpha.data.quality)
    ↓
FEATURE ENGINE (prop_alpha.features.price_volume)
    ↓
ALPHA / SETUP (prop_alpha.strategies)
    ↓
BACKTEST ENGINE (prop_alpha.backtest.engine)
    ↓
COST MODEL (prop_alpha.backtest.costs)
    ↓
OOS SPLIT (last 20% of trading days, in cli._run_full_research)
    ↓
BOOTSTRAP (prop_alpha.statistics.bootstrap)
    ↓
MONTE CARLO (prop_alpha.statistics.monte_carlo)
    ↓
PROP SIMULATION (prop_alpha.prop.simulator)
    ↓
RANKING + REPORT (prop_alpha.reporting.report)
```

This is the "research first" subset of the full spec pipeline (§3): no
regime engine, no ML meta-alpha, no execution/live layer. Those are later
phases (§137).

## Package layout

```text
src/prop_alpha/
├── config.py         # pydantic EngineConfig — no hardcoded parameters
├── data/              # schema, synthetic generator, quality gate, parquet/duckdb loader
├── features/           # price/volume/volatility/VWAP/order-flow features
├── strategies/          # Alpha object (base.py) + baseline strategies
├── backtest/            # event-driven engine, cost model, trade/day metrics
├── statistics/           # bootstrap, Monte Carlo
├── prop/                  # AccountState, prop-firm rules, path simulator
├── reporting/              # ranking + markdown report generation
├── utils/hashing.py        # reproducibility (git commit, config/dataset hashes, experiment IDs)
└── cli.py                   # `pae` Typer CLI, incl. `pae research full-run`
```

## Key design decisions

- **No look-ahead**: a strategy's `generate_signals` may only use data up to
  and including bar *t*. The backtest engine enters at bar *t+1*'s open
  (`engine.py`, signal read from `df.iloc[i-1]`).
- **Conservative same-bar stop/target**: if both are touched within one
  bar, the stop is assumed to fill first (`test_backtest.py`
  `test_stop_hit_before_target_when_both_touched_same_bar`).
- **End-of-day flatten**: no position carries overnight in this MVP; every
  open trade is closed at the last bar of its session.
- **Reproducibility**: every `full-run` records git commit hash, a hash of
  the resolved config, a hash of the dataset file, and the seed, in the
  report header. Same inputs → byte-identical report body.
- **Prop rules are config, not code**: `PropFirmConfig` (spec §34) holds
  every account rule; `simulate_prop_paths` never hardcodes a specific
  firm's numbers.
- **Fixed position size**: this slice trades 1 contract per signal — the
  Position Sizing Engine (spec §37, EV/uncertainty/distance-to-breach aware
  sizing) is not yet implemented, so `$` P&L magnitudes are illustrative of
  pipeline correctness, not of what an appropriately-sized account would see.
