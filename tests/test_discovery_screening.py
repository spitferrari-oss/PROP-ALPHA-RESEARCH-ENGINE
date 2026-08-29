from prop_alpha.backtest.costs import CostModel
from prop_alpha.config import EngineConfig
from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.discovery.conditions import CONDITION_LIBRARY
from prop_alpha.discovery.setup_generator import generate_candidate_setups
from prop_alpha.discovery.screening import quick_evaluate
from prop_alpha.features.pipeline import build_full_feature_set
from prop_alpha.regimes.pipeline import build_regime_features


def _prepared(n_days=60, seed=61):
    df = generate_synthetic_ohlcv(n_days=n_days, seed=seed)
    config = EngineConfig()
    feats = build_full_feature_set(df, config)
    days = sorted(feats["timestamp"].dt.tz_convert("America/New_York").dt.date.unique())
    oos_start_day = days[int(len(days) * 0.8)]
    in_sample_days = {d for d in days if d < oos_start_day}
    feats = build_regime_features(feats, in_sample_days, config.regime)
    cost_model = CostModel(tick_size=config.market.tick_size, tick_value=config.market.tick_value,
                            commission_per_round_turn=config.cost.commission_per_round_turn,
                            slippage_ticks=config.cost.slippage_ticks, spread_ticks=config.cost.spread_ticks)
    return feats, cost_model, config, oos_start_day


def test_quick_evaluate_returns_expected_keys():
    feats, cost_model, config, oos_start_day = _prepared()
    candidate = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=1, max_candidates=1, seed=1)[0]
    result = quick_evaluate(candidate, feats, cost_model, config, oos_start_day)
    for key in ["alpha_id", "alpha_name", "n_trades", "win_rate", "is_ev_per_day", "oos_ev_per_day", "passed_screen"]:
        assert key in result


def test_passed_screen_requires_min_trades():
    feats, cost_model, config, oos_start_day = _prepared()
    config.discovery.min_trades_to_screen = 100_000  # impossible to hit
    candidate = generate_candidate_setups(CONDITION_LIBRARY, max_combo_size=1, max_candidates=1, seed=1)[0]
    result = quick_evaluate(candidate, feats, cost_model, config, oos_start_day)
    assert result["passed_screen"] is False


def test_zero_trade_candidate_does_not_crash():
    feats, cost_model, config, oos_start_day = _prepared()
    # Two mutually exclusive regime conditions ANDed together should never fire.
    from prop_alpha.discovery.setup_generator import GeneratedStrategy
    trend_up = next(c for c in CONDITION_LIBRARY if c.name == "regime_trend_up")
    trend_down = next(c for c in CONDITION_LIBRARY if c.name == "regime_trend_down")
    impossible = GeneratedStrategy("IMPOSSIBLE", [trend_up, trend_down], direction=1)
    result = quick_evaluate(impossible, feats, cost_model, config, oos_start_day)
    assert result["n_trades"] == 0
    assert result["passed_screen"] is False
