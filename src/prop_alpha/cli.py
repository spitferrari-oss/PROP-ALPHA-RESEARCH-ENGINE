"""CLI entry point `pae` (spec §81, §82)."""
from __future__ import annotations

from pathlib import Path

import typer

from prop_alpha.backtest.costs import CostModel
from prop_alpha.backtest.engine import run_backtest, trades_to_frame
from prop_alpha.backtest.metrics import compute_day_metrics, compute_trade_metrics, daily_pnl
from prop_alpha.config import EngineConfig
from prop_alpha.data.loader import load_parquet, save_parquet
from prop_alpha.data.quality import validate_ohlcv
from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.pipeline import build_full_feature_set
from prop_alpha.prop.simulator import simulate_prop_paths
from prop_alpha.reporting.report import generate_report
from prop_alpha.statistics.bootstrap import bootstrap_daily_pnl
from prop_alpha.statistics.cost_sensitivity import breakeven_cost_profile, evaluate_cost_sensitivity
from prop_alpha.statistics.dsr import compute_dsr_for_pool
from prop_alpha.statistics.monte_carlo import simulate_daily_pnl_paths
from prop_alpha.statistics.pbo import build_pnl_matrix, compute_pbo
from prop_alpha.statistics.walk_forward import run_walk_forward
from prop_alpha.strategies.absorption_reversal import AbsorptionReversal
from prop_alpha.strategies.baselines import (
    BASELINE_STRATEGIES,
    RandomDirection,
    RandomEntry,
)
from prop_alpha.strategies.compression_expansion import CompressionExpansion
from prop_alpha.strategies.delta_acceleration_momentum import DeltaAccelerationMomentum
from prop_alpha.strategies.liquidity_sweep_reversal import LiquiditySweepReversal
from prop_alpha.strategies.momentum import IntradayMomentum
from prop_alpha.strategies.opening_drive_continuation import OpeningDriveContinuation
from prop_alpha.strategies.opening_range import OpeningRangeBreakout
from prop_alpha.strategies.prior_day_breakout import PriorDayHighLowBreakout
from prop_alpha.strategies.prior_day_reversal import PriorDayHighLowReversal
from prop_alpha.strategies.volume_profile_breakout import VolumeProfileBreakout
from prop_alpha.strategies.volume_profile_reversion import VolumeProfileMeanReversion
from prop_alpha.strategies.vwap_reversion import VwapMeanReversion
from prop_alpha.utils.hashing import git_commit_hash, hash_dict, hash_file, make_experiment_id

app = typer.Typer(help="Prop Alpha Research Engine CLI")
data_app = typer.Typer(help="Data pipeline commands")
strategy_app = typer.Typer(help="Strategy backtest/discovery commands")
research_app = typer.Typer(help="End-to-end research commands")
app.add_typer(data_app, name="data")
app.add_typer(strategy_app, name="strategy")
app.add_typer(research_app, name="research")

DEMO_RAW_PATH = "data/raw/nq_15m_synthetic.parquet"
DEMO_FEATURES_PATH = "data/features/nq_15m_features.parquet"

# The 12 MVP baseline strategies (spec §89) — "baseline" in the sense of
# benchmark alphas to validate the pipeline against, not the trivial
# no-edge comparators in strategies.baselines (spec §90).
ALPHA_STRATEGIES = [
    IntradayMomentum,               # ALPHA_01
    OpeningRangeBreakout,           # ALPHA_02
    VwapMeanReversion,              # ALPHA_03
    VolumeProfileMeanReversion,     # ALPHA_04
    VolumeProfileBreakout,          # ALPHA_05
    PriorDayHighLowReversal,        # ALPHA_06
    PriorDayHighLowBreakout,        # ALPHA_07
    DeltaAccelerationMomentum,      # ALPHA_08
    AbsorptionReversal,             # ALPHA_09
    LiquiditySweepReversal,         # ALPHA_10
    CompressionExpansion,           # ALPHA_11
    OpeningDriveContinuation,       # ALPHA_12
]


@data_app.command("generate-demo")
def data_generate_demo(
    n_days: int = 250,
    seed: int = 42,
    out: str = DEMO_RAW_PATH,
) -> None:
    """Generate a SYNTHETIC demo OHLCV dataset for pipeline testing (spec §123)."""
    df = generate_synthetic_ohlcv(n_days=n_days, seed=seed)
    path = save_parquet(df, out)
    typer.echo(f"[SYNTHETIC] wrote {len(df)} bars ({n_days} days) to {path}")


@data_app.command("validate")
def data_validate(path: str = DEMO_RAW_PATH) -> None:
    df = load_parquet(path)
    report = validate_ohlcv(df)
    if report.is_valid:
        typer.echo(f"OK: {report.n_rows} rows, no data quality issues found.")
    else:
        typer.echo(f"INVALID: {report.issues}")
        raise typer.Exit(code=1)


@data_app.command("features")
def data_features(
    in_path: str = DEMO_RAW_PATH,
    out_path: str = DEMO_FEATURES_PATH,
    config: str = typer.Option(None, help="Path to a YAML EngineConfig; defaults built in if omitted"),
) -> None:
    engine_config = EngineConfig.from_yaml(config) if config else EngineConfig()
    df = load_parquet(in_path)
    feats = build_full_feature_set(df, engine_config)
    save_parquet(feats, out_path)
    typer.echo(f"wrote features for {len(feats)} bars to {out_path}")


def _evaluate_strategy(strategy, df_feat, cost_model, config, oos_start_day, run_diagnostics: bool) -> tuple[dict, "pd.Series"]:
    """Backtest one strategy and run its statistical validation gates (spec
    §60 Research Gates): OOS split, bootstrap, Monte Carlo/prop simulation,
    and — for real alpha candidates only (`run_diagnostics=True`) — walk-
    forward stability and a cost-sensitivity stress test. Baseline
    comparators (spec §90) skip the last two since they aren't candidates
    for promotion, just a floor every alpha must clear.

    Returns (result_dict, daily_pnl_series) — the latter feeds the
    cross-strategy PBO/DSR diagnostics computed once after every strategy
    has been evaluated.
    """
    df_signals = strategy.with_risk_levels(df_feat)
    trades = run_backtest(
        df_signals,
        cost_model=cost_model,
        max_trades_day=config.risk.max_trades_day,
        point_value=config.market.point_value,
    )
    trades_df = trades_to_frame(trades)

    trade_metrics = compute_trade_metrics(trades_df)
    day_metrics = compute_day_metrics(trades_df)
    dpnl = daily_pnl(trades_df)

    oos_trades = trades_df[trades_df["exit_time"].dt.date >= oos_start_day] if not trades_df.empty else trades_df
    oos_ev_day = compute_day_metrics(oos_trades)["ev_per_day_dollars"]

    boot = bootstrap_daily_pnl(dpnl, n_boot=1000, seed=config.seed) if len(dpnl) > 5 else None

    mc_paths = simulate_daily_pnl_paths(dpnl, n_paths=5000, n_days=30, seed=config.seed) if len(dpnl) > 1 else None
    prop_sim = (
        simulate_prop_paths(mc_paths, config.prop)
        if mc_paths is not None
        else {"p_breach": float("nan"), "p_payout": float("nan"), "expected_payout": float("nan"),
              "expected_days_to_payout": float("nan")}
    )

    wf = None
    cost_sensitivity = None
    breakeven_profile = None
    if run_diagnostics and not trades_df.empty:
        wf = run_walk_forward(
            strategy, df_feat, cost_model,
            max_trades_day=config.risk.max_trades_day,
            point_value=config.market.point_value,
            n_folds=5,
        )
        cost_sensitivity = evaluate_cost_sensitivity(
            df_signals, cost_model,
            max_trades_day=config.risk.max_trades_day,
            point_value=config.market.point_value,
        )
        breakeven_profile = breakeven_cost_profile(cost_sensitivity)

    wf_positive_fraction = wf["positive_fold_fraction"] if wf else float("nan")
    is_walk_forward_robust = run_diagnostics and wf is not None and wf_positive_fraction >= 0.6

    if is_walk_forward_robust and oos_ev_day is not None and oos_ev_day > 0:
        research_status = "WALK_FORWARD"
    elif oos_ev_day is not None and oos_ev_day > 0:
        research_status = "OUT_OF_SAMPLE"
    else:
        research_status = "BACKTESTED"

    result = {
        "alpha_id": strategy.meta.alpha_id,
        "alpha_name": strategy.meta.alpha_name,
        "family": strategy.meta.family,
        "mechanism": strategy.meta.mechanism,
        "research_status": research_status,
        **trade_metrics,
        **day_metrics,
        "boot_ev_p5": boot["ev_per_day"]["p5"] if boot else float("nan"),
        "boot_ev_p95": boot["ev_per_day"]["p95"] if boot else float("nan"),
        "mc_n_paths": prop_sim.get("n_paths", "n/a"),
        "mc_n_days": prop_sim.get("n_days_horizon", "n/a"),
        "p_breach": prop_sim["p_breach"],
        "p_payout": prop_sim["p_payout"],
        "expected_payout": prop_sim["expected_payout"],
        "expected_days_to_payout": prop_sim["expected_days_to_payout"],
        "wf_n_folds": wf["n_folds"] if wf else None,
        "wf_positive_fold_fraction": wf_positive_fraction,
        "wf_worst_fold_ev_per_day": wf["worst_fold_ev_per_day"] if wf else float("nan"),
        "wf_fold_ev_per_day": wf["fold_ev_per_day"] if wf else None,
        "cost_sensitivity": cost_sensitivity,
        "breakeven_cost_profile": breakeven_profile,
    }
    return result, dpnl


def _instantiate_baselines(seed: int) -> list:
    instances = []
    for strat_cls in BASELINE_STRATEGIES:
        if strat_cls is RandomEntry:
            instances.append(strat_cls(seed=seed))
        elif strat_cls is RandomDirection:
            instances.append(strat_cls(seed=seed + 1))
        else:
            instances.append(strat_cls())
    return instances


def _run_full_research(config_path: str | None, n_days: int, out_dir: str, fast: bool = False) -> Path:
    config = EngineConfig.from_yaml(config_path) if config_path else EngineConfig()

    raw_path = Path(DEMO_RAW_PATH)
    df_raw = generate_synthetic_ohlcv(n_days=n_days, seed=config.seed)
    save_parquet(df_raw, raw_path)

    quality = validate_ohlcv(df_raw)
    if not quality.is_valid:
        typer.echo(f"BACKTEST STATUS = INVALID: {quality.issues}")
        raise typer.Exit(code=1)

    df_feat = build_full_feature_set(df_raw, config)
    save_parquet(df_feat, DEMO_FEATURES_PATH)

    unique_days = sorted(df_feat["timestamp"].dt.date.unique())
    oos_start_day = unique_days[int(len(unique_days) * 0.8)]

    cost_model = CostModel(
        tick_size=config.market.tick_size,
        tick_value=config.market.tick_value,
        commission_per_round_turn=config.cost.commission_per_round_turn,
        slippage_ticks=config.cost.slippage_ticks,
        spread_ticks=config.cost.spread_ticks,
    )

    alpha_instances = [cls() for cls in ALPHA_STRATEGIES]
    baseline_instances = _instantiate_baselines(config.seed)

    results = []
    alpha_daily_pnl = {}
    for strategy in alpha_instances:
        result, dpnl = _evaluate_strategy(strategy, df_feat, cost_model, config, oos_start_day, run_diagnostics=not fast)
        results.append(result)
        alpha_daily_pnl[result["alpha_id"]] = dpnl
    for strategy in baseline_instances:
        result, _ = _evaluate_strategy(strategy, df_feat, cost_model, config, oos_start_day, run_diagnostics=False)
        results.append(result)

    # Cross-strategy overfitting diagnostics (spec §30): computed once over
    # the alpha trial pool, not per-strategy — PBO/DSR are statements about
    # the *selection process* across all candidates tried, not about any one
    # alpha in isolation.
    pnl_matrix = build_pnl_matrix(alpha_daily_pnl, unique_days)
    pbo_result = compute_pbo(pnl_matrix, n_splits=8)
    dsr_by_alpha = compute_dsr_for_pool(alpha_daily_pnl)
    for r in results:
        dsr = dsr_by_alpha.get(r["alpha_id"])
        r["dsr"] = dsr["dsr"] if dsr else float("nan")

    experiment_id = make_experiment_id()
    meta = {
        "git_commit": git_commit_hash(),
        "config_hash": hash_dict(config.model_dump()),
        "dataset_hash": hash_file(raw_path),
        "dataset_source": df_raw.attrs.get("source", "unknown"),
        "seed": config.seed,
    }
    diagnostics = {"pbo": pbo_result, "dsr_by_alpha": dsr_by_alpha}
    report_path = generate_report(results, experiment_id, meta, diagnostics=diagnostics, out_dir=out_dir)
    return report_path


@research_app.command("full-run")
def research_full_run(
    config: str = typer.Option(None, help="Path to a YAML EngineConfig; defaults built in if omitted"),
    n_days: int = 250,
    out_dir: str = "reports",
    fast: bool = typer.Option(
        False, help="Skip walk-forward analysis and cost-sensitivity stress testing (spec §26/§23) for"
        " faster iteration. PBO/DSR and the OOS/bootstrap/Monte Carlo/prop gates still run."
    ),
) -> None:
    """Run the full pipeline: data -> features -> backtest -> OOS -> Monte
    Carlo -> prop simulation -> walk-forward -> cost sensitivity -> PBO/DSR
    -> ranking -> report (spec §82, §122).
    """
    report_path = _run_full_research(config, n_days, out_dir, fast=fast)
    typer.echo(f"Report written to {report_path}")


if __name__ == "__main__":
    app()
