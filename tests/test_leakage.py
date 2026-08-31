import pandas as pd
import pytest

from prop_alpha.statistics.leakage import (
    check_developing_profile_not_static_within_session,
    check_no_duplicate_timestamps,
    check_outcome_horizon_overlap,
    check_timestamps_monotonic,
    check_train_test_index_overlap,
    run_leakage_checks,
)


def _sorted_df():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31", "2024-01-02 09:32"], utc=True),
        "close": [100.0, 101.0, 102.0],
    })


def test_timestamps_monotonic_passes_for_sorted_frame():
    finding = check_timestamps_monotonic(_sorted_df())
    assert finding.passed is True
    assert finding.severity == "HARD"


def test_timestamps_monotonic_fails_for_shuffled_frame():
    df = _sorted_df().iloc[[2, 0, 1]].reset_index(drop=True)
    finding = check_timestamps_monotonic(df)
    assert finding.passed is False


def test_timestamps_monotonic_empty_frame_passes():
    finding = check_timestamps_monotonic(pd.DataFrame({"timestamp": []}))
    assert finding.passed is True


def test_no_duplicate_timestamps_passes_when_unique():
    finding = check_no_duplicate_timestamps(_sorted_df())
    assert finding.passed is True


def test_no_duplicate_timestamps_fails_when_duplicated():
    df = pd.concat([_sorted_df(), _sorted_df().iloc[[0]]], ignore_index=True)
    finding = check_no_duplicate_timestamps(df)
    assert finding.passed is False
    assert "1 duplicate" in finding.detail


def test_train_test_index_overlap_passes_when_disjoint():
    finding = check_train_test_index_overlap(range(0, 10), range(10, 20))
    assert finding.passed is True


def test_train_test_index_overlap_fails_when_overlapping():
    finding = check_train_test_index_overlap(range(0, 10), range(5, 15))
    assert finding.passed is False
    assert finding.severity == "HARD"


def test_outcome_horizon_overlap_passes_when_no_crossing_trade():
    trades = pd.DataFrame({
        "entry_time": pd.to_datetime(["2024-01-01 10:00", "2024-01-05 10:00"], utc=True),
        "exit_time": pd.to_datetime(["2024-01-01 11:00", "2024-01-05 11:00"], utc=True),
    })
    finding = check_outcome_horizon_overlap(trades, oos_start_day=pd.Timestamp("2024-01-03").date())
    assert finding.passed is True
    assert finding.severity == "WARNING"


def test_outcome_horizon_overlap_flags_crossing_trade():
    trades = pd.DataFrame({
        "entry_time": pd.to_datetime(["2024-01-02 23:00"], utc=True),
        "exit_time": pd.to_datetime(["2024-01-03 01:00"], utc=True),
    })
    finding = check_outcome_horizon_overlap(trades, oos_start_day=pd.Timestamp("2024-01-03").date())
    assert finding.passed is False


def test_outcome_horizon_overlap_empty_trades_passes():
    finding = check_outcome_horizon_overlap(pd.DataFrame(), oos_start_day=pd.Timestamp("2024-01-03").date())
    assert finding.passed is True


def test_developing_profile_exempt_prefix_always_passes():
    df = pd.DataFrame({"prior_day_high": [1.0, 1.0, 1.0], "session_id": ["A", "A", "A"]})
    finding = check_developing_profile_not_static_within_session(df, "prior_day_high", "session_id")
    assert finding.passed is True


def test_developing_profile_flags_static_within_session():
    df = pd.DataFrame({
        "vp_poc": [100.0, 100.0, 100.0, 200.0, 200.0],
        "session_id": ["A", "A", "A", "B", "B"],
    })
    finding = check_developing_profile_not_static_within_session(df, "vp_poc", "session_id")
    assert finding.passed is False
    assert "2/2" in finding.detail


def test_developing_profile_passes_when_value_varies():
    df = pd.DataFrame({
        "vp_poc": [100.0, 101.0, 102.0, 200.0, 205.0],
        "session_id": ["A", "A", "A", "B", "B"],
    })
    finding = check_developing_profile_not_static_within_session(df, "vp_poc", "session_id")
    assert finding.passed is True


def test_run_leakage_checks_runs_only_supplied_checks():
    df = _sorted_df()
    report = run_leakage_checks(df)
    check_names = {f.check for f in report.findings}
    assert check_names == {"timestamps_monotonic", "no_duplicate_timestamps"}


def test_run_leakage_checks_has_hard_leakage_true_on_shuffled_frame():
    df = _sorted_df().iloc[[2, 0, 1]].reset_index(drop=True)
    report = run_leakage_checks(df)
    assert report.has_hard_leakage is True
    assert len(report.failed_findings()) >= 1


def test_run_leakage_checks_has_hard_leakage_false_for_clean_data():
    report = run_leakage_checks(_sorted_df())
    assert report.has_hard_leakage is False


def test_run_leakage_checks_includes_train_test_overlap_when_supplied():
    report = run_leakage_checks(_sorted_df(), train_index=[0, 1], test_index=[1, 2])
    assert report.has_hard_leakage is True
    names = {f.check for f in report.failed_findings()}
    assert "train_test_index_overlap" in names
