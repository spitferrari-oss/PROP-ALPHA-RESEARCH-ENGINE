"""Parquet + DuckDB data layer (spec §77)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def save_parquet(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def load_parquet(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def query(sql: str, **parquet_paths: str | Path) -> pd.DataFrame:
    """Run a SQL query over one or more parquet files via DuckDB.

    Each keyword becomes a view name usable in `sql`, e.g.
    query("select * from bars limit 10", bars="data/gold/nq_15m.parquet").
    """
    con = duckdb.connect(database=":memory:")
    try:
        for name, path in parquet_paths.items():
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet(?)", [str(path)])
        return con.execute(sql).fetchdf()
    finally:
        con.close()
