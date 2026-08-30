import pandas as pd

from prop_alpha.paper.decay import classify_alpha_decay


def _shadow_log_from_daily_pnl(daily_values, start="2024-05-01"):
    n = len(daily_values)
    times = pd.date_range(start, periods=n, freq="1D", tz="America/New_York")
    return pd.DataFrame({"entry_time": times, "exit_time": times, "pnl": daily_values})


def test_no_shadow_trades_returns_green():
    result = classify_alpha_decay(
        pd.DataFrame(columns=["exit_time", "pnl"]),
        is_ev_per_day=100.0, is_boot_ev_p5=50.0, is_boot_ev_p95=150.0,
    )
    assert result["level"] == "GREEN"
    assert result["n_shadow_days"] == 0
    assert result["shadow_boot_ci"] is None


def test_persistently_negative_shadow_pnl_is_red():
    log = _shadow_log_from_daily_pnl([-100.0] * 10)
    result = classify_alpha_decay(
        log, is_ev_per_day=100.0, is_boot_ev_p5=50.0, is_boot_ev_p95=150.0, seed=1, min_days_for_ci=5,
    )
    assert result["level"] == "RED"


def test_ci_overlapping_zero_is_orange():
    # Alternating +/-200: mean 0, so a block bootstrap's 90% CI for EV/day
    # is expected to straddle zero deterministically (not via a random draw).
    log = _shadow_log_from_daily_pnl([200.0, -200.0] * 5)
    result = classify_alpha_decay(
        log, is_ev_per_day=100.0, is_boot_ev_p5=50.0, is_boot_ev_p95=150.0, seed=1, min_days_for_ci=5,
    )
    assert result["level"] == "ORANGE"


def test_strong_positive_shadow_matches_is_range_is_green():
    log = _shadow_log_from_daily_pnl([100.0] * 10)
    result = classify_alpha_decay(
        log, is_ev_per_day=100.0, is_boot_ev_p5=50.0, is_boot_ev_p95=150.0, seed=1, min_days_for_ci=5,
    )
    assert result["level"] == "GREEN"


def test_degraded_ev_below_one_sigma_is_yellow():
    # IS 90% CI [80, 120] -> sigma ~= (120-80)/3.29 ~= 12.2; shadow constant
    # at 70 is a positive, non-overlapping-zero CI but > 1 sigma below IS EV.
    log = _shadow_log_from_daily_pnl([70.0] * 10)
    result = classify_alpha_decay(
        log, is_ev_per_day=100.0, is_boot_ev_p5=80.0, is_boot_ev_p95=120.0, seed=1, min_days_for_ci=5,
    )
    assert result["level"] == "YELLOW"


def test_below_min_days_for_ci_skips_ci_based_levels():
    log = _shadow_log_from_daily_pnl([-100.0, -100.0])
    result = classify_alpha_decay(
        log, is_ev_per_day=100.0, is_boot_ev_p5=80.0, is_boot_ev_p95=120.0, seed=1, min_days_for_ci=5,
    )
    assert result["shadow_boot_ci"] is None
    assert result["level"] in ("YELLOW", "GREEN")
