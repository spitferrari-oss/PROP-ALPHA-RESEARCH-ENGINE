"""CLI entry point `pae` (spec §81, §82)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import typer

from prop_alpha.agents.audit import AuditEntry, AuditTrail
from prop_alpha.agents.critic import evaluate_critic_findings
from prop_alpha.agents.risk_agent import evaluate_risk_gates
from prop_alpha.agents.statistician import evaluate_statistician_gates
from prop_alpha.agents.supervisor import review
from prop_alpha.backtest.costs import CostModel
from prop_alpha.backtest.engine import run_backtest, trades_to_frame
from prop_alpha.backtest.metrics import compute_day_metrics, compute_trade_metrics, daily_pnl
from prop_alpha.config import EngineConfig
from prop_alpha.data.loader import load_parquet, save_parquet
from prop_alpha.data.quality import validate_ohlcv
from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.discovery.hypothesis import HypothesisLedger
from prop_alpha.discovery.pipeline import run_discovery
from prop_alpha.governance.constitution import (
    ConstitutionError,
    assert_constitution_valid,
    get_constitution_status,
)
from prop_alpha.features.pipeline import build_full_feature_set
from prop_alpha.ml.features import build_ml_feature_matrix
from prop_alpha.ml.meta_alpha import evaluate_meta_alpha
from prop_alpha.paper.decay import classify_alpha_decay
from prop_alpha.paper.drift import compute_feature_drift
from prop_alpha.paper.monitor import evaluate_paper_monitor
from prop_alpha.paper.shadow import build_shadow_log
from prop_alpha.prop.simulator import simulate_prop_paths
from prop_alpha.regimes.conditional_ev import conditional_ev_by_regime
from prop_alpha.regimes.pipeline import build_regime_features
from prop_alpha.reporting.discovery_report import generate_discovery_report
from prop_alpha.reporting.report import generate_report, rank_alphas
from prop_alpha.risk.payout_optimizer import compare_policies, default_policies
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
options_app = typer.Typer(help="Options intelligence commands (Data Feed extension)")
data_center_app = typer.Typer(help="Data Center dashboard commands (Data Feed extension)")
replay_app = typer.Typer(help="Historical replay commands (Data Feed extension)")
live_shadow_app = typer.Typer(help="Live shadow mode trade proposal commands (Data Feed extension)")
constitution_app = typer.Typer(help="Research Constitution governance commands (hardening pass)")
system_app = typer.Typer(help="Environment/dependency diagnostics (hardening pass)")
app.add_typer(data_app, name="data")
app.add_typer(strategy_app, name="strategy")
app.add_typer(research_app, name="research")
app.add_typer(options_app, name="options")
app.add_typer(data_center_app, name="data-center")
app.add_typer(replay_app, name="replay")
app.add_typer(live_shadow_app, name="live-shadow")
app.add_typer(constitution_app, name="constitution")
app.add_typer(system_app, name="system")


def _require_valid_constitution(command_name: str) -> None:
    """The Constitution pre-check every governance-gated command calls
    before doing meaningful work (hardening pass Step 4, "Constitution
    pre-check"). Deliberately does not catch `ConstitutionError` — Typer
    turns an uncaught exception into a non-zero exit with the error
    message printed, which is exactly "DO NOT CONTINUE," not a silent
    degraded-mode continuation.

    Note on command coverage: the hardening spec names `pae strategy
    backtest`/`validate`/`discover`, `pae portfolio optimize`, and `pae
    prop simulate` as the commands to gate. None of those exist as
    separate CLI commands in this repository — backtesting, discovery,
    and prop simulation all happen inline inside `pae research full-run`/
    `pae research discover`/`pae research gex-templates`, and no
    standalone `portfolio`/`prop simulate` command was ever built. This
    gate is wired into the three commands that actually perform that
    work instead of adding hollow stub commands just to match names that
    don't correspond to real functionality here (see `reports/
    hardening_report.md`).
    """
    try:
        assert_constitution_valid()
    except ConstitutionError as exc:
        typer.echo(f"STATUS: CONSTITUTION INVALID\nRESEARCH EXECUTION BLOCKED\n\n{exc}", err=True)
        raise typer.Exit(code=1) from exc


@constitution_app.command("show")
def constitution_show() -> None:
    """Print the Research Constitution's raw content (hardening pass)."""
    from prop_alpha.governance.constitution import DEFAULT_CONSTITUTION_PATH

    typer.echo(DEFAULT_CONSTITUTION_PATH.read_text())


@constitution_app.command("hash")
def constitution_hash_cmd() -> None:
    """Print the Constitution file's current SHA256 (hardening pass)."""
    from prop_alpha.governance.constitution import calculate_constitution_hash

    typer.echo(calculate_constitution_hash())


@constitution_app.command("verify")
def constitution_verify_cmd() -> None:
    """Verify the Constitution against its lock file; non-zero exit and
    'STATUS: CONSTITUTION INVALID' on failure (hardening pass).
    """
    status = get_constitution_status()
    _print_constitution_status(status)
    if status["status"] != "CONSTITUTION VALID":
        raise typer.Exit(code=1)


@constitution_app.command("status")
def constitution_status_cmd() -> None:
    """Same report as `verify`, without the non-zero exit on failure —
    for scripts that want to inspect status without branching on exit
    code (hardening pass).
    """
    _print_constitution_status(get_constitution_status())


def _print_constitution_status(status: dict) -> None:
    typer.echo("PROP ALPHA ENGINE")
    typer.echo("CONSTITUTION STATUS")
    typer.echo("─" * 32)
    typer.echo("")
    typer.echo(f"ID:       {status['id']}")
    typer.echo(f"VERSION:  {status['version']}")
    typer.echo(f"HASH:     {status['hash']}")
    typer.echo("")
    typer.echo(f"Integrity: {status['integrity']}")
    typer.echo(f"Lockfile:  {status['lockfile']}")
    typer.echo(f"Version:   {status['version_check']}")
    typer.echo("")
    typer.echo(f"STATUS: {status['status']}")
    if status["status"] != "CONSTITUTION VALID":
        typer.echo("RESEARCH EXECUTION BLOCKED")
        for error in status["errors"]:
            typer.echo(f"  - {error}")


_CORE_DEPENDENCIES = [
    ("pandas", "PANDAS"), ("numpy", "NUMPY"), ("scipy", "SCIPY"),
    ("pyarrow", "PYARROW"), ("duckdb", "DUCKDB"), ("yaml", "PYYAML"),
    ("pydantic", "PYDANTIC"), ("typer", "TYPER"), ("sklearn", "SKLEARN"),
]
_OPTIONAL_DEPENDENCIES = [
    ("databento", "DATABENTO SDK"), ("requests", "REQUESTS / GEXBOT CLIENT"),
]


@system_app.command("doctor")
def system_doctor() -> None:
    """Hardening pass (Step 3, Blocker F): environment/dependency
    diagnostics. Reports Python and every core/optional package's
    installed state, version, and required/optional classification.
    Never silently imports an optional package as a side effect of
    anything else — the only import this command performs on an
    optional package is this explicit, reported check.
    """
    import importlib
    import sys

    typer.echo("PARE SYSTEM DOCTOR")
    typer.echo("")
    typer.echo(f"PYTHON          {sys.version.split()[0]:<14} required=True  (>=3.11)")
    typer.echo("")
    typer.echo("PACKAGE INSTALLATION")

    all_required_ok = True
    for module_name, label in _CORE_DEPENDENCIES:
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", "unknown")
            typer.echo(f"{label:<24} INSTALLED       version={version:<14} required=True   optional=False")
        except ImportError:
            all_required_ok = False
            typer.echo(f"{label:<24} MISSING         version={'n/a':<14} required=True   optional=False")

    typer.echo("")
    for module_name, label in _OPTIONAL_DEPENDENCIES:
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", "unknown")
            typer.echo(f"{label:<24} INSTALLED       version={version:<14} required=False  optional=True")
        except ImportError:
            typer.echo(f"{label:<24} NOT INSTALLED   version={'n/a':<14} required=False  optional=True")

    typer.echo("")
    typer.echo(f"OVERALL: {'PASS' if all_required_ok else 'FAIL — missing required package(s)'}")
    if not all_required_ok:
        raise typer.Exit(code=1)


@system_app.command("test")
def system_test() -> None:
    """Hardening pass (Step 47): runs the test suite grouped by marker
    (UNIT/INTEGRATION/PROVIDER/NETWORK/LIVE) and summarizes PASS/FAIL/
    SKIP/BLOCKED per group. As of this hardening pass, every test in
    this repository runs fully offline via dependency-injected fakes and
    mocks — none carry `network`/`provider`/`live` markers yet, because
    none of them actually need real credentials to run. That means the
    NETWORK/PROVIDER/LIVE groups below legitimately report 0 tests, not
    a fabricated PASS; that is the accurate state of this repository, see
    reports/hardening_report.md.
    """
    import subprocess
    import sys

    groups = [
        ("UNIT", "not integration and not network and not provider and not live"),
        ("INTEGRATION", "integration"),
        ("PROVIDER", "provider"),
        ("NETWORK", "network"),
        ("LIVE", "live"),
    ]

    typer.echo("PARE SYSTEM TEST")
    typer.echo("")
    any_failed = False
    for label, expr in groups:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-m", expr],
            capture_output=True, text=True,
        )
        stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
        summary_line = stdout_lines[-1] if stdout_lines else "(no output)"
        # pytest exit code 5 == no tests collected for this -m expression (not a failure)
        if result.returncode == 5 or "0 passed" in summary_line and "failed" not in summary_line:
            status = "BLOCKED (0 tests collected for this marker)"
        elif result.returncode == 0:
            status = "PASS"
        else:
            status = "FAIL"
            any_failed = True
        typer.echo(f"{label:<12} {status:<40} {summary_line}")

    typer.echo("")
    typer.echo(f"OVERALL: {'FAIL' if any_failed else 'PASS'}")
    if any_failed:
        raise typer.Exit(code=1)


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


@data_app.command("record")
def data_record(
    instrument: str = typer.Option(..., help="Generic instrument symbol (e.g. NQ) — see providers.databento.symbology"),
    level: str = typer.Option("L1", help="DataLevel to subscribe at: L1, L2, L3, or L4"),
    duration_seconds: float = typer.Option(30.0, help="How long to record; Ctrl+C stops early"),
    lake_root: str = typer.Option("data/lake", help="Data lake root (extension spec §6)"),
    recording_config: str = typer.Option(None, help="Path to a YAML RecordingConfig; defaults built in if omitted"),
) -> None:
    """Data Feed extension (§14/§101, Phase F): shadow-record a live
    Databento feed to the local data lake's `raw` tier. Requires
    `DATABENTO_API_KEY` and the `databento` package
    (`pip install 'prop-alpha-engine[databento]'`) — this command is not
    exercised by the test suite for that reason (extension §134/§136);
    `data.live.session.record_live_session` is, via an injected fake
    provider.
    """
    from prop_alpha.data.lake import DataLakePaths
    from prop_alpha.data.live.session import record_live_session
    from prop_alpha.data.recording_config import RecordingConfig
    from prop_alpha.providers.base import DataLevel
    from prop_alpha.providers.databento import DatabentoProvider
    from prop_alpha.providers.databento.symbology import DEFAULT_SCHEMA_BY_LEVEL

    data_level = DataLevel(level)
    config = RecordingConfig.from_yaml(recording_config) if recording_config else RecordingConfig()
    lake = DataLakePaths(root=Path(lake_root))

    try:
        result = record_live_session(
            provider_factory=lambda recorder: DatabentoProvider(recorder=recorder),
            provider_name="databento",
            instrument=instrument,
            level=data_level,
            schema_for_path=DEFAULT_SCHEMA_BY_LEVEL[data_level],
            lake=lake,
            duration_seconds=duration_seconds,
            config=config,
        )
    except KeyboardInterrupt:
        typer.echo("Recording interrupted.")
        raise typer.Exit(code=0)

    if not result.recorded:
        typer.echo("Recording disabled (recording.enabled=false) — nothing written.")
    else:
        typer.echo(f"Recorded {result.message_count} messages to {result.output_path}")


@data_app.command("ingest")
def data_ingest(
    instrument: str = typer.Option(..., help="Generic instrument symbol (e.g. NQ) — see providers.databento.symbology"),
    start: str = typer.Option(..., help="Start date, YYYY-MM-DD"),
    end: str = typer.Option(..., help="End date, YYYY-MM-DD (inclusive)"),
    level: str = typer.Option("L1", help="DataLevel to fetch at: L1, L2, L3, or L4"),
    lake_root: str = typer.Option("data/lake", help="Data lake root (extension spec §6)"),
    max_retries: int = typer.Option(3, help="Retries per day before marking it FAILED"),
) -> None:
    """Data Feed extension (§10, Phase G): incremental historical
    ingestion into the data lake's `raw` tier — one day at a time,
    resumable (already-written days are skipped), retried, quality-gated.
    Requires `DATABENTO_API_KEY` and the `databento` package (see `pae
    data record`'s docstring) — not exercised by the test suite for that
    reason; `data.ingest.ingest_historical`'s orchestration is, via a
    scripted fake provider.
    """
    from prop_alpha.data.ingest import ingest_historical
    from prop_alpha.data.lake import DataLakePaths
    from prop_alpha.providers.base import DataLevel
    from prop_alpha.providers.databento import DatabentoProvider
    from prop_alpha.providers.databento.symbology import DEFAULT_SCHEMA_BY_LEVEL

    data_level = DataLevel(level)
    lake = DataLakePaths(root=Path(lake_root))

    result = ingest_historical(
        provider=DatabentoProvider(),
        instrument=instrument,
        level=data_level,
        schema=DEFAULT_SCHEMA_BY_LEVEL[data_level],
        start=dt.date.fromisoformat(start),
        end=dt.date.fromisoformat(end),
        lake=lake,
        max_retries=max_retries,
    )

    typer.echo(
        f"Ingest complete: {result.n_written} written, {result.n_skipped_existing} already present, "
        f"{result.n_quality_blocked} quality-blocked, {result.n_failed} failed."
    )
    for day_result in result.days:
        if day_result.status == "FAILED":
            typer.echo(f"  FAILED {day_result.date}: {day_result.error}")
        elif day_result.quality_blocked:
            typer.echo(f"  WRITTEN but quality-blocked {day_result.date}: {list(day_result.blocked_reasons)}")


@options_app.command("snapshot")
def options_snapshot(
    underlying: str = typer.Option(..., help="Underlying ticker (e.g. SPX, NDX, SPY, QQQ)"),
) -> None:
    """Data Feed extension (§104, Phase H/I): fetch one GEXBOT snapshot,
    normalize it into the vendor-agnostic `OptionsSnapshot` (extension
    §28), and print each metric's value and availability status.
    Requires `GEXBOT_API_KEY` and the `requests` package (see `pae data
    record`'s docstring for the equivalent Databento caveat) — not
    exercised by the test suite for that reason; the normalization
    pipeline itself is, via an injected fake client
    (`tests/test_options_normalize.py`, `tests/test_gexbot_provider.py`).
    """
    from prop_alpha.providers.gexbot import GexbotOptionsProvider

    provider = GexbotOptionsProvider()
    snapshot = provider.get_snapshot(underlying)

    typer.echo(f"GEXBOT snapshot for {underlying} at {snapshot['timestamp']}")
    for name in (
        "spot", "gex", "dex", "gamma_flip", "major_positive_gamma", "major_negative_gamma",
        "vanna", "charm", "vomma", "skew", "options_volume", "open_interest",
    ):
        metric = snapshot[name]
        status = metric["availability"]["status"]
        value = f"{metric['value']:.4g}" if metric["value"] is not None else "n/a"
        typer.echo(f"  {name:<22} {value:>14}   [{status}]")


@options_app.command("verify-provider")
def options_verify_provider(
    underlying: str = typer.Option("SPX", help="Underlying ticker to check against"),
    report_dir: str = typer.Option(
        "provider_capability_reports", help="Directory to save the capability report JSON to",
    ),
) -> None:
    """Hardening pass (Step 22, Blocker G): a real, one-shot GEXBOT
    contract check — authenticate, make exactly one documented/safe call
    (`get_gex`), and inspect the actual response structure field by
    field. Never guesses at an undocumented endpoint and never reports a
    metric AVAILABLE unless it was actually present in the response.
    Requires `GEXBOT_API_KEY` and the `requests` package; if either is
    missing, or the network call fails for any reason, this reports
    UNAVAILABLE/FAIL honestly rather than a fabricated pass — that is the
    correct, expected result in this environment (no network access, no
    GEXBOT account), not a bug.
    """
    from prop_alpha.options.gexbot.capability import save_capability_report, verify_provider_contract

    report = verify_provider_contract(underlying=underlying)
    report_path = save_capability_report(report, out_dir=report_dir)

    typer.echo("GEXBOT PROVIDER VERIFICATION")
    typer.echo("")
    typer.echo(f"Authentication: {report.authentication}")
    for name in ("gex", "dex", "gamma_flip", "vanna", "charm", "vomma", "skew"):
        label = name.replace("_", " ").title() if name != "gex" and name != "dex" else name.upper()
        typer.echo(f"{label + ':':<16}{report.metric_availability.get(name, 'NOT_CHECKED')}")
    typer.echo(f"Orderflow:      {report.orderflow_capability}")
    typer.echo("")
    typer.echo(f"Provider status:\n{report.contract_state}")
    if report.error:
        typer.echo(f"\nDetail: {report.error}")
    typer.echo(f"\nCapability report saved to {report_path}")


@options_app.command("historical")
def options_historical(
    underlying: str = typer.Option(..., help="Underlying ticker"),
) -> None:
    """Hardening pass (Step 26): explicit honesty about GEXBOT historical
    data. GEXBOT's own API has no historical endpoint this repo has ever
    verified (extension §62's limitation); PARE's own proprietary options
    history only accumulates once live recording begins (`options.
    recording`). This command distinguishes PROVIDER_HISTORICAL (never
    available from GEXBOT here) from PARE_RECORDED_HISTORY (only
    available once a recorder has actually been run for this underlying)
    rather than inventing historical GEX data.
    """
    typer.echo(f"pae options historical --underlying {underlying}")
    typer.echo("")
    typer.echo("PROVIDER_HISTORICAL: NOT_AVAILABLE")
    typer.echo(
        "  GEXBOT's API has no historical endpoint this repo has ever verified "
        "(extension §62). GexbotOptionsProvider.get_historical raises NotImplementedError."
    )
    typer.echo("")
    typer.echo("PARE_RECORDED_HISTORY: NOT_AVAILABLE")
    typer.echo(
        "  No options snapshots have been recorded for this underlying via "
        "options.recording.recorder.OptionsRecorder in this environment. Once a "
        "recording session has been run and produced stored snapshot partitions, "
        "this command reports what's actually on disk instead of NOT_AVAILABLE."
    )


@data_center_app.command("status")
def data_center_status(
    underlying: str = typer.Option(
        None, help="Underlying ticker for the options feed status (e.g. SPX). Omit to skip the options feed section.",
    ),
) -> None:
    """Data Feed extension (§105-109, Phase M): assemble and print the
    cross-market Data Center status (extension §21/§54's `FeedHealth`/
    `DataQualityReport` combined with GEXBOT health, per
    `data_center.status`'s aggregation).

    This one-shot CLI invocation can only report what it can compute
    synchronously right here: the futures feed section needs an
    already-running `ConnectionManager`/`MessageBuffer` pair from an
    active `pae data record` session (a separate long-lived process this
    command doesn't have access to), and the data quality section needs
    an already-computed `DataQualityReport` (e.g. from `pae data
    ingest`), so both print "not available" rather than a fabricated
    status. Only the options feed — a single synchronous GEXBOT poll — is
    actually populated here. Requires `GEXBOT_API_KEY` and the `requests`
    package when `--underlying` is given; not exercised by the test suite
    for that reason (the aggregation/rendering it calls into is, via
    injected `FeedHealth`/`GexbotHealth`/`DataQualityReport` fixtures in
    `tests/test_data_center_{status,render}.py`).
    """
    from prop_alpha.data_center.render import render_status_markdown
    from prop_alpha.data_center.status import assemble_data_center_status
    from prop_alpha.options.gexbot.client import GexbotClient
    from prop_alpha.options.gexbot.health import compute_health
    from prop_alpha.options.gexbot.parser import parse_snapshot

    options_feed = None
    data_source = "NOT_CONNECTED"
    if underlying:
        client = GexbotClient()
        raw = client.get_gex(underlying)
        gex_snapshot = parse_snapshot(raw, underlying)
        options_feed = compute_health(gex_snapshot, connected=True, authenticated=True, n_polls=1, n_errors=0)
        data_source = "REAL"  # a real GEXBOT HTTP call just succeeded — never label this MOCK/SYNTHETIC

    status = assemble_data_center_status(options_feed=options_feed, data_source=data_source)
    typer.echo(render_status_markdown(status))


@replay_app.command("run")
def replay_run(
    provider: str = typer.Option(..., help="Provider partition to replay (e.g. databento)"),
    instrument: str = typer.Option(..., help="Instrument partition to replay (e.g. ES)"),
    schema: str = typer.Option(..., help="Schema partition to replay (e.g. ohlcv-1m)"),
    tier: str = typer.Option("raw", help="Data lake tier to replay from (extension §6)"),
    lake_root: str = typer.Option("data/lake", help="Data lake root"),
    speed: float = typer.Option(0.0, help="0 = as fast as possible; 1.0 = real-time; 2.0 = 2x real-time; ..."),
) -> None:
    """Data Feed extension (§56-58, Phase N): deterministically replay an
    already-ingested historical lake partition through the same
    `LiveMessageEnvelope`/`EventRouter` shape a live subscription would
    use (`replay.reader.dataframe_to_envelopes` + `replay.engine.
    replay_envelopes`), printing each event as it's dispatched. This CLI
    command needs a real ingested lake partition (`pae data ingest`) to
    run against, so it isn't exercised by the test suite itself — the
    reader/engine logic it calls into is
    (`tests/test_replay_{reader,engine}.py`).
    """
    from prop_alpha.data.lake import DataLakePaths
    from prop_alpha.data.lake_query import query_tier
    from prop_alpha.data.live.event_router import EventRouter
    from prop_alpha.replay.engine import replay_envelopes
    from prop_alpha.replay.reader import dataframe_to_envelopes

    lake = DataLakePaths(root=Path(lake_root))
    df = query_tier(lake, tier, provider=provider, instrument=instrument, schema=schema)
    envelopes = dataframe_to_envelopes(df, provider=provider, instrument=instrument, schema=schema)

    router = EventRouter()
    router.subscribe(lambda e: typer.echo(f"{e.timestamp_normalized.isoformat()}  {e.payload}"))

    result = replay_envelopes(envelopes, on_envelope=router.route, speed=(speed or None))
    typer.echo(
        f"Replay complete: {result.n_events} events, "
        f"{result.start_timestamp} -> {result.end_timestamp}, "
        f"{result.wall_clock_seconds:.3f}s wall-clock."
    )


@live_shadow_app.command("list")
def live_shadow_list(
    ledger_path: str = typer.Option("research_memory/live_shadow/proposals.jsonl", help="Live shadow ledger path"),
    status: str = typer.Option(None, help="Filter to one status: PENDING, APPROVED, or REJECTED"),
) -> None:
    """Data Feed extension (§76-80, Phase O): list logged trade proposals
    — never executed orders, purely a review queue. `status` narrows to
    one `ProposalStatus`; omit it to see everything logged so far.
    """
    from prop_alpha.live_shadow.ledger import LiveShadowLedger

    ledger = LiveShadowLedger(path=ledger_path)
    records = ledger.read_proposals()
    if status:
        records = [r for r in records if r["status"] == status]

    if not records:
        typer.echo("No proposals found.")
        return
    for r in records:
        typer.echo(
            f"{r['proposal_id']}  {r['timestamp']}  {r['instrument']} {r['direction']}  "
            f"entry={r['entry_price']}  [{r['status']}]  {r['rationale']}"
        )


@live_shadow_app.command("decide")
def live_shadow_decide(
    proposal_id: str = typer.Option(..., help="Proposal ID to decide on (from `pae live-shadow list`)"),
    decision: str = typer.Option(..., help="APPROVED or REJECTED"),
    reviewer: str = typer.Option(..., help="Name/identifier of the human reviewer"),
    rationale: str = typer.Option(None, help="Optional free-text rationale for the decision"),
    ledger_path: str = typer.Option("research_memory/live_shadow/proposals.jsonl", help="Live shadow ledger path"),
) -> None:
    """Data Feed extension (§78-80, Phase O): record a human reviewer's
    APPROVED/REJECTED decision on a logged trade proposal. This only ever
    updates the ledger's record of what was decided — extension §132/§162
    mean this never sends, simulates as filled, or otherwise activates a
    real order.
    """
    from prop_alpha.live_shadow.feedback import apply_feedback
    from prop_alpha.live_shadow.ledger import LiveShadowLedger
    from prop_alpha.live_shadow.proposal import ProposalStatus, proposal_from_record

    ledger = LiveShadowLedger(path=ledger_path)
    matches = [r for r in ledger.read_proposals() if r["proposal_id"] == proposal_id]
    if not matches:
        typer.echo(f"No proposal found with id {proposal_id!r}.", err=True)
        raise typer.Exit(code=1)
    if any(f["proposal_id"] == proposal_id for f in ledger.read_feedback()):
        typer.echo(f"Proposal {proposal_id!r} already has a recorded decision.", err=True)
        raise typer.Exit(code=1)

    proposal = proposal_from_record(matches[-1])
    _, feedback = apply_feedback(
        proposal, ProposalStatus(decision), reviewer=reviewer, rationale=rationale,
    )
    ledger.record_feedback(feedback)
    typer.echo(f"Recorded {decision} for proposal {proposal_id} by {reviewer}.")


@live_shadow_app.command("start")
def live_shadow_start(
    instrument: str = typer.Option("NQ", help="Instrument to subscribe to"),
    provider: str = typer.Option(
        "mock", help="Futures provider: 'mock' (MockFuturesDataProvider, always available) or 'databento' "
                     "(real provider — requires DATABENTO_API_KEY and the databento package)",
    ),
    mode: str = typer.Option(
        "LIVE_SHADOW",
        help="REPLAY_SHADOW / LIVE_SHADOW / PAPER / LIVE_HUMAN_APPROVAL / LIVE_AUTO. LIVE_AUTO is representable "
             "as a label but nothing in this repository ever executes a real order regardless of mode — see "
             "execution.gateway.",
    ),
    status_path: str = typer.Option(
        "research_memory/live_shadow/session_status.json", help="Where to persist session status",
    ),
    ledger_path: str = typer.Option("research_memory/live_shadow/proposals.jsonl", help="Live shadow ledger path"),
) -> None:
    """Hardening pass (Step 36-39, Blocker C): runs the real PROVIDER ->
    NORMALIZATION -> FEATURES -> REGIME -> ALPHA -> NO-TRADE -> RISK ->
    PAPER/SHADOW PROPOSAL pipeline (`live_shadow.session.
    run_live_shadow_session`) against a subscribed futures provider.

    This environment has no background-daemon/process-supervisor
    infrastructure, so this command runs synchronously to completion (the
    mock provider delivers a short deterministic burst of bars and
    finishes; a real provider's `subscribe_live` would run until its
    caller stops it) rather than actually daemonizing — `pae live-shadow
    status`/`stop` read/update the status file this command writes,
    honestly, rather than pretending to signal a background process.

    No alpha/proposal generator is wired into this command by default —
    every bar is evaluated against the no-trade gate with no supplied
    expected value, so `NO_EDGE` blocks every proposal and nothing is
    logged. That is the safe, honest default: this command exists to
    prove the pipeline wiring itself works end to end, not to propose
    real trades without an explicit alpha behind them.
    """
    from prop_alpha.live_shadow.ledger import LiveShadowLedger
    from prop_alpha.live_shadow.session import LiveShadowMode, run_live_shadow_session
    from prop_alpha.providers.base import DataLevel
    from prop_alpha.providers.mocks import MockFuturesDataProvider

    if provider == "mock":
        futures_provider = MockFuturesDataProvider()
        data_source = "MOCK"
    elif provider == "databento":
        from prop_alpha.providers.databento import DatabentoProvider

        futures_provider = DatabentoProvider()
        data_source = "REAL"
    else:
        typer.echo(f"Unknown provider {provider!r}. Use 'mock' or 'databento'.", err=True)
        raise typer.Exit(code=1)

    try:
        shadow_mode = LiveShadowMode(mode)
    except ValueError:
        typer.echo(f"Unknown mode {mode!r}. Use one of {[m.value for m in LiveShadowMode]}.", err=True)
        raise typer.Exit(code=1)

    status = run_live_shadow_session(
        futures_provider, instrument=instrument, level=DataLevel.L1, mode=shadow_mode, data_source=data_source,
        ledger=LiveShadowLedger(path=ledger_path), status_path=status_path,
    )
    typer.echo(f"state={status.state}  data_source={status.data_source}  "
               f"n_events={status.n_events}  n_proposals={status.n_proposals}")
    if status.message:
        typer.echo(status.message)


@live_shadow_app.command("status")
def live_shadow_status(
    status_path: str = typer.Option(
        "research_memory/live_shadow/session_status.json", help="Where session status is persisted",
    ),
) -> None:
    """Reads the on-disk session status `pae live-shadow start` wrote."""
    from prop_alpha.live_shadow.session import get_live_shadow_status

    status = get_live_shadow_status(status_path)
    typer.echo("LIVE SHADOW SESSION STATUS")
    typer.echo("")
    typer.echo(f"mode:          {status.mode}")
    typer.echo(f"state:         {status.state}")
    typer.echo(f"data_source:   {status.data_source}")
    typer.echo(f"provider:      {status.provider_name}")
    typer.echo(f"started_at:    {status.started_at}")
    typer.echo(f"last_event_at: {status.last_event_at}")
    typer.echo(f"n_events:      {status.n_events}")
    typer.echo(f"n_proposals:   {status.n_proposals}")
    if status.message:
        typer.echo(f"message:       {status.message}")


@live_shadow_app.command("stop")
def live_shadow_stop(
    status_path: str = typer.Option(
        "research_memory/live_shadow/session_status.json", help="Where session status is persisted",
    ),
) -> None:
    """Marks the on-disk session status STOPPED (see `live_shadow.session.
    stop_live_shadow_session`'s docstring for why this is a status-file
    update, not a real process signal, in this environment).
    """
    from prop_alpha.live_shadow.session import stop_live_shadow_session

    status = stop_live_shadow_session(status_path)
    typer.echo(f"state={status.state}  {status.message}")


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
        "diagnostics_run": wf is not None,
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


def _prepare_dataset(config: EngineConfig, n_days: int) -> dict:
    """Shared data -> features -> regime prep used by both `full-run` and
    `discover`, so the two commands can never silently diverge on how the
    IS/OOS boundary or regime fit are computed.
    """
    raw_path = Path(DEMO_RAW_PATH)
    df_raw = generate_synthetic_ohlcv(n_days=n_days, seed=config.seed)
    save_parquet(df_raw, raw_path)

    quality = validate_ohlcv(df_raw)
    if not quality.is_valid:
        typer.echo(f"BACKTEST STATUS = INVALID: {quality.issues}")
        raise typer.Exit(code=1)

    df_feat = build_full_feature_set(df_raw, config)

    unique_days = sorted(df_feat["timestamp"].dt.date.unique())
    oos_start_day = unique_days[int(len(unique_days) * 0.8)]
    in_sample_days = {d for d in unique_days if d < oos_start_day}

    # Regime Engine (spec §12/§13): rule-based classification is pure
    # per-bar arithmetic (no fitting), but the Gaussian Mixture classifier
    # is fit on in-sample days only and then applied to the full series —
    # fitting on OOS data too would leak OOS market structure into the
    # cluster definitions every OOS backtest gets evaluated against.
    df_feat = build_regime_features(df_feat, in_sample_days, config.regime)
    save_parquet(df_feat, DEMO_FEATURES_PATH)

    cost_model = CostModel(
        tick_size=config.market.tick_size,
        tick_value=config.market.tick_value,
        commission_per_round_turn=config.cost.commission_per_round_turn,
        slippage_ticks=config.cost.slippage_ticks,
        spread_ticks=config.cost.spread_ticks,
    )

    return {
        "raw_path": raw_path,
        "df_raw": df_raw,
        "df_feat": df_feat,
        "unique_days": unique_days,
        "oos_start_day": oos_start_day,
        "in_sample_days": in_sample_days,
        "cost_model": cost_model,
    }


def _run_full_research(config_path: str | None, n_days: int, out_dir: str, fast: bool = False) -> Path:
    _constitution_status = get_constitution_status()
    config = EngineConfig.from_yaml(config_path) if config_path else EngineConfig()
    prepared = _prepare_dataset(config, n_days)
    raw_path = prepared["raw_path"]
    df_raw = prepared["df_raw"]
    df_feat = prepared["df_feat"]
    unique_days = prepared["unique_days"]
    oos_start_day = prepared["oos_start_day"]
    cost_model = prepared["cost_model"]

    alpha_instances = [cls() for cls in ALPHA_STRATEGIES]
    baseline_instances = _instantiate_baselines(config.seed)

    results = []
    alpha_daily_pnl = {}
    baseline_daily_pnl_by_name = {}
    for strategy in alpha_instances:
        result, dpnl = _evaluate_strategy(strategy, df_feat, cost_model, config, oos_start_day, run_diagnostics=not fast)
        results.append(result)
        alpha_daily_pnl[result["alpha_id"]] = dpnl
    for strategy in baseline_instances:
        result, dpnl = _evaluate_strategy(strategy, df_feat, cost_model, config, oos_start_day, run_diagnostics=False)
        results.append(result)
        baseline_daily_pnl_by_name[result["alpha_name"]] = dpnl

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

    # Payout Optimizer (spec §38): applied to the #1-ranked alpha only — a
    # sizing/stop-trading policy comparison is a downstream-of-selection
    # question, not something to run for all 12 candidates on every research
    # run.
    payout_optimizer_results = None
    payout_optimizer_alpha_name = None
    conditional_ev_table = None
    meta_alpha_result = None
    paper_monitor_result = None
    decay_result = None
    drift_findings = None
    supervisor_verdict = None
    alpha_results = [r for r in results if r["family"] != "BASELINE"]
    if alpha_results:
        top_alpha_result = rank_alphas(alpha_results)[0]
        top_strategy = next(s for s in alpha_instances if s.meta.alpha_id == top_alpha_result["alpha_id"])
        top_signals = top_strategy.with_risk_levels(df_feat)
        top_trades = run_backtest(
            top_signals, cost_model=cost_model,
            max_trades_day=config.risk.max_trades_day, point_value=config.market.point_value,
        )
        top_trades_df = trades_to_frame(top_trades)
        payout_optimizer_results = compare_policies(
            top_trades_df, config.prop, point_value=config.market.point_value, seed=config.seed,
            policies=default_policies(config.risk.risk_per_trade),
        )
        payout_optimizer_alpha_name = top_strategy.meta.alpha_name

        # Conditional EV by Regime (spec §14): "when does the winner work,
        # not just does it work" — the whole point of building a regime
        # engine at all (spec §140/§141).
        conditional_ev_table = conditional_ev_by_regime(top_trades_df, df_feat)

        # ML Meta-Alpha (spec §44-47/§101): predict P(this trade wins) from
        # market state, with a Logistic Regression baseline the Random
        # Forest must actually beat OOS before it's worth using (spec §45).
        is_trades = top_trades_df[top_trades_df["entry_time"].dt.date < oos_start_day] if not top_trades_df.empty else top_trades_df
        oos_trades = top_trades_df[top_trades_df["entry_time"].dt.date >= oos_start_day] if not top_trades_df.empty else top_trades_df
        X_is, y_is_win, y_is_r = build_ml_feature_matrix(is_trades, df_feat)
        X_oos, y_oos_win, _ = build_ml_feature_matrix(oos_trades, df_feat)
        meta_alpha_result = evaluate_meta_alpha(X_is, y_is_win, y_is_r, X_oos, y_oos_win, config.ml, seed=config.seed)

        # Shadow Mode / Paper Trading (spec §97-101, §132): no live feed
        # exists in this environment, so the shadow log replays the same
        # OOS trades used above rather than fabricating a fake live stream
        # (spec §123) — see paper/shadow.py's docstring for the honest
        # limitation this implies.
        meta_model = meta_alpha_result.get("model") if meta_alpha_result else None
        shadow_log = build_shadow_log(oos_trades, X_oos, meta_model, top_alpha_result)
        paper_monitor_result = evaluate_paper_monitor(
            shadow_log, min_trades_for_calibration=config.paper.min_shadow_trades_for_calibration,
        )
        decay_result = classify_alpha_decay(
            shadow_log,
            is_ev_per_day=top_alpha_result.get("ev_per_day_dollars"),
            is_boot_ev_p5=top_alpha_result.get("boot_ev_p5"),
            is_boot_ev_p95=top_alpha_result.get("boot_ev_p95"),
            seed=config.seed,
            n_boot=config.paper.decay_bootstrap_n,
            min_days_for_ci=config.paper.decay_min_shadow_days_for_ci,
        )
        drift_findings = compute_feature_drift(
            X_is, X_oos,
            feature_columns=config.paper.drift_features,
            psi_threshold=config.paper.psi_drift_threshold,
        )

        # Multi-Agent Research Architecture (spec §58-60/§128/§129): the
        # Statistician and Risk Agent mechanically check the Research Gates
        # against evidence already computed above; the Critic actively
        # looks for reasons the result might be false; the Supervisor is
        # the only thing allowed to turn all of that into a verdict, and
        # every verdict is appended to the Audit Trail regardless of
        # outcome.
        statistician_gates = evaluate_statistician_gates(
            top_alpha_result, config.agents, paper_monitor_result, decay_result,
        )
        risk_gates = evaluate_risk_gates(top_alpha_result, payout_optimizer_results, config.prop)
        critic_findings = evaluate_critic_findings(
            top_alpha_result, pbo_result, conditional_ev_table,
            alpha_daily_pnl.get(top_alpha_result["alpha_id"]), baseline_daily_pnl_by_name,
            unique_days, config.agents,
            decay_result=decay_result, drift_findings=drift_findings,
        )
        supervisor_verdict = review(statistician_gates + risk_gates, critic_findings)

        audit_entry = AuditEntry(
            date=dt.date.today().isoformat(),
            experiment_id="PENDING",  # filled in once experiment_id is minted below
            alpha_id=top_alpha_result["alpha_id"],
            alpha_name=top_alpha_result["alpha_name"],
            hypothesis=top_alpha_result.get("mechanism", ""),
            dataset_hash=hash_file(raw_path),
            config_hash=hash_dict(config.model_dump()),
            result_summary=(
                f"n_trades={top_alpha_result['n_trades']}, "
                f"research_status={top_alpha_result['research_status']}, "
                f"p_breach={top_alpha_result['p_breach']}, p_payout={top_alpha_result['p_payout']}"
            ),
            decision=supervisor_verdict.verdict,
            reasons=supervisor_verdict.blocking_reasons,
            constitution_id=_constitution_status["id"] or "",
            constitution_version=_constitution_status["version"] or "",
            constitution_hash=_constitution_status["hash"] or "",
            git_commit=git_commit_hash(),
        )

    experiment_id = make_experiment_id()
    if supervisor_verdict is not None:
        audit_entry.experiment_id = experiment_id
        AuditTrail().append(audit_entry)
    meta = {
        "git_commit": git_commit_hash(),
        "config_hash": hash_dict(config.model_dump()),
        "dataset_hash": hash_file(raw_path),
        "dataset_source": df_raw.attrs.get("source", "unknown"),
        "seed": config.seed,
    }
    diagnostics = {
        "pbo": pbo_result,
        "dsr_by_alpha": dsr_by_alpha,
        "payout_optimizer": payout_optimizer_results,
        "payout_optimizer_alpha_name": payout_optimizer_alpha_name,
        "conditional_ev_table": conditional_ev_table,
        "conditional_ev_alpha_name": payout_optimizer_alpha_name,
        "meta_alpha_result": meta_alpha_result,
        "meta_alpha_alpha_name": payout_optimizer_alpha_name,
        "paper_monitor_result": paper_monitor_result,
        "decay_result": decay_result,
        "drift_findings": drift_findings,
        "paper_trading_alpha_name": payout_optimizer_alpha_name,
        "supervisor_verdict": supervisor_verdict,
        "supervisor_alpha_name": payout_optimizer_alpha_name,
    }
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

    Constitution-gated (hardening pass): refuses to run if the Research
    Constitution fails verification.
    """
    _require_valid_constitution("research full-run")
    report_path = _run_full_research(config, n_days, out_dir, fast=fast)
    typer.echo(f"Report written to {report_path}")


def _run_discover(config_path: str | None, n_days: int, out_dir: str, top_n: int, ledger_path: str) -> Path:
    config = EngineConfig.from_yaml(config_path) if config_path else EngineConfig()
    prepared = _prepare_dataset(config, n_days)

    ledger = HypothesisLedger(ledger_path)
    discovery_result = run_discovery(
        prepared["df_feat"], prepared["cost_model"], config, prepared["oos_start_day"],
        ledger=ledger, dataset_note=f"{n_days}-day synthetic demo dataset (seed={config.seed})",
    )

    experiment_id = make_experiment_id(prefix="DISC")
    meta = {
        "git_commit": git_commit_hash(),
        "config_hash": hash_dict(config.model_dump()),
        "dataset_hash": hash_file(prepared["raw_path"]),
        "dataset_source": prepared["df_raw"].attrs.get("source", "unknown"),
        "seed": config.seed,
    }
    return generate_discovery_report(discovery_result, experiment_id, meta, top_n=top_n, out_dir=out_dir)


@research_app.command("discover")
def research_discover(
    config: str = typer.Option(None, help="Path to a YAML EngineConfig; defaults built in if omitted"),
    n_days: int = 250,
    out_dir: str = "reports",
    top_n: int = 15,
    ledger_path: str = typer.Option(
        "research_memory/hypotheses/ledger.jsonl",
        help="Hypothesis Ledger file (spec §20) — every candidate, survivor or not, is appended here.",
    ),
) -> None:
    """Alpha Discovery Engine (spec §18/§19 Level 2, §20, §48): generate
    candidate setups via combinatorial search over a condition library,
    quick-screen each on IS/OOS EV, log every one to the Hypothesis Ledger,
    run a symbolic-regression scan for simple predictive expressions, and
    report the survivors. A discovered candidate reaches at most
    HYPOTHESIS/BACKTESTED here — promote a promising one to
    `cli.ALPHA_STRATEGIES` and run `pae research full-run` for the full
    Phase 4 statistical validation gates before it means anything.

    Constitution-gated (hardening pass): refuses to run if the Research
    Constitution fails verification.
    """
    _require_valid_constitution("research discover")
    report_path = _run_discover(config, n_days, out_dir, top_n, ledger_path)
    typer.echo(f"Discovery report written to {report_path}")


@research_app.command("gex-templates")
def research_gex_templates(
    enriched_frame_path: str = typer.Option(
        ..., help="Parquet file: sync.cross_market.synchronize_frame output already run through "
                   "research_templates.gex_market_frame.enrich_synced_frame_with_gex_features",
    ),
    oos_start_day: str = typer.Option(..., help="OOS split date, YYYY-MM-DD"),
    config: str = typer.Option(None, help="Path to a YAML EngineConfig; defaults built in if omitted"),
    max_candidates: int = typer.Option(150, help="Max cross-market candidates to generate (extension §111-114)"),
    ledger_path: str = typer.Option(
        "research_memory/hypotheses/ledger.jsonl",
        help="Hypothesis Ledger file (spec §20) — every candidate, survivor or not, is appended here.",
    ),
) -> None:
    """Data Feed extension (§111-114, Phase P): auto-generate GEX/futures
    cross-market templates, quick-screen each, log every one to the
    Hypothesis Ledger, and report the survivors.

    Requires an already-synced, already-enriched futures+options frame as
    input — there is currently no built pipeline in this repo that
    produces one end-to-end on its own: GEXBOT has no historical endpoint
    (extension §62's limitation, Phase H) and no options-side recorder
    exists yet (Phase F's own noted gap), so today that frame has to come
    from combining `pae data ingest` output with your own accumulated
    options snapshot history via `sync.cross_market.synchronize_frame` +
    `research_templates.gex_market_frame.enrich_synced_frame_with_gex_features`.
    Not exercised by the test suite for that reason; the condition
    library, template generator, and discovery orchestration it calls
    into are (`tests/test_research_templates_*.py`).

    Constitution-gated (hardening pass): refuses to run if the Research
    Constitution fails verification.
    """
    _require_valid_constitution("research gex-templates")

    import pandas as pd

    from prop_alpha.discovery.hypothesis import HypothesisLedger
    from prop_alpha.research_templates.discovery import run_gex_futures_discovery

    cfg = EngineConfig.from_yaml(config) if config else EngineConfig()
    cfg.discovery.max_candidates = max_candidates
    df_enriched = pd.read_parquet(enriched_frame_path)
    cost_model = CostModel(
        tick_size=cfg.market.tick_size, tick_value=cfg.market.tick_value,
        commission_per_round_turn=cfg.cost.commission_per_round_turn,
        slippage_ticks=cfg.cost.slippage_ticks, spread_ticks=cfg.cost.spread_ticks,
    )
    ledger = HypothesisLedger(ledger_path)

    result = run_gex_futures_discovery(
        df_enriched, cost_model, cfg, dt.date.fromisoformat(oos_start_day), ledger=ledger,
        dataset_note=f"enriched frame at {enriched_frame_path}",
    )

    typer.echo(
        f"GEX/futures templates: {result['n_candidates']} candidates, "
        f"{result['n_passed_screen']} passed screen."
    )
    for r in result["survivors"][:10]:
        typer.echo(f"  {r['alpha_id']}  {r['alpha_name']}  OOS EV/day={r['oos_ev_per_day']:.2f}  n_trades={r['n_trades']}")


if __name__ == "__main__":
    app()
