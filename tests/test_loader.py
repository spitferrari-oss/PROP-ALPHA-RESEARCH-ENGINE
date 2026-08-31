import pandas as pd
import pytest

from prop_alpha.data.loader import load_parquet, query, save_parquet


def test_save_and_load_parquet_round_trip(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3]})
    path = save_parquet(df, tmp_path / "data.parquet")
    loaded = load_parquet(path)
    pd.testing.assert_frame_equal(loaded, df)


def test_query_runs_sql_over_a_registered_parquet_view(tmp_path):
    # Regression test: CREATE VIEW ... FROM read_parquet(?) previously
    # raised "Unexpected prepared parameter. This type of statement can't
    # be prepared!" — DuckDB rejects a bound parameter inside CREATE VIEW.
    # This was never caught before because query() had no test at all.
    path = tmp_path / "bars.parquet"
    save_parquet(pd.DataFrame({"close": [100.0, 101.0, 102.0]}), path)

    result = query("SELECT COUNT(*) AS n, SUM(close) AS total FROM bars", bars=path)

    assert result["n"].iloc[0] == 3
    assert result["total"].iloc[0] == pytest.approx(303.0)


def test_query_joins_multiple_registered_views(tmp_path):
    path_a = tmp_path / "a.parquet"
    path_b = tmp_path / "b.parquet"
    save_parquet(pd.DataFrame({"id": [1, 2], "x": [10, 20]}), path_a)
    save_parquet(pd.DataFrame({"id": [1, 2], "y": [100, 200]}), path_b)

    result = query("SELECT a.id, a.x, b.y FROM a JOIN b USING (id) ORDER BY a.id", a=path_a, b=path_b)

    assert result["x"].tolist() == [10, 20]
    assert result["y"].tolist() == [100, 200]
