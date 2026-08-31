import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from prop_alpha.data.ingest import ingest_historical
from prop_alpha.data.lake import DataLakePaths
from prop_alpha.data.quality_config import DataQualityConfig
from prop_alpha.providers.base import DataLevel


def _bars(day: dt.date, n: int = 5) -> pd.DataFrame:
    start = pd.Timestamp(day.year, day.month, day.day, 9, 30, tz="UTC")
    ts = pd.date_range(start, periods=n, freq="1min")
    df = pd.DataFrame({
        "timestamp": ts, "open": [100.0] * n, "high": [100.5] * n,
        "low": [99.5] * n, "close": [100.2] * n, "volume": [10] * n,
    })
    df.attrs["dataset"] = "GLBX.MDP3"
    return df


class _ScriptedProvider:
    name = "fake"

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls = []

    def get_historical(self, instrument, start, end, level, schema=None):
        self.calls.append(start)
        item = self.responses.get(start)
        if isinstance(item, list):
            item = item.pop(0)
        if isinstance(item, Exception):
            raise item
        if item is None:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        return item


def test_ingest_writes_one_partition_per_day(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    d1, d2 = dt.date(2024, 1, 2), dt.date(2024, 1, 3)
    provider = _ScriptedProvider({d1: _bars(d1), d2: _bars(d2)})

    result = ingest_historical(provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d2, lake)

    assert result.n_written == 2
    assert result.n_failed == 0
    for day_result in result.days:
        assert day_result.status == "WRITTEN"
        assert Path(day_result.path).exists()


def test_ingest_resume_skips_existing_partition(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    d1 = dt.date(2024, 1, 2)
    provider = _ScriptedProvider({d1: _bars(d1)})
    ingest_historical(provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d1, lake)
    assert provider.calls == [d1]

    result = ingest_historical(provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d1, lake)
    assert result.days[0].status == "SKIPPED_EXISTING"
    assert provider.calls == [d1]  # no new call made on resume


def test_ingest_retries_then_succeeds(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    d1 = dt.date(2024, 1, 2)
    provider = _ScriptedProvider({d1: [ConnectionError("boom"), _bars(d1)]})

    result = ingest_historical(
        provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d1, lake,
        max_retries=3, sleep_fn=lambda s: None,
    )
    assert result.n_written == 1
    assert len(provider.calls) == 2


def test_ingest_marks_failed_after_exhausting_retries(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    d1 = dt.date(2024, 1, 2)
    provider = _ScriptedProvider({d1: [ConnectionError("a"), ConnectionError("b"), ConnectionError("c")]})

    result = ingest_historical(
        provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d1, lake,
        max_retries=3, sleep_fn=lambda s: None,
    )
    assert result.n_failed == 1
    assert result.days[0].status == "FAILED"
    assert "c" in result.days[0].error
    assert len(provider.calls) == 3


def test_ingest_skips_empty_days_without_writing(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    d1 = dt.date(2024, 1, 6)
    provider = _ScriptedProvider({d1: None})

    result = ingest_historical(provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d1, lake)
    assert result.days[0].status == "SKIPPED_EMPTY"
    partition = lake.partition_path("raw", "fake", "NQ", "ohlcv-1m", d1)
    assert not partition.exists()


def test_ingest_flags_quality_blocked_day_but_still_writes(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    d1 = dt.date(2024, 1, 2)
    df = _bars(d1, n=5)
    df["sequence"] = [1, 2, 3, 5, 6]  # a sequence gap -> blocked_on trips
    provider = _ScriptedProvider({d1: df})

    result = ingest_historical(
        provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d1, lake,
        quality_config=DataQualityConfig(),
    )
    day_result = result.days[0]
    assert day_result.status == "WRITTEN"
    assert day_result.quality_blocked is True
    assert any("sequence_gap" in r for r in day_result.blocked_reasons)
    assert Path(day_result.path).exists()
    assert result.n_quality_blocked == 1


def test_ingest_covers_full_date_range_inclusive(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    d1, d2, d3 = dt.date(2024, 1, 2), dt.date(2024, 1, 3), dt.date(2024, 1, 4)
    provider = _ScriptedProvider({d: _bars(d) for d in (d1, d2, d3)})

    result = ingest_historical(provider, "NQ", DataLevel.L1, "ohlcv-1m", d1, d3, lake)
    assert [r.date for r in result.days] == [d1, d2, d3]
    assert result.n_written == 3
