"""Data Quality Engine (extension spec §19-20): every feed/dataset gets a
graduated 0-100 `DATA_QUALITY_SCORE`, not a bare pass/fail — a dataset
with a handful of glitches out of thousands of rows should score high but
not perfect, and the severity bands (§20) let a caller decide what to do
about each range. This is a different tool from
`prop_alpha.data.quality.validate_ohlcv` (the original Phase 1 gate: a
strict must-pass check the core synthetic-data pipeline runs before any
backtest) — this module is for the Data Feed extension's real-provider
historical/live data, covering the full extension §19 checklist rather
than just OHLCV bar sanity, and generic across bars/trades/quote schemas.

Each check is column-presence-aware: a check that doesn't apply to the
frame it's given (e.g. crossed-book on a bars-only frame with no bid/ask
columns) is marked `applicable=False` and contributes nothing to the
score, rather than fabricating a pass or a violation for data that was
never there (extension §51-52's "never silently substitute").
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from prop_alpha.data.live.health import FeedHealth
from prop_alpha.data.quality_config import DataQualityConfig

SEVERITY_BANDS = (
    (99.0, "EXCELLENT"),
    (97.0, "GOOD"),
    (95.0, "WARNING"),
)


def severity_for_score(score: float) -> str:
    for threshold, label in SEVERITY_BANDS:
        if score >= threshold:
            return label
    return "CRITICAL"


DEFAULT_CHECK_WEIGHTS: dict[str, float] = {
    "missing_timestamps": 20.0,
    "duplicate_timestamps": 15.0,
    "out_of_order": 15.0,
    "invalid_prices": 20.0,
    "negative_volume": 10.0,
    "crossed_book": 15.0,
    "locked_book": 5.0,
    "impossible_spreads": 10.0,
    "sequence_gaps": 15.0,
    "abnormal_timestamp_jumps": 10.0,
    "contract_mismatch": 25.0,
    "stale_feed": 20.0,
    "malformed_payload": 20.0,
}

_BID_CANDIDATES = ("bid_price", "bid_px_00", "bid")
_ASK_CANDIDATES = ("ask_price", "ask_px_00", "ask")

_BLOCKED_ON_CHECK_NAMES = {
    "sequence_gap": ("sequence_gaps",),
    "timestamp_error": ("duplicate_timestamps", "out_of_order", "abnormal_timestamp_jumps", "missing_timestamps"),
    "malformed_payload": ("malformed_payload",),
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    n_checked: int
    n_violations: int
    applicable: bool = True

    @property
    def violation_rate(self) -> float:
        if not self.applicable or self.n_checked == 0:
            return 0.0
        return self.n_violations / self.n_checked


@dataclass(frozen=True)
class DataQualityReport:
    checks: list[CheckResult] = field(default_factory=list)
    score: float = 100.0
    severity: str = "EXCELLENT"

    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if c.applicable and c.n_violations > 0]


def _find_bid_ask_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    bid = next((c for c in _BID_CANDIDATES if c in df.columns), None)
    ask = next((c for c in _ASK_CANDIDATES if c in df.columns), None)
    return bid, ask


def _check_missing_timestamps(df: pd.DataFrame, expected_freq: pd.Timedelta | None) -> CheckResult:
    if expected_freq is None or len(df) < 2:
        return CheckResult("missing_timestamps", 0, 0, applicable=False)
    ts = df["timestamp"].sort_values()
    span = ts.iloc[-1] - ts.iloc[0]
    expected_steps = max(int(span / expected_freq), 1)
    actual_steps = len(df) - 1
    missing = max(expected_steps - actual_steps, 0)
    return CheckResult("missing_timestamps", n_checked=expected_steps, n_violations=missing)


def _check_duplicate_timestamps(df: pd.DataFrame) -> CheckResult:
    n_dupes = int(df["timestamp"].duplicated().sum())
    return CheckResult("duplicate_timestamps", n_checked=len(df), n_violations=n_dupes)


def _check_out_of_order(df: pd.DataFrame) -> CheckResult:
    ts = df["timestamp"].sort_index()
    diffs = ts.diff().dropna()
    n = int((diffs < pd.Timedelta(0)).sum())
    return CheckResult("out_of_order", n_checked=len(diffs), n_violations=n)


def _check_invalid_prices(df: pd.DataFrame) -> CheckResult:
    price_cols = [c for c in ("open", "high", "low", "close", "price") if c in df.columns]
    if not price_cols:
        return CheckResult("invalid_prices", 0, 0, applicable=False)
    sub = df[price_cols]
    bad = (sub.isna() | (sub <= 0)).any(axis=1)
    return CheckResult("invalid_prices", n_checked=len(df), n_violations=int(bad.sum()))


def _check_negative_volume(df: pd.DataFrame) -> CheckResult:
    vol_cols = [c for c in ("volume", "size") if c in df.columns]
    if not vol_cols:
        return CheckResult("negative_volume", 0, 0, applicable=False)
    bad = (df[vol_cols] < 0).any(axis=1)
    return CheckResult("negative_volume", n_checked=len(df), n_violations=int(bad.sum()))


def _check_crossed_book(df: pd.DataFrame) -> CheckResult:
    bid_col, ask_col = _find_bid_ask_columns(df)
    if bid_col is None or ask_col is None:
        return CheckResult("crossed_book", 0, 0, applicable=False)
    bad = df[bid_col] > df[ask_col]
    return CheckResult("crossed_book", n_checked=len(df), n_violations=int(bad.sum()))


def _check_locked_book(df: pd.DataFrame) -> CheckResult:
    bid_col, ask_col = _find_bid_ask_columns(df)
    if bid_col is None or ask_col is None:
        return CheckResult("locked_book", 0, 0, applicable=False)
    bad = df[bid_col] == df[ask_col]
    return CheckResult("locked_book", n_checked=len(df), n_violations=int(bad.sum()))


def _check_impossible_spreads(
    df: pd.DataFrame, max_spread_ticks: float | None = None, tick_size: float | None = None,
) -> CheckResult:
    bid_col, ask_col = _find_bid_ask_columns(df)
    if bid_col is None or ask_col is None:
        return CheckResult("impossible_spreads", 0, 0, applicable=False)
    spread = df[ask_col] - df[bid_col]
    bad = spread < 0
    if max_spread_ticks is not None and tick_size is not None:
        bad = bad | (spread > max_spread_ticks * tick_size)
    return CheckResult("impossible_spreads", n_checked=len(df), n_violations=int(bad.sum()))


def _check_sequence_gaps(df: pd.DataFrame) -> CheckResult:
    if "sequence" not in df.columns:
        return CheckResult("sequence_gaps", 0, 0, applicable=False)
    seq = df["sequence"].dropna()
    if len(seq) < 2:
        return CheckResult("sequence_gaps", n_checked=0, n_violations=0)
    diffs = seq.diff().dropna()
    n_gaps = int((diffs != 1).sum())
    return CheckResult("sequence_gaps", n_checked=len(diffs), n_violations=n_gaps)


def _check_abnormal_timestamp_jumps(
    df: pd.DataFrame, expected_freq: pd.Timedelta | None, jump_multiple: float = 5.0,
) -> CheckResult:
    if expected_freq is None or len(df) < 2:
        return CheckResult("abnormal_timestamp_jumps", 0, 0, applicable=False)
    diffs = df["timestamp"].sort_values().diff().dropna()
    n_jumps = int((diffs > expected_freq * jump_multiple).sum())
    return CheckResult("abnormal_timestamp_jumps", n_checked=len(diffs), n_violations=n_jumps)


def _check_contract_mismatch(df: pd.DataFrame, expected_instrument: str | None) -> CheckResult:
    symbol_col = next((c for c in ("symbol", "instrument", "raw_symbol") if c in df.columns), None)
    if symbol_col is None or expected_instrument is None:
        return CheckResult("contract_mismatch", 0, 0, applicable=False)
    # A contract-month suffix (e.g. "NQZ4") is a legitimate label for the
    # generic root ("NQ"), not a mismatch — compare the root prefix, not
    # exact equality.
    bad = ~df[symbol_col].astype(str).str.upper().str.startswith(str(expected_instrument).upper())
    return CheckResult("contract_mismatch", n_checked=len(df), n_violations=int(bad.sum()))


def _score_from_checks(checks: list[CheckResult], weights: dict[str, float]) -> float:
    penalty = sum(weights.get(c.name, 0.0) * c.violation_rate for c in checks if c.applicable)
    return max(0.0, min(100.0, 100.0 - penalty))


def evaluate_batch_quality(
    df: pd.DataFrame,
    expected_freq: pd.Timedelta | None = None,
    expected_instrument: str | None = None,
    max_spread_ticks: float | None = None,
    tick_size: float | None = None,
    weights: dict[str, float] | None = None,
) -> DataQualityReport:
    """Runs the extension §19 checklist against a historical/batch frame
    (bars, trades, or quotes — whichever columns are present). `df` must
    carry a `timestamp` column; every other check gracefully marks itself
    not-applicable when its required columns are absent.
    """
    weights = weights or DEFAULT_CHECK_WEIGHTS
    checks = [
        _check_missing_timestamps(df, expected_freq),
        _check_duplicate_timestamps(df),
        _check_out_of_order(df),
        _check_invalid_prices(df),
        _check_negative_volume(df),
        _check_crossed_book(df),
        _check_locked_book(df),
        _check_impossible_spreads(df, max_spread_ticks, tick_size),
        _check_sequence_gaps(df),
        _check_abnormal_timestamp_jumps(df, expected_freq),
        _check_contract_mismatch(df, expected_instrument),
    ]
    score = _score_from_checks(checks, weights)
    return DataQualityReport(checks=checks, score=score, severity=severity_for_score(score))


def evaluate_live_quality(
    batch_report: DataQualityReport,
    feed_health: FeedHealth,
    stale_threshold_seconds: float,
    n_messages: int,
    n_malformed: int = 0,
    weights: dict[str, float] | None = None,
) -> DataQualityReport:
    """Folds the live-specific stale-feed signal (from
    `data.live.health.FeedHealth` — already computed from a
    `ConnectionManager` + `MessageBuffer`, not recomputed here) and a
    malformed-payload count into a batch-style report over the same
    window's buffered messages.
    """
    weights = weights or DEFAULT_CHECK_WEIGHTS
    is_stale = (
        feed_health.last_message_age_seconds is not None
        and feed_health.last_message_age_seconds > stale_threshold_seconds
    )
    stale_check = CheckResult("stale_feed", n_checked=1, n_violations=1 if is_stale else 0)
    malformed_check = CheckResult(
        "malformed_payload", n_checked=max(n_messages, 1), n_violations=n_malformed, applicable=n_messages > 0,
    )
    checks = list(batch_report.checks) + [stale_check, malformed_check]
    score = _score_from_checks(checks, weights)
    return DataQualityReport(checks=checks, score=score, severity=severity_for_score(score))


def is_blocked(report: DataQualityReport, config: DataQualityConfig) -> tuple[bool, list[str]]:
    """Independent of the graduated score: extension §103's `blocked_on`
    flags are hard stops — a single violation in a flagged category blocks
    regardless of how good the overall score still looks.
    """
    flag_values = {
        "sequence_gap": config.blocked_on.sequence_gap,
        "timestamp_error": config.blocked_on.timestamp_error,
        "malformed_payload": config.blocked_on.malformed_payload,
    }
    check_by_name = {c.name: c for c in report.checks}
    reasons = []
    for flag_name, check_names in _BLOCKED_ON_CHECK_NAMES.items():
        if not flag_values[flag_name]:
            continue
        for check_name in check_names:
            check = check_by_name.get(check_name)
            if check is not None and check.applicable and check.n_violations > 0:
                reasons.append(f"{flag_name}:{check_name}")
    return bool(reasons), reasons
