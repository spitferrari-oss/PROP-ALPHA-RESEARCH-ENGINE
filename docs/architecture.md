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
WALK-FORWARD ANALYSIS (prop_alpha.statistics.walk_forward) — alphas only, skipped with --fast
    ↓
BOOTSTRAP (prop_alpha.statistics.bootstrap)
    ↓
MONTE CARLO (prop_alpha.statistics.monte_carlo)
    ↓
COST SENSITIVITY (prop_alpha.statistics.cost_sensitivity) — alphas only, skipped with --fast
    ↓
PBO + DSR (prop_alpha.statistics.pbo / dsr) — once across the alpha trial pool
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
├── statistics/           # bootstrap, Monte Carlo, walk-forward, PBO, DSR, cost sensitivity
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

## Statistical validation (Phase 4, spec §26/§23/§24/§30)

- **Walk-Forward Analysis** (`statistics/walk_forward.py`) splits each
  alpha's days into 5 sequential, non-overlapping folds and re-backtests
  independently within each — folds only ever see their own rows of the
  already-computed `df_feat` (features aren't recomputed, so no cross-fold
  leakage is possible). Current strategies are fixed-rule, not fitted, so
  this validates *temporal stability* (did the edge hold up rolling forward
  through time, or was the full-sample number one lucky stretch?) rather
  than parameter re-optimization — a future parameterized/ML strategy would
  add an actual fit-on-train step per fold on top of this same splitting.
- **Cost sensitivity** (`statistics/cost_sensitivity.py`) re-backtests each
  alpha's already-generated signals across the five cost profiles already
  defined in `backtest/costs.py` (optimistic → extreme) and reports the
  EV/day degradation curve plus the most expensive profile the strategy
  still survives.
- **PBO** (`statistics/pbo.py`) and **DSR** (`statistics/dsr.py`) are
  computed once across the 12-alpha trial pool, not per-strategy — they are
  statements about the *selection process*, not about any single alpha.
  PBO uses Combinatorially Symmetric Cross-Validation (Bailey et al. 2014):
  split the trading days into 8 blocks, and for every way of choosing half
  the blocks as "in-sample", ask how often the in-sample Sharpe-ratio
  winner ranked below the out-of-sample median. DSR (Bailey & Lopez de
  Prado 2014) deflates each alpha's Sharpe ratio by the expected maximum
  Sharpe achievable by pure luck across N=12 independent trials, given the
  trial pool's own Sharpe spread — a high raw Sharpe with a low DSR is a
  multiple-testing red flag, not grounds for promotion.
- **`research_status` lifecycle** (spec §9): an alpha only reaches
  `WALK_FORWARD` (up from `OUT_OF_SAMPLE`) once its OOS EV/day is positive
  *and* at least 60% of its walk-forward folds are individually
  EV/day-positive. Baseline comparators never run walk-forward/cost
  sensitivity (they aren't candidates for promotion) and cap out at
  `OUT_OF_SAMPLE`/`BACKTESTED`.
- **`pae research full-run --fast`** skips walk-forward and cost
  sensitivity (the two per-alpha diagnostics that each mean N more full
  backtests) for faster iteration; OOS, bootstrap, Monte Carlo, and the
  pool-level PBO/DSR still run every time.

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
