import pandas as pd

from prop_alpha.sessions.engine import SessionEngine, SessionWindow


def _engine(**overrides):
    windows = [
        SessionWindow(name="US_OPEN", start="09:30", end="11:30"),
        SessionWindow(name="ASIA", start="19:00", end="03:00"),  # wraps midnight
    ]
    defaults = dict(windows=windows, holidays=["2024-01-15"], half_days={}, calendar_timezone="America/New_York")
    defaults.update(overrides)
    return SessionEngine(**defaults)


def test_simple_window_matches_inside_and_outside():
    engine = _engine()
    inside = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    outside = pd.Timestamp("2024-01-02 12:00", tz="America/New_York")
    assert "US_OPEN" in engine.active_windows(inside)
    assert "US_OPEN" not in engine.active_windows(outside)


def test_overnight_window_wraps_midnight():
    engine = _engine()
    late_night = pd.Timestamp("2024-01-02 23:00", tz="America/New_York")
    early_morning = pd.Timestamp("2024-01-03 02:00", tz="America/New_York")
    midday = pd.Timestamp("2024-01-02 12:00", tz="America/New_York")
    assert "ASIA" in engine.active_windows(late_night)
    assert "ASIA" in engine.active_windows(early_morning)
    assert "ASIA" not in engine.active_windows(midday)


def test_holiday_flagged():
    engine = _engine()
    holiday_ts = pd.Timestamp("2024-01-15 10:00", tz="America/New_York")
    normal_ts = pd.Timestamp("2024-01-16 10:00", tz="America/New_York")
    assert engine.is_holiday(holiday_ts)
    assert not engine.is_trading_day(holiday_ts)
    assert engine.is_trading_day(normal_ts)


def test_weekend_is_not_a_trading_day():
    engine = _engine()
    saturday = pd.Timestamp("2024-01-06 10:00", tz="America/New_York")
    assert not engine.is_trading_day(saturday)


def test_minutes_since_open():
    engine = _engine()
    ts = pd.Timestamp("2024-01-02 10:15", tz="America/New_York")
    assert engine.minutes_since_open(ts, "US_OPEN") == 45.0


def test_half_day_shortens_window():
    engine = _engine(half_days={"2024-01-02": "10:00"})
    before_cutoff = pd.Timestamp("2024-01-02 09:45", tz="America/New_York")
    after_cutoff = pd.Timestamp("2024-01-02 10:30", tz="America/New_York")
    assert "US_OPEN" in engine.active_windows(before_cutoff)
    assert "US_OPEN" not in engine.active_windows(after_cutoff)


def test_annotate_adds_expected_columns():
    engine = _engine()
    ts = pd.date_range("2024-01-02 09:30", periods=5, freq="15min", tz="America/New_York")
    df = pd.DataFrame({"timestamp": ts})
    out = engine.annotate(df)
    assert "session" in out.columns
    assert "in_session_us_open" in out.columns
    assert "is_trading_day" in out.columns
    assert (out["session"] == "US_OPEN").all()
