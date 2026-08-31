"""End-to-end integration tests for the Data Feed + Options Intelligence
Layer extension (extension spec §134-140): wires the mock providers
(`providers.mocks`) through the real cross-phase pipeline — ingest (Phase
G) -> sync (Phase J) -> GEX enrichment (Phase P) -> market state (Phase L)
-> live shadow proposals (Phase O) -> deterministic replay (Phase N) -> a
GEX/futures discovery run (Phase P) — with no real network access, API
keys, or vendor SDKs, so this suite runs anywhere CI does.

This is deliberately not a re-test of any single phase's own unit
behavior (each already has its own focused test file) — it exists to
catch the one thing per-phase unit tests can't: that the pieces actually
connect (matching column names, matching timestamp conventions, no
silently-dropped data) end to end.
"""
from __future__ import annotations

import datetime as dt

import pytest

from prop_alpha.data.ingest import ingest_historical
from prop_alpha.data.lake import DataLakePaths
from prop_alpha.data.lake_query import query_tier
from prop_alpha.data.live.event_router import EventRouter
from prop_alpha.data.live.recorder import LiveRecorder
from prop_alpha.discovery.hypothesis import HypothesisLedger
from prop_alpha.features.pipeline import build_full_feature_set
from prop_alpha.config import EngineConfig
from prop_alpha.backtest.costs import CostModel
from prop_alpha.live_shadow.engine import run_live_shadow_session
from prop_alpha.live_shadow.ledger import LiveShadowLedger
from prop_alpha.live_shadow.proposal import make_proposal
from prop_alpha.market_state.vector import MarketState, build_market_state
from prop_alpha.providers.base import DataLevel
from prop_alpha.providers.mocks import MockFuturesDataProvider, MockOptionsDataProvider
from prop_alpha.regimes.pipeline import build_regime_features
from prop_alpha.replay.engine import replay_envelopes
from prop_alpha.replay.reader import read_jsonl_envelopes
from prop_alpha.research_templates.conditions import GEX_CONDITION_LIBRARY
from prop_alpha.research_templates.discovery import run_gex_futures_discovery
from prop_alpha.research_templates.gex_market_frame import enrich_synced_frame_with_gex_features
from prop_alpha.sync.cross_market import synchronize_frame

pytestmark = pytest.mark.integration


def _ingest_and_sync(tmp_path, n_snapshots=40, snapshot_interval_seconds=180.0):
    lake = DataLakePaths(root=tmp_path / "lake")
    futures_provider = MockFuturesDataProvider(seed=11)
    options_provider = MockOptionsDataProvider(seed=11)

    ingest_result = ingest_historical(
        provider=futures_provider, instrument="NQ", level=DataLevel.L1, schema="ohlcv-1m",
        start=dt.date(2024, 1, 2), end=dt.date(2024, 1, 4), lake=lake,
    )
    assert ingest_result.n_written >= 1
    assert ingest_result.n_failed == 0

    df_futures = query_tier(lake, "raw", provider="mock", instrument="NQ", schema="ohlcv-1m")
    assert not df_futures.empty

    start_ts = df_futures["timestamp"].min().to_pydatetime()
    options_snapshots = options_provider.generate_snapshot_sequence(
        "NQ", start_ts, n=n_snapshots, interval_seconds=snapshot_interval_seconds,
    )
    synced = synchronize_frame(df_futures, options_snapshots)
    return lake, futures_provider, options_provider, synced


def test_ingest_produces_a_queryable_lake_partition(tmp_path):
    lake, _, _, synced = _ingest_and_sync(tmp_path)
    assert "options_gex" in synced.columns
    assert "sync_time_difference_ms" in synced.columns
    # not every bar necessarily falls within sync tolerance of a snapshot,
    # but with a 180s snapshot cadence over 1-minute bars most should.
    assert synced["options_gex"].notna().any()


def test_enrichment_adds_gex_dex_state_on_top_of_sync(tmp_path):
    _, _, _, synced = _ingest_and_sync(tmp_path)
    enriched = enrich_synced_frame_with_gex_features(synced)
    assert "gex_regime" in enriched.columns
    assert "dex_sign" in enriched.columns
    assert set(enriched["gex_regime"].unique()) <= {
        "STRONG_POSITIVE_GAMMA", "POSITIVE_GAMMA", "NEUTRAL", "NEGATIVE_GAMMA",
        "STRONG_NEGATIVE_GAMMA", "UNKNOWN",
    }


def test_market_state_built_from_an_enriched_synced_row(tmp_path):
    _, _, _, synced = _ingest_and_sync(tmp_path)
    enriched = enrich_synced_frame_with_gex_features(synced)
    row = enriched.iloc[len(enriched) // 2].to_dict()

    state = build_market_state(row, timestamp=row["timestamp"])
    assert isinstance(state, MarketState)
    assert state.price_state.get("close") == row["close"]
    assert state.completeness > 0


def test_live_shadow_session_logs_proposals_from_a_market_state_stream(tmp_path):
    _, _, _, synced = _ingest_and_sync(tmp_path)
    enriched = enrich_synced_frame_with_gex_features(synced)

    states = [
        build_market_state(row.to_dict(), timestamp=row["timestamp"])
        for _, row in enriched.head(20).iterrows()
    ]

    def proposal_generator(state: MarketState):
        close = state.price_state.get("close")
        if close is None:
            return None
        return make_proposal(
            timestamp=state.timestamp, instrument="NQ", direction="LONG",
            entry_price=close, rationale="integration test: always propose when close is known",
        )

    ledger = LiveShadowLedger(path=tmp_path / "live_shadow.jsonl")
    result = run_live_shadow_session(states, proposal_generator=proposal_generator, ledger=ledger)

    assert result.n_market_states == 20
    assert result.n_proposals == len(ledger.read_proposals())
    assert result.n_proposals > 0


def test_recorded_live_session_replays_deterministically(tmp_path):
    futures_provider = MockFuturesDataProvider(seed=5)
    session_path = tmp_path / "session.jsonl"
    recorder = LiveRecorder(path=str(session_path))

    from prop_alpha.data.live.recorder import build_envelope

    def on_message(payload: dict):
        recorder.record(build_envelope(
            provider=futures_provider.name, instrument="NQ", schema="ohlcv-1m",
            payload=payload, timestamp_exchange=dt.datetime.fromisoformat(payload["timestamp"]),
        ))

    handle = futures_provider.subscribe_live("NQ", level=None, on_message=on_message)
    handle.close()
    assert recorder.message_count == 5

    envelopes = read_jsonl_envelopes(str(session_path))
    assert len(envelopes) == 5

    router = EventRouter()
    dispatched = []
    router.subscribe(dispatched.append, provider="mock")

    result = replay_envelopes(envelopes, on_envelope=router.route)
    assert result.n_events == 5
    assert len(dispatched) == 5
    # deterministic: dispatched order matches ascending timestamp_normalized
    assert [e.timestamp_normalized for e in dispatched] == sorted(e.timestamp_normalized for e in dispatched)


def test_gex_futures_discovery_runs_on_mock_provider_sourced_data(tmp_path):
    lake, futures_provider, options_provider, _ = _ingest_and_sync(tmp_path, n_snapshots=200, snapshot_interval_seconds=60.0)

    df_futures = query_tier(lake, "raw", provider="mock", instrument="NQ", schema="ohlcv-1m")
    # Round-trip back to the wall-clock tz the core feature pipeline expects
    # (MockFuturesDataProvider only converted this data's original NY-session
    # timestamps to UTC on the way out -- this undoes that, it doesn't
    # invent a new time reference).
    df_futures = df_futures.copy()
    df_futures["timestamp"] = df_futures["timestamp"].dt.tz_convert("America/New_York")

    config = EngineConfig()
    feats = build_full_feature_set(df_futures, config)
    days = sorted(feats["timestamp"].dt.tz_convert("America/New_York").dt.date.unique())
    oos_start_day = days[-1]
    in_sample_days = {d for d in days if d < oos_start_day}
    feats = build_regime_features(feats, in_sample_days, config.regime)

    start_ts = feats["timestamp"].min().to_pydatetime()
    options_snapshots = options_provider.generate_snapshot_sequence(
        "NQ", start_ts, n=400, interval_seconds=60.0,
    )
    synced = synchronize_frame(feats, options_snapshots)
    enriched = enrich_synced_frame_with_gex_features(synced)

    cost_model = CostModel(
        tick_size=config.market.tick_size, tick_value=config.market.tick_value,
        commission_per_round_turn=config.cost.commission_per_round_turn,
        slippage_ticks=config.cost.slippage_ticks, spread_ticks=config.cost.spread_ticks,
    )
    config.discovery.max_candidates = 4
    ledger = HypothesisLedger(path=tmp_path / "hypotheses.jsonl")

    from prop_alpha.discovery.conditions import CONDITION_LIBRARY

    result = run_gex_futures_discovery(
        enriched, cost_model, config, oos_start_day, ledger=ledger,
        futures_library=CONDITION_LIBRARY[:2], gex_library=GEX_CONDITION_LIBRARY[:2],
    )

    assert result["n_candidates"] == 4
    assert len(ledger.read_all()) == 4
