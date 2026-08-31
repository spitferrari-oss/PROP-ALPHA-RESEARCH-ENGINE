import datetime as dt

import pandas as pd
import pytest

from prop_alpha.data.lake import DataLakePaths
from prop_alpha.data.lake_query import list_partitions, query_tier, tier_glob


def _write_partition(lake, tier, provider, instrument, schema, date, df):
    path = lake.partition_path(tier, provider, instrument, schema, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def test_tier_glob_matches_partition_path_pattern(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    pattern = tier_glob(lake, "raw", "databento", "NQ", "trades")
    assert pattern.replace("\\", "/").endswith("raw/databento/NQ/trades/*.parquet")


def test_list_partitions_finds_written_files(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    _write_partition(lake, "raw", "databento", "NQ", "trades", dt.date(2024, 1, 1), pd.DataFrame({"a": [1]}))
    _write_partition(lake, "raw", "databento", "NQ", "trades", dt.date(2024, 1, 2), pd.DataFrame({"a": [2]}))
    partitions = list_partitions(lake, "raw", "databento", "NQ", "trades")
    assert len(partitions) == 2


def test_list_partitions_empty_when_nothing_written(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    assert list_partitions(lake, "raw", "databento", "NQ", "trades") == []


def test_query_tier_unions_all_partitions(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    _write_partition(lake, "raw", "databento", "NQ", "trades", dt.date(2024, 1, 1), pd.DataFrame({"price": [100.0]}))
    _write_partition(lake, "raw", "databento", "NQ", "trades", dt.date(2024, 1, 2), pd.DataFrame({"price": [101.0]}))

    df = query_tier(lake, "raw", provider="databento", instrument="NQ", schema="trades")
    assert sorted(df["price"].tolist()) == [100.0, 101.0]


def test_query_tier_supports_custom_sql(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    _write_partition(
        lake, "raw", "databento", "NQ", "trades", dt.date(2024, 1, 1),
        pd.DataFrame({"price": [100.0, 200.0]}),
    )

    df = query_tier(
        lake, "raw", sql="SELECT COUNT(*) AS n FROM lake",
        provider="databento", instrument="NQ", schema="trades",
    )
    assert df["n"].iloc[0] == 2


def test_query_tier_raises_clear_error_when_nothing_matches(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    with pytest.raises(FileNotFoundError, match="No partition files matched"):
        query_tier(lake, "raw", provider="databento", instrument="NQ", schema="trades")


def test_query_tier_unions_across_instruments_when_unfiltered(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    _write_partition(lake, "raw", "databento", "NQ", "trades", dt.date(2024, 1, 1), pd.DataFrame({"price": [1.0]}))
    _write_partition(lake, "raw", "databento", "ES", "trades", dt.date(2024, 1, 1), pd.DataFrame({"price": [2.0]}))

    df = query_tier(lake, "raw", provider="databento")  # no instrument filter -> both
    assert len(df) == 2
