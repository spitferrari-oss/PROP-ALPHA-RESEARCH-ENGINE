# Architecture

## Pipeline (Phase 1 + 2 slice)

```text
RAW DATA (synthetic, spec §123)
    ↓
DATA QUALITY (prop_alpha.data.quality)
    ↓
FEATURE ENGINE (prop_alpha.features.pipeline.build_full_feature_set)
    ├─ price/volume/volatility/VWAP/order-flow (features.price_volume)
    ├─ volume profile: POC/VAH/VAL/HVN/LVN, prior-day levels (features.volume_profile)
    └─ session annotation: windows, holidays, half-days (sessions.engine)
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
├── sessions/            # Session Engine: named windows, holidays, half-days (spec §7)
├── features/             # price/volume/volatility/VWAP/order-flow/market-structure + volume profile; pipeline.py chains features + session annotation
├── strategies/             # Alpha object (base.py) + 12 baseline strategies (spec §89) + 6 no-edge comparators (baselines.py, spec §90)
├── backtest/            # event-driven engine, cost model, trade/day metrics
├── statistics/           # bootstrap, Monte Carlo
├── prop/                  # AccountState, prop-firm rules, path simulator
├── reporting/              # ranking + markdown report generation
├── utils/hashing.py        # reproducibility (git commit, config/dataset hashes, experiment IDs)
└── cli.py                   # `pae` Typer CLI, incl. `pae research full-run`
```

## Strategy library (Phase 3, spec §89/§90)

`cli.ALPHA_STRATEGIES` holds all 12 MVP baseline strategies; each is a small
`Strategy` subclass whose `generate_signals` reads only already-computed
feature columns:

| ID | Strategy | Family | Key features used |
|---|---|---|---|
| ALPHA_01 | Intraday Momentum | MOMENTUM | return z-score, relative volume |
| ALPHA_02 | Opening Range Breakout | MOMENTUM | per-day opening range |
| ALPHA_03 | VWAP Mean Reversion | MEAN_REVERSION | `vwap_z` |
| ALPHA_04 | Volume Profile Mean Reversion | MEAN_REVERSION | `vp_vah`/`vp_val` |
| ALPHA_05 | Volume Profile Breakout | MOMENTUM | `vp_vah`/`vp_val` crossing |
| ALPHA_06 | Previous Day High/Low Reversal | MEAN_REVERSION | `prior_day_high`/`low` sweep+reject |
| ALPHA_07 | Previous Day High/Low Breakout | MOMENTUM | `prior_day_high`/`low` |
| ALPHA_08 | Delta Acceleration Momentum | MICROSTRUCTURE | `delta_acceleration_z` |
| ALPHA_09 | Absorption Reversal | MICROSTRUCTURE | `relative_volume`, `body`/`atr_14`, `delta` |
| ALPHA_10 | Liquidity Sweep Reversal | MICROSTRUCTURE | `prior_swing_high`/`low` sweep + `delta` |
| ALPHA_11 | Compression to Expansion | MOMENTUM | `volatility_percentile`, `true_range`/`atr_14` |
| ALPHA_12 | Opening Drive Continuation | MOMENTUM | first-bar body vs `atr_14` |

`strategies/baselines.py` holds the 6 trivial no-edge comparators from §90
(Buy & Hold, Random Entry, Random Direction, Simple MA Crossover, Simple
Breakout, Simple Mean Reversion), tagged `family="BASELINE"` and reported
separately — see §90: "every alpha must demonstrate incremental value over
an appropriate baseline."

On the current synthetic dataset, ALPHA_09 (Absorption Reversal) tends to
produce zero trades — the synthetic generator does not model true
volume/price absorption, so its conjunction of conditions rarely fires.
That is a property of the synthetic data, not a bug: the pipeline handles a
zero-trade strategy gracefully (metrics report NaN, bootstrap/Monte Carlo
are skipped) rather than crashing or fabricating a result.

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
- **Volume Profile uses a fixed price ladder**: bin edges are `tick_size *
  bin_ticks` (config: `volume_profile.bin_ticks`), not the day's realized
  high/low range — using the full day's range to place bin edges would leak
  end-of-day information into an intraday "developing" profile. Each bar's
  volume is split evenly across every bin its `[low, high]` touches.
  `vp_poc/vah/val/width/hvn_count/lvn_count` are as-of-that-bar; `vp_prior_*`
  are deliberately the *previous completed* day's finalized profile.
- **Session Engine is independent of feature/strategy code** (spec §7): a
  window's start/end/timezone lives entirely in `EngineConfig.sessions`, so
  redefining a session (or adding a new one) never touches
  `sessions/engine.py`, `features/*.py`, or a strategy file.
