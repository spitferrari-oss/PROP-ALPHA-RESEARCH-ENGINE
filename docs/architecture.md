# Architecture

## Pipeline (Phase 1-10 slice)

```text
RAW DATA (synthetic, spec §123)
    ↓
DATA QUALITY (prop_alpha.data.quality)
    ↓
FEATURE ENGINE (prop_alpha.features.pipeline.build_full_feature_set)
    ├─ price/volume/volatility/VWAP/order-flow/market-structure (features.price_volume)
    ├─ volume profile: POC/VAH/VAL/HVN/LVN, prior-day levels (features.volume_profile)
    └─ session annotation: windows, holidays, half-days (sessions.engine)
    ↓
REGIME ENGINE (prop_alpha.regimes.pipeline.build_regime_features)
    ├─ rule-based cascade (regimes.rule_based) — pure per-bar arithmetic
    ├─ Gaussian Mixture (regimes.statistical) — fit on in-sample days only
    └─ transition flags (regimes.transition)
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
    ↓
PAYOUT OPTIMIZER (prop_alpha.risk.payout_optimizer) — #1-ranked alpha only:
    position sizing (risk.position_sizing) x stop-trading policies (risk.stop_trading)
    x prop simulation, ranked by Expected Payout
    ↓
CONDITIONAL EV BY REGIME (prop_alpha.regimes.conditional_ev) — #1-ranked alpha only
    ↓
ML META-ALPHA (prop_alpha.ml.meta_alpha) — #1-ranked alpha only:
    Logistic Regression baseline + Random Forest, both fit on IS trades,
    calibration (ml.calibration) + ensemble-uncertainty gate evaluated OOS
    ↓
SHADOW MODE / PAPER TRADING (prop_alpha.paper) — #1-ranked alpha only:
    shadow log built by replaying the same OOS trades (shadow.py)
    ↓
    Live/Paper Monitor (monitor.py) — Expected vs Actual R, calibration
    Alpha Decay Monitor (decay.py) — GREEN/YELLOW/ORANGE/RED vs IS bootstrap CI
    Drift Detection (drift.py) — PSI between IS and shadow feature distributions
    ↓
MULTI-AGENT REVIEW (prop_alpha.agents) — #1-ranked alpha only:
    Statistician (statistician.py) + Risk Agent (risk_agent.py) -> gates
        (Statistician's PAPER_TRADING_ACCEPTABLE gate reads the Alpha Decay
        Monitor's level)
    Critic (critic.py) -> findings (incl. ALPHA_DECAY, FEATURE_DRIFT)
    Supervisor (supervisor.py) -> verdict, logged to Audit Trail (audit.py)
```

`pae research discover` shares the same data/feature/regime prep
(`cli._prepare_dataset`, used by both commands) but is otherwise a
separate pipeline from `full-run`:

```text
CONDITION LIBRARY (prop_alpha.discovery.conditions) — ~20 predicates over
    existing feature/regime columns
    ↓
SETUP GENERATOR (prop_alpha.discovery.setup_generator) — combinatorial
    search: 1-2 conditions AND'ed, both directions, same ATR-based
    stop/target every hand-coded alpha uses
    ↓
QUICK SCREEN (prop_alpha.discovery.screening) — cheap backtest-only IS/OOS
    EV check per candidate (no bootstrap/MC/WFA)
    ↓
HYPOTHESIS LEDGER (prop_alpha.discovery.hypothesis) — every candidate,
    survivor or not, appended to research_memory/hypotheses/ledger.jsonl
    ↓
SYMBOLIC REGRESSION (prop_alpha.discovery.symbolic_regression) — a
    complementary raw-signal scan, independent of the candidate list above
    ↓
DISCOVERY REPORT (prop_alpha.reporting.discovery_report)
```

A discovery survivor reaches at most `HYPOTHESIS`/`BACKTESTED` — promoting
one further means a human hand-codes it as a `Strategy`, adds it to
`cli.ALPHA_STRATEGIES`, and runs it through `full-run`'s actual Phase 4
gates (walk-forward, bootstrap, PBO/DSR, cost sensitivity). Discovery
never auto-promotes anything, on purpose (spec §18: generating
combinations must never make them automatically valid).

This is the "research first" subset of the full spec pipeline (§3): no
execution/live layer, no multi-agent research loop. Those are later phases
(§137).

## Package layout

```text
src/prop_alpha/
├── config.py         # pydantic EngineConfig — no hardcoded parameters
├── data/              # schema, synthetic generator, quality gate, parquet/duckdb loader
│   ├── live/            # Data Feed extension: provider-agnostic Live Data Engine (connection/subscription/recorder/event router/health/session)
│   ├── lake.py          # Data Feed extension: data lake directory structure (raw/normalized/curated/features/outcomes/snapshots/metadata)
│   ├── manifest.py      # Data Feed extension: DatasetManifest (spec §9)
│   ├── immutable_store.py # Data Feed extension: write-once storage + append-only dataset ledger (spec §7-8)
│   ├── normalize.py     # Data Feed extension: cross-provider bars/trades schema unification (spec §6)
│   ├── quality_engine.py # Data Feed extension: graduated 0-100 DATA_QUALITY_SCORE across bars/trades/quotes (spec §19-20)
│   ├── quality_config.py # Data Feed extension: quality thresholds + blocked_on flags (spec §103)
│   ├── recording_config.py # Data Feed extension: RecordingConfig (spec §101)
│   ├── lake_query.py    # Data Feed extension: DuckDB query layer over the data lake (spec §6/§10-11)
│   └── ingest.py         # Data Feed extension: incremental/resumable/retried/quality-gated historical ingestion (spec §10)
├── sessions/            # Session Engine: named windows, holidays, half-days (spec §7)
├── features/             # price/volume/volatility/VWAP/order-flow/market-structure + volume profile; pipeline.py chains features + session annotation
├── regimes/                # rule-based + Gaussian Mixture regime classifiers, transition flags, conditional EV by regime
├── discovery/               # condition library, combinatorial setup generator, quick screening, symbolic regression, Hypothesis Ledger
├── ml/                      # ML feature matrix, Meta-Alpha model (baseline + Random Forest), calibration diagnostics
├── paper/                    # Shadow Mode replay, Live/Paper Monitor, Alpha Decay Monitor, PSI drift detection
├── providers/               # Data Feed extension: provider ABCs + Databento historical/live + GEXBOT options adapters (see docs/data_feed_extension.md)
├── options/                  # Data Feed extension: options intelligence subsystem
│   ├── models.py             #   vendor-agnostic OptionsSnapshot/OptionsLevel (spec §28-29)
│   ├── normalize.py          #   GexSnapshot -> OptionsSnapshot (spec §28)
│   ├── levels.py             #   Options Level Engine: snapshot -> OptionsLevel objects (spec §29)
│   └── gexbot/                #   GEXBOT-specific client/auth/parser/models/health
├── sync/                     # Data Feed extension: futures/options synchronization + CrossMarketState (spec §35-36)
├── agents/                   # Statistician/Risk/Critic/Supervisor + Audit Trail (deterministic, no LLM calls)
├── strategies/             # Alpha object (base.py) + 12 baseline strategies (spec §89) + 6 no-edge comparators (baselines.py, spec §90)
├── backtest/            # event-driven engine, cost model, trade/day metrics
├── statistics/           # bootstrap, Monte Carlo, walk-forward, PBO, DSR, cost sensitivity
├── prop/                  # AccountState, prop-firm rules, path simulator
├── risk/                   # position sizing, stop-trading policies, payout optimizer
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

## Prop Engine (Phase 5, spec §37/§38/§39)

The main alpha-ranking backtest deliberately stays at 1 contract for every
strategy (see "Fixed position size" below) — sizing is layered on
*afterward*, as a separate, independently testable concern:

```text
1-contract trades (backtest.engine.run_backtest)
    ↓
StopTradingPolicy.apply_day_policy    — drop trades after a day-level rule fires
    ↓
SizingConfig.apply_position_sizing    — walk trades in time order, size each
    against the account state that would actually have existed at that point
    ↓
daily P&L -> Monte Carlo -> prop simulation -> Expected Payout
```

- **`risk/position_sizing.py`** (spec §37): `fixed_contracts` (constant N)
  or `fixed_risk` (risk_per_trade % of *current* equity, so sizing
  compounds as the account grows or shrinks — see `apply_position_sizing`'s
  running `equity`). An optional `dynamic_rule` scales the risk percentage
  up after an intraday profit or down after an intraday loss (spec §38
  Policies B/C). `prop_aware=True` (the default) caps contracts so a single
  stop-out can never exceed the account's remaining daily-loss budget
  (`max_daily_loss + daily_pnl_so_far`) — tested directly in
  `test_apply_position_sizing_never_exceeds_daily_budget_on_a_single_trade`.
  Both `pnl` and commission in a 1-contract trade scale linearly with
  contract count, so rescaling is just `contracts * pnl_per_contract` — no
  need to re-run the backtest per sizing choice.
- **`risk/stop_trading.py`** (spec §39): `StopTradingPolicy` supports
  `stop_after_profit_r`, `stop_after_loss_r`, and `stop_after_n_losses`.
  `apply_day_policy` walks trades in time order and drops everything after
  the day's condition first fires — the triggering trade itself is kept
  (the policy stops trading *after* it, not retroactively).
- **`risk/payout_optimizer.py`** (spec §38): `default_policies()` returns
  the spec's own five worked examples (A constant risk, B increase after
  profit, C decrease after loss, D profit lock at +1R, E stop after +2R).
  `compare_policies` re-derives each policy's daily P&L from the *same*
  underlying 1-contract trade sequence and runs it through the existing
  Monte Carlo + prop simulator, so the comparison is apples-to-apples and
  ranks by **Expected Payout** (spec §134 Rank 1), not EV/day — on this
  synthetic dataset, the profit-lock policy has *lower* EV/day than
  constant risk but a much lower P(Breach) and a *higher* Expected Payout,
  which is exactly the distinction §38 exists to surface. Applied only to
  the #1-ranked alpha per run (comparing money-management policy is a
  downstream-of-selection question, not something to run for all 12
  candidates every time).
- **A degenerate result is reported, not hidden**: if the fixed-risk budget
  (`risk.risk_per_trade × prop.account_size`) can't afford even 1 contract
  at an alpha's stop distance and `market.point_value`, every policy prices
  in 0 contracts — the report says so explicitly (spec §37: the system must
  prevent sizing that could breach on one plausible loss; refusing to size
  at all is the conservative, correct behavior here, not a bug).

## Regime Engine (Phase 6, spec §12/§13/§14)

Regime features are added to `df_feat` right after the feature engine and
before any strategy sees the data — every strategy and diagnostic
downstream automatically has `regime_rule`, `regime_gmm`,
`regime_gmm_confidence`, `regime_transitioning`, `high_liquidity`, and
`low_liquidity` columns available, even though today's 12 alphas don't
condition their signals on them.

- **`regimes/rule_based.py`**: a priority-ordered `np.select` cascade —
  PANIC → BREAKOUT → COMPRESSION → EXPANSION → TREND_UP → TREND_DOWN →
  HIGH_VOLATILITY → LOW_VOLATILITY → (default) RANGE, with UNKNOWN when any
  input feature is still NaN (warm-up bars). Every threshold is on a ratio
  or percentile (`true_range / atr_14`, `volatility_percentile`,
  `relative_volume`), never a raw price level, per spec §116/§117 — and all
  configurable via `RegimeConfig`, not hardcoded. High/low liquidity are
  reported as separate boolean columns rather than folded into the primary
  label, since a bar can independently be e.g. both TREND_UP and
  LOW_LIQUIDITY — collapsing that into one categorical would throw away
  real information.
- **`regimes/statistical.py`**: `GmmRegimeClassifier` wraps
  `sklearn.mixture.GaussianMixture` over 3 standardized features
  (`log_returns`, `realized_vol_20`, `volume_z`). Gaussian Mixture is the
  spec's own listed alternative to HMM/Markov-Switching (§12), so this
  satisfies the "statistical" branch of "rule-based; HMM; clustering;
  change point" without a separate HMM dependency. **Fit is IS-only**:
  `regimes/pipeline.build_regime_features` fits on the same in-sample day
  set the OOS split already uses (`cli._run_full_research`'s
  `in_sample_days`), then predicts on the full series — fitting on the
  whole dataset would leak OOS market structure into the cluster
  boundaries every OOS backtest is then judged against.
- **`regimes/transition.py`**: `regime_transitioning` is spec §13's "is it
  changing," not "what is it" — flagged when the rule-based label has
  flipped at least twice within a short rolling window (whipsawing, not a
  single clean transition) or the GMM's posterior confidence in its top
  cluster drops below a threshold (the statistical model itself is
  unsure). This is a lightweight proxy for formal change-point detection,
  not a CUSUM/Bayesian change-point algorithm — see "What's not built yet."
- **`regimes/conditional_ev.py`**: this is the payoff for building a regime
  engine at all (spec §140/§141: don't add complexity that doesn't move
  OOS EV or Payout Utility). It joins the #1-ranked alpha's trades to the
  rule-based regime active at each entry bar and reports EV/trade, win
  rate, and count per regime — on the synthetic dataset this reveals the
  top alpha's EV/trade ranges from +$2,614 in BREAKOUT down to -$707 in
  LOW_VOLATILITY, a >3,000% swing that the flat, unconditional EV/day
  number in the main ranking table completely hides.

## Alpha Discovery Engine (Phase 7, spec §18/§19/§20/§48)

- **Generation is decoupled from validation** (spec §18's explicit
  requirement): `discovery/setup_generator.generate_candidate_setups`
  builds `GeneratedStrategy` instances — a plain `Strategy` subclass whose
  `generate_signals` ANDs 1-2 `Condition` predicates together — purely
  combinatorially, with no awareness of how they'll perform. Every
  candidate reuses the exact same ATR-based stop/target as the 12
  hand-coded alphas (`Strategy.with_risk_levels`), so a discovered setup's
  backtest is directly comparable to a hand-coded one's.
- **The condition library is the search space** (`discovery/conditions.py`):
  ~20 named boolean predicates over already-computed feature/regime
  columns (VWAP z-score extremes, delta acceleration, relative volume,
  every rule-based regime label, transition stability, prior-day
  breaks, developing POC proximity). `max_combo_size` is capped at 2 —
  not the spec's "migliaia di combinazioni" scale — because each
  candidate costs a full backtest through the same per-bar Python loop
  every alpha uses; see "What's not built yet" for the performance
  ceiling this implies.
- **Screening is deliberately cheap and deliberately weak**
  (`discovery/screening.quick_evaluate`): only a backtest, no
  bootstrap/Monte Carlo/walk-forward — passing requires enough trades and
  positive EV/day on *both* the in-sample and out-of-sample slices, a
  coarse filter against an IS-only fluke, not a validation gate. A pass
  reaches `BACKTESTED` at most; only a human hand-coding the idea and
  running it through `full-run`'s Phase 4 gates can promote it to
  `WALK_FORWARD`/`ROBUST`.
- **Every candidate is logged, survivor or not**
  (`discovery/hypothesis.HypothesisLedger`, spec §20): an append-only
  JSONL file — rejected candidates become `RETIRED` hypotheses with their
  actual IS/OOS numbers as `result`, not silently discarded (spec §96
  Failed Strategy Database). The mechanism/economic-rationale text is
  auto-derived from the conditions used (`Condition.mechanism_hint`), so
  even an auto-generated candidate carries a plausible "why," not just a
  boolean expression.
- **Symbolic regression is a separate, complementary scan**
  (`discovery/symbolic_regression.py`, spec §48): ranks single features
  and pairwise sums/differences by Spearman IC against a short-horizon
  *forward* return, tie-broken toward fewer terms (spec §49). The forward
  return intentionally uses future bars (`close.shift(-horizon)`) — that
  is correct here since it is the regression's target/label, not an input
  feature; it must never be used as one. This surfaces *which raw signals*
  carry information, distinct from the setup generator's boolean-rule
  search — a human turns a high-IC expression into a new condition for the
  library, not something the pipeline does automatically.

## ML Meta-Alpha (Phase 8, spec §44/§45/§46/§47/§101)

- **Baseline-first is enforced, not just aspirational** (spec §45):
  `ml/meta_alpha.MetaAlphaModel.fit` always trains a `LogisticRegression`
  alongside the `RandomForestClassifier` — there is no code path that fits
  the Random Forest alone. `evaluate_meta_alpha` compares their OOS Brier
  scores and sets `recommended_model` explicitly; the report prints
  whichever one actually won, including the honest case where it's the
  simpler baseline. On the synthetic dataset the Random Forest beat the
  baseline on OOS Brier score but had a *worse* OOS ECE (0.227 vs
  0.137) — a real mixed result the report shows as-is rather than
  collapsing into a single "ML wins" headline.
- **Same IS-only preprocessing discipline as the GMM regime classifier**:
  `_make_preprocessor` builds a `ColumnTransformer`
  (`SimpleImputer`+`StandardScaler` for numeric/boolean columns,
  `OneHotEncoder(handle_unknown="ignore")` for `regime_rule`/`session`)
  wrapped in the same `Pipeline` as each model. Calling `.fit(X_is, ...)`
  fits imputation medians, scaling, and the one-hot vocabulary on
  in-sample rows only; `.predict(X_oos)` reuses those exact fitted
  statistics — `handle_unknown="ignore"` means a category that only
  appears OOS gets an all-zero encoding rather than crashing or leaking
  its existence back into training.
- **Ensemble variance is the uncertainty method** (spec §47 lists several;
  this is the one that comes free with a Random Forest):
  `predict_uncertainty` transforms OOS rows once through the fitted
  preprocessor, then asks every individual tree in the forest for its own
  P(win) and takes the standard deviation across trees — high
  disagreement among trees is a distinct signal from a low *averaged*
  probability, and is flagged as a would-be `NO_TRADE` when it exceeds
  `ml.uncertainty_threshold`. On the synthetic dataset's small OOS sample
  (~30 trades) for the #1 alpha, ensemble disagreement is high enough that
  every OOS trade clears the threshold — a real, honestly-reported
  consequence of a ~200-tree forest trained on well under 100 IS trades,
  not a tuned-away inconvenience; a larger sample or fewer trees would
  narrow it, and the report is upfront that the gate is uninformative at
  this sample size rather than pretending it is decisive.
- **Expected R is a second, separate regressor**
  (`expected_r_pipeline`, spec §46): a `RandomForestRegressor` over the
  same feature matrix predicting the realized R-multiple rather than
  win/loss — available via `predict_expected_r` but not yet surfaced in
  the report table (see "What's not built yet").
- **Graceful degradation, not a crash, on thin data**: `evaluate_meta_alpha`
  returns `status="INSUFFICIENT_DATA"` (with the actual IS/OOS counts) when
  there aren't enough trades or only one outcome class is present in the
  training split, and the report renders that explicitly rather than
  fitting a meaningless model or raising.

## Paper Trading / Shadow Mode (Phase 10, spec §97-101/§131-133)

**No live feed exists in this environment.** Spec §123 forbids presenting
fabricated data as real market evidence, so `paper/shadow.build_shadow_log`
replays the #1-ranked alpha's already-computed OOS trades (the same ones
used for the Phase 4/8 statistical validation and ML Meta-Alpha layers) as
the shadow log's source, rather than inventing a synthetic "live" stream.
Every report section and docstring in this layer says so explicitly — this
demonstrates the monitoring mechanism end-to-end, and must never be read as
a claim of genuine forward performance. A real deployment would feed this
same monitor/decay/drift machinery from newly-collected forward data
gathered after promotion (spec §131 Deployment Stage 3+) instead.

- **`paper/shadow.py`** (spec §132 — "compute what would have been done
  without sending real orders"): `build_shadow_log` takes the OOS trade
  frame, the matching OOS feature matrix (`X_oos`, already built for ML
  Meta-Alpha), the fitted `MetaAlphaModel` (or `None` when Phase 8 had
  insufficient data to fit one), and the alpha's own `alpha_result` dict.
  It attaches a single constant `expected_r` (the alpha's in-sample
  expectancy) per row, alongside each trade's realized `actual_r`/`pnl` and
  — when a model was fit and its row count matches — the model's own
  `predict_proba_rf` output as `model_probability`. Deliberately does *not*
  include an expected-vs-actual slippage column (also named in spec §100):
  the backtest/shadow cost model is deterministic, so the two figures would
  always be identical and the comparison would be theater.
- **`paper/monitor.py`** (spec §100/§101): `evaluate_paper_monitor` reports
  `n_shadow_trades`, `expected_r` vs. `actual_mean_r` (and their difference,
  `r_prediction_error`), `win_rate`, and — once at least
  `paper.min_shadow_trades_for_calibration` shadow trades carry a
  `model_probability` — reuses `ml.calibration.compute_calibration_metrics`
  (Brier score, log loss, ECE) against the shadow trades' actual outcomes,
  the same diagnostic Phase 8 computed OOS, now computed on the shadow
  period instead.
- **`paper/decay.py`** (spec §97/§98): `classify_alpha_decay` compares the
  shadow period's own daily P&L against the alpha's Phase 4 in-sample
  bootstrap CI (`boot_ev_p5`/`boot_ev_p95`, already in `alpha_result`) and
  assigns one of four mechanically-checkable levels: **RED** if the shadow
  period's own 90% bootstrap CI for EV/day is entirely negative, **ORANGE**
  if that CI straddles zero, **YELLOW** if shadow EV/day has degraded more
  than roughly one IS-bootstrap sigma (approximated from the already-computed
  90% CI's p5-p95 span, ~3.29 sigma for a normal distribution) below IS
  EV/day, else **GREEN**. Spec §98 also names a fifth level, **RETIRED**
  ("economic thesis invalidated / not automatable") — that is a judgment
  call about *why* an edge decayed, not a statistic, so this module never
  auto-assigns it (spec §128); a RED classification is the signal a human
  should look at that question.
- **`paper/drift.py`** (spec §99): `compute_psi` bins the "expected"
  (in-sample) array into quantiles and measures how much the "actual"
  (shadow) array's distribution across those same bins has shifted — the
  standard Population Stability Index, PSI > 0.2 conventionally read as
  significant drift. `compute_feature_drift` applies this to a handful of
  configured features (`paper.drift_features`, default
  `volatility_percentile`/`relative_volume`/`vwap_z`) by reusing the IS/OOS
  ML feature matrices already built for Meta-Alpha (`X_is`/`X_oos`) rather
  than re-extracting features from raw bars. Only PSI is implemented; spec
  §99 also names KS, Jensen-Shannon divergence, Wasserstein distance, and
  change-point detection, and drift categories beyond feature drift
  (regime/performance/volatility/liquidity/execution) — none of those are
  built, a documented gap rather than a claim of full coverage.
- **`config.PaperTradingConfig`**: every threshold above
  (`psi_drift_threshold`, `drift_features`, `decay_min_shadow_days_for_ci`,
  `decay_bootstrap_n`, `min_shadow_trades_for_calibration`) lives in config,
  not hardcoded in `paper/*.py`, following the same discipline as
  `AgentsConfig`'s thresholds (spec §80/§116).
- Wired into `cli._run_full_research` immediately after the ML Meta-Alpha
  block (same `oos_trades`/`X_oos` already computed there, no recomputation)
  and feeds both the Statistician's `PAPER_TRADING_ACCEPTABLE` gate and the
  Critic's `ALPHA_DECAY`/`FEATURE_DRIFT` findings — see below. New report
  section: "Paper Trading / Shadow Mode for `<top alpha>`".

## Multi-Agent Research Architecture (Phase 9, spec §58-60/§128/§129)

**Deliberately not LLM agents.** Spec §57 describes Researcher/Analyst/
Critic/Documentation/Orchestrator roles for an LLM; spec §58 chains ten
named agents down to a Supervisor. Wiring actual LLM calls into this
pipeline would make every research run non-deterministic and break the
byte-identical-reproducibility guarantee (spec §75) every phase so far has
maintained — and spec §128 is explicit that an LLM must never be the sole
arbiter of statistical validity anyway. So Phase 9 implements the
*architecture* — clearly separated agents with the spec's own
responsibilities, a Supervisor that is the only thing allowed to issue a
verdict, and a permanent Audit Trail — as deterministic Python evaluating
evidence Phases 1-8 already computed. An LLM (or a human) could later sit
in front of any one of these agents to interpret its output in prose; none
of them need one to do their actual job.

- **`agents/gates.py`**: shared `Gate` (name/status/detail) and `Finding`
  (category/severity/description) types. `Gate.status` is one of `PASS`,
  `FAIL`, `NOT_EVALUATED` — a distinct third state, not a boolean, because
  spec §128 requires the system to never quietly treat an unchecked
  criterion as satisfied.
- **`agents/statistician.py`** (spec §60): checks 11 of the 12 Research
  Gates directly against fields already in `alpha_result` (from
  `cli._evaluate_strategy`) plus the Phase 10 paper-trading evidence — no new
  computation of its own, only reading. `NO_LEAKAGE` and `PARAMETER_ROBUST`
  are always `NOT_EVALUATED` (no engine exists for them yet); as of Phase 10,
  `PAPER_TRADING_ACCEPTABLE` is `NOT_EVALUATED` only when there are no shadow
  trades to replay, otherwise `PASS` iff the Alpha Decay Monitor's level is
  GREEN (see "Paper Trading / Shadow Mode" above — spec §133's
  live-eligibility bar is strict, so YELLOW/ORANGE/RED all read `FAIL`, not
  a partial pass). `WALK_FORWARD_ROBUST`
  and `COST_ROBUST` read the `diagnostics_run` flag on `alpha_result`
  before deciding `PASS`/`FAIL` vs `NOT_EVALUATED` — this flag was added
  specifically because the first live test of this phase caught a real
  bug: with `--fast` (which skips walk-forward/cost-sensitivity), those
  two gates were reading `FAIL` (`breakeven_cost_profile=None`,
  `research_status` never reaching `WALK_FORWARD`) as if the alpha had
  been tested and failed, when it had never been tested at all. Regression
  test: `test_diagnostics_not_run_marks_wf_and_cost_gates_not_evaluated_not_fail`.
- **`agents/risk_agent.py`**: two checks the Statistician doesn't cover —
  did *any* Payout Optimizer policy manage to size a real position
  (`SIZING_FEASIBLE`), and does the realized trade sequence's max drawdown
  stay inside `prop.max_total_loss` (`DRAWDOWN_WITHIN_LIMITS`) — distinct
  from the Statistician's Monte-Carlo-simulated P(breach), which is about
  many simulated paths, not this one realized sequence.
- **`agents/critic.py`** (spec §59): findings, not gates — a `HIGH`
  severity finding blocks the Supervisor's verdict, `LOW`/`MEDIUM` are
  always surfaced but never block. Checks: `LOW_SAMPLE` (trade count),
  `OVERFIT_RISK` (DSR below threshold, or pool-level PBO above it),
  `REGIME_FRAGILE` (majority of regimes in the conditional-EV table show
  negative EV/trade), `EXECUTION_SENSITIVE` (breakeven cost profile is
  `None` or only `optimistic`), `HIDDEN_CORRELATION` (the top alpha's
  daily P&L correlates > threshold with a trivial baseline's, via the same
  `statistics.pbo.build_pnl_matrix` used for PBO — reused rather than
  hand-rolled to keep the day-alignment logic in one place), and, as of
  Phase 10, `ALPHA_DECAY` (severity scales with the Alpha Decay Monitor's
  level: HIGH for RED, MEDIUM for ORANGE, LOW for YELLOW, nothing for GREEN)
  and `FEATURE_DRIFT` (MEDIUM when any monitored feature's PSI exceeds
  `paper.psi_drift_threshold` between the in-sample and shadow periods).
- **`agents/supervisor.py`** (spec §58/§128): aggregates gates + findings
  into `PASSES_ALL_EVALUATED_GATES` or `RESEARCH_FAIL` — never a bare
  "PASS". The verdict's `disclaimer` always names every `NOT_EVALUATED`
  gate and states outright that this system must never declare an alpha
  "real-money ready" on its own; a `NOT_EVALUATED` gate can never by
  itself cause `RESEARCH_FAIL` (only an evaluated `FAIL` or a `HIGH`
  critic finding does).
- **`agents/audit.py`** (spec §129): every Supervisor verdict — pass or
  fail — is appended to `research_memory/audit/audit_trail.jsonl`
  (experiment ID, hypothesis, dataset/config hashes, result summary,
  decision, reasons), mirroring the Phase 7 `HypothesisLedger`'s
  append-only pattern; a past decision is never rewritten, only added to.

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
- **Fixed 1 contract for the main alpha ranking, by design**: the "Top
  Alpha Ranking" table always backtests 1 contract per signal, deliberately
  — comparing 12 alphas apples-to-apples means holding money-management
  choices constant across all of them (spec §112-113 rank *strategies*).
  The Position Sizing Engine and Payout Optimizer (Phase 5, see above) are
  a separate layer applied only to the #1-ranked alpha; `$` P&L in the main
  ranking table is still illustrative of relative pipeline/alpha quality,
  not of what a sized account would actually earn — that's what the Payout
  Optimizer section answers.
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
