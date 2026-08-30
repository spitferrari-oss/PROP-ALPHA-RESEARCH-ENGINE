import datetime as dt

import pytest

from prop_alpha.data.lake import TIERS, DataLakePaths


def test_ensure_creates_every_tier(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    lake.ensure()
    for name in TIERS:
        assert (tmp_path / "lake" / name).is_dir()


def test_tier_properties_match_root_layout(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    assert lake.raw == tmp_path / "lake" / "raw"
    assert lake.normalized == tmp_path / "lake" / "normalized"
    assert lake.curated == tmp_path / "lake" / "curated"
    assert lake.features == tmp_path / "lake" / "features"
    assert lake.outcomes == tmp_path / "lake" / "outcomes"
    assert lake.snapshots == tmp_path / "lake" / "snapshots"
    assert lake.metadata == tmp_path / "lake" / "metadata"


def test_unknown_tier_raises():
    lake = DataLakePaths()
    with pytest.raises(ValueError, match="Unknown data lake tier"):
        lake.tier("bronze")


def test_partition_path_matches_extension_11_example(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    path = lake.partition_path("raw", "databento", "NQ", "trades", dt.date(2026, 8, 30))
    assert path == tmp_path / "lake" / "raw" / "databento" / "NQ" / "trades" / "2026-08-30.parquet"


def test_default_root_is_data_lake():
    assert DataLakePaths().root.as_posix() == "data/lake"
