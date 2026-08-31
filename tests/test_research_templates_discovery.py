import numpy as np
import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.config import EngineConfig
from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.discovery.hypothesis import HypothesisLedger
from prop_alpha.discovery.setup_generator import GeneratedStrategy
from prop_alpha.features.pipeline import build_full_feature_set
from prop_alpha.regimes.pipeline import build_regime_features
from prop_alpha.research_templates.conditions import GEX_CONDITION_LIBRARY
from prop_alpha.research_templates.discovery import hypothesis_from_gex_template, run_gex_futures_discovery
from prop_alpha.research_templates.gex_market_frame import enrich_synced_frame_with_gex_features


def test_hypothesis_from_gex_template_fields():
    condition = GEX_CONDITION_LIBRARY[0]
    from prop_alpha.discovery.conditions import CONDITION_LIBRARY
    candidate = GeneratedStrategy("GEXFUT_0001", [CONDITION_LIBRARY[0], condition], direction=1)
    result = {"n_trades": 10, "is_ev_per_day": 5.0, "oos_ev_per_day": 3.0, "passed_screen": True}

    hyp = hypothesis_from_gex_template(candidate, result, market="NQ", dataset_note="test dataset")

    assert hyp.hypothesis_id == "GEXFUT_0001"
    assert "cross-market" in hyp.market
    assert hyp.status == "BACKTESTED"
    assert condition.name in hyp.features
    assert "GEX_STATE_STALE" in hyp.expected_failure_modes


def test_hypothesis_from_gex_template_zero_trades_is_retired():
    from prop_alpha.discovery.conditions import CONDITION_LIBRARY
    candidate = GeneratedStrategy("GEXFUT_0002", [CONDITION_LIBRARY[0], GEX_CONDITION_LIBRARY[0]], direction=1)
    result = {"n_trades": 0, "is_ev_per_day": float("nan"), "oos_ev_per_day": float("nan"), "passed_screen": False}

    hyp = hypothesis_from_gex_template(candidate, result, market="NQ", dataset_note="test dataset")
    assert hyp.status == "RETIRED"
    assert "never fired" in hyp.result


def _prepared_enriched(n_days=60, seed=61):
    df = generate_synthetic_ohlcv(n_days=n_days, seed=seed)
    config = EngineConfig()
    feats = build_full_feature_set(df, config)
    days = sorted(feats["timestamp"].dt.tz_convert("America/New_York").dt.date.unique())
    oos_start_day = days[int(len(days) * 0.8)]
    in_sample_days = {d for d in days if d < oos_start_day}
    feats = build_regime_features(feats, in_sample_days, config.regime)
    cost_model = CostModel(
        tick_size=config.market.tick_size, tick_value=config.market.tick_value,
        commission_per_round_turn=config.cost.commission_per_round_turn,
        slippage_ticks=config.cost.slippage_ticks, spread_ticks=config.cost.spread_ticks,
    )

    # Synthetic options columns standing in for a real sync.cross_market.synchronize_frame
    # output (no real GEXBOT connectivity in tests) -- deterministic, seeded, and never
    # presented as real market data (see this module's docstring discipline elsewhere).
    rng = np.random.default_rng(seed)
    n = len(feats)
    feats["options_gex"] = rng.normal(0, 1, n)
    feats["options_dex"] = rng.normal(0, 1, n)
    feats["options_gamma_flip"] = feats["close"] + rng.normal(0, 5, n)
    feats["options_major_positive_gamma"] = feats["close"] + 20.0
    feats["options_major_negative_gamma"] = feats["close"] - 20.0

    enriched = enrich_synced_frame_with_gex_features(feats)
    return enriched, cost_model, config, oos_start_day


def test_run_gex_futures_discovery_returns_expected_keys(tmp_path):
    enriched, cost_model, config, oos_start_day = _prepared_enriched()
    config.discovery.max_candidates = 6
    ledger = HypothesisLedger(path=tmp_path / "ledger.jsonl")
    from prop_alpha.discovery.conditions import CONDITION_LIBRARY

    result = run_gex_futures_discovery(
        enriched, cost_model, config, oos_start_day, ledger=ledger,
        futures_library=CONDITION_LIBRARY[:2], gex_library=GEX_CONDITION_LIBRARY[:2],
    )
    for key in ("n_candidates", "n_passed_screen", "survivors", "all_results"):
        assert key in result
    assert result["n_candidates"] == 6


def test_run_gex_futures_discovery_logs_every_candidate_to_ledger(tmp_path):
    enriched, cost_model, config, oos_start_day = _prepared_enriched()
    config.discovery.max_candidates = 4
    ledger = HypothesisLedger(path=tmp_path / "ledger.jsonl")
    from prop_alpha.discovery.conditions import CONDITION_LIBRARY

    result = run_gex_futures_discovery(
        enriched, cost_model, config, oos_start_day, ledger=ledger,
        futures_library=CONDITION_LIBRARY[:2], gex_library=GEX_CONDITION_LIBRARY[:2],
    )
    logged = ledger.read_all()
    assert len(logged) == result["n_candidates"] == 4


def test_run_gex_futures_discovery_survivors_sorted_by_oos_ev_descending(tmp_path):
    enriched, cost_model, config, oos_start_day = _prepared_enriched()
    config.discovery.max_candidates = 12
    ledger = HypothesisLedger(path=tmp_path / "ledger.jsonl")
    from prop_alpha.discovery.conditions import CONDITION_LIBRARY

    result = run_gex_futures_discovery(
        enriched, cost_model, config, oos_start_day, ledger=ledger,
        futures_library=CONDITION_LIBRARY[:3], gex_library=GEX_CONDITION_LIBRARY[:3],
    )
    oos_evs = [r["oos_ev_per_day"] for r in result["survivors"]]
    assert oos_evs == sorted(oos_evs, reverse=True)
