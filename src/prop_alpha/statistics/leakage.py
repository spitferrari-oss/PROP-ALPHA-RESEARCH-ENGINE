"""Data leakage engine (hardening pass Step 49).

**Scope, stated honestly**: this is a *structural* leakage checker —
timestamp ordering, index overlap between splits, trade-horizon overlap
across an OOS boundary, and a heuristic "developing feature is
suspiciously static within a session" check. It is not a general
detector of arbitrary look-ahead bugs buried inside a feature's own
formula (verifying that, say, `features/price_volume.py`'s VWAP
calculation never peeks forward requires reading that code, not running
a generic checker against its output) — claiming otherwise would itself
violate the Constitution's `NO_FABRICATED_DATA`/honesty principles. What
this module *does* catch are the leakage vectors that show up in the
data's own shape regardless of which feature produced it: a shuffled
frame, overlapping train/test indices, a trade whose outcome horizon
crosses the OOS split, and a "developing" profile column that never
actually develops (a hallmark of accidentally using a whole day's data
on every bar of that day instead of only data up to each bar).

A `HARD` finding means the experiment this report is attached to must be
invalidated — never silently reported alongside a passing result. A
`WARNING` finding is worth a human's attention but is not automatically
disqualifying (e.g. a trade legitimately held across an OOS boundary is
not inherently wrong, just worth knowing about).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

_DEVELOPING_EXEMPT_PREFIXES = ("prior_day", "vp_prior")


@dataclass(frozen=True)
class LeakageFinding:
    check: str
    severity: str  # "HARD" | "WARNING"
    passed: bool
    detail: str


@dataclass(frozen=True)
class LeakageReport:
    findings: tuple[LeakageFinding, ...] = field(default_factory=tuple)

    @property
    def has_hard_leakage(self) -> bool:
        return any(f.severity == "HARD" and not f.passed for f in self.findings)

    def failed_findings(self) -> list[LeakageFinding]:
        return [f for f in self.findings if not f.passed]


def check_timestamps_monotonic(df: pd.DataFrame, timestamp_column: str = "timestamp") -> LeakageFinding:
    """A reordered/shuffled frame is directly exploitable by any
    rolling-window feature — it would compute a window using rows that
    are chronologically in the future relative to the row it's labeled
    on.
    """
    if timestamp_column not in df.columns or df.empty:
        return LeakageFinding("timestamps_monotonic", "HARD", True, "empty frame or column absent — nothing to check")
    is_sorted = df[timestamp_column].is_monotonic_increasing
    return LeakageFinding(
        "timestamps_monotonic", "HARD", is_sorted,
        "timestamps are strictly non-decreasing" if is_sorted else "timestamps are NOT sorted ascending",
    )


def check_no_duplicate_timestamps(df: pd.DataFrame, timestamp_column: str = "timestamp") -> LeakageFinding:
    """A duplicate timestamp can let a downstream join/merge_asof pick
    the wrong row silently — a distinct risk from `data.quality_engine`'s
    duplicate-timestamp check (which scores data quality), this one asks
    specifically whether a duplicate could let a model see the same
    outcome twice under two different feature rows.
    """
    if timestamp_column not in df.columns or df.empty:
        return LeakageFinding("no_duplicate_timestamps", "HARD", True, "empty frame or column absent")
    n_dupes = int(df[timestamp_column].duplicated().sum())
    return LeakageFinding(
        "no_duplicate_timestamps", "HARD", n_dupes == 0,
        "no duplicate timestamps" if n_dupes == 0 else f"{n_dupes} duplicate timestamp(s) found",
    )


def check_train_test_index_overlap(train_index, test_index) -> LeakageFinding:
    overlap = set(train_index) & set(test_index)
    return LeakageFinding(
        "train_test_index_overlap", "HARD", len(overlap) == 0,
        "no overlap" if not overlap else f"{len(overlap)} overlapping index value(s) between train and test",
    )


def check_outcome_horizon_overlap(
    trades_df: pd.DataFrame, oos_start_day, entry_column: str = "entry_time", exit_column: str = "exit_time",
) -> LeakageFinding:
    """A trade whose entry is in-sample but whose exit lands on/after the
    OOS split date has an outcome that spans the boundary — flagged as a
    `WARNING`, not `HARD`: holding a position across an arbitrary
    calendar split is not inherently wrong, it just means whichever
    slice a caller groups this trade into partially "sees" the other
    slice's price action, which is worth knowing when interpreting IS
    vs. OOS metrics separately.
    """
    if trades_df.empty or entry_column not in trades_df.columns or exit_column not in trades_df.columns:
        return LeakageFinding("outcome_horizon_overlap", "WARNING", True, "no trades to check")
    entry_day = trades_df[entry_column].dt.date
    exit_day = trades_df[exit_column].dt.date
    crossing = int(((entry_day < oos_start_day) & (exit_day >= oos_start_day)).sum())
    return LeakageFinding(
        "outcome_horizon_overlap", "WARNING", crossing == 0,
        "no trade crosses the OOS boundary" if crossing == 0
        else f"{crossing} trade(s) entered IS but exited on/after the OOS split date",
    )


def check_developing_profile_not_static_within_session(
    df: pd.DataFrame, column: str, session_id_column: str,
) -> LeakageFinding:
    """A column meant to represent a *developing* intraday quantity (a
    running volume profile POC, a running session VWAP) that is
    identical for the first and last bar of a session is a hallmark of
    having been computed once over the whole session and back-filled —
    exactly the shape of look-ahead leakage. Columns whose name starts
    with `prior_day`/`vp_prior` are exempt: a prior-completed-day
    quantity is legitimately constant across the entire current session,
    that's not leakage, that's the feature working as designed.
    """
    if column.startswith(_DEVELOPING_EXEMPT_PREFIXES):
        return LeakageFinding(
            "developing_profile_not_static", "WARNING", True,
            f"{column!r} is a prior-period feature — constant-within-session is expected, not checked",
        )
    if column not in df.columns or session_id_column not in df.columns or df.empty:
        return LeakageFinding("developing_profile_not_static", "WARNING", True, "column or session id absent")

    static_sessions = 0
    checked_sessions = 0
    for _, group in df.groupby(session_id_column):
        if len(group) < 2:
            continue
        checked_sessions += 1
        if group[column].nunique(dropna=True) <= 1:
            static_sessions += 1

    if checked_sessions == 0:
        return LeakageFinding("developing_profile_not_static", "WARNING", True, "no multi-row sessions to check")
    passed = static_sessions == 0
    return LeakageFinding(
        "developing_profile_not_static", "WARNING", passed,
        "value varies within every multi-row session" if passed
        else f"{static_sessions}/{checked_sessions} session(s) show a constant value across the whole session",
    )


def run_leakage_checks(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    train_index=None,
    test_index=None,
    trades_df: pd.DataFrame | None = None,
    oos_start_day=None,
    developing_profile_columns: tuple[str, ...] = (),
    session_id_column: str | None = None,
) -> LeakageReport:
    """Runs whichever checks the supplied inputs allow — every argument
    besides `df` is optional, and an omitted check simply doesn't run
    rather than being scored as a fabricated pass or fail.
    """
    findings = [
        check_timestamps_monotonic(df, timestamp_column),
        check_no_duplicate_timestamps(df, timestamp_column),
    ]
    if train_index is not None and test_index is not None:
        findings.append(check_train_test_index_overlap(train_index, test_index))
    if trades_df is not None and oos_start_day is not None:
        findings.append(check_outcome_horizon_overlap(trades_df, oos_start_day))
    if session_id_column is not None:
        for column in developing_profile_columns:
            findings.append(check_developing_profile_not_static_within_session(df, column, session_id_column))

    return LeakageReport(findings=tuple(findings))
