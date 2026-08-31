"""DuckDB query layer over the data lake (extension spec §6: "Database di
query: DuckDB"; §10-11's partitioning). Queries a whole partitioned tier —
every day's parquet file under a provider/instrument/schema — as a single
view via a glob pattern, rather than requiring a caller to enumerate
files. Follows the same scoped-DuckDB-connection-over-a-registered-view
shape as `data.loader.query`, with one difference: DuckDB rejects a
prepared parameter inside `CREATE VIEW` ("Unexpected prepared parameter.
This type of statement can't be prepared!"), so the glob pattern — built
entirely from this module's own inputs, not external text — is inlined as
an escaped string literal instead of bound with `?` (caught while writing
this module's own tests; `data.loader.query` carries the same latent bug,
untested and uncalled elsewhere in this repo).
"""
from __future__ import annotations

import glob as globmod
from pathlib import Path

import duckdb
import pandas as pd

from prop_alpha.data.lake import DataLakePaths


def tier_glob(
    lake: DataLakePaths,
    tier: str,
    provider: str | None = None,
    instrument: str | None = None,
    schema: str | None = None,
) -> str:
    """The DuckDB/glob pattern for a tier, optionally narrowed by
    provider/instrument/schema — an omitted segment becomes a `*`
    wildcard across every value at that level.
    """
    parts = [provider or "*", instrument or "*", schema or "*", "*.parquet"]
    return str(lake.tier(tier).joinpath(*parts))


def list_partitions(
    lake: DataLakePaths,
    tier: str,
    provider: str | None = None,
    instrument: str | None = None,
    schema: str | None = None,
) -> list[Path]:
    """Lists partition files matching the glob without loading any data —
    e.g. used by ingestion's resume logic to know which days are already
    present.
    """
    pattern = tier_glob(lake, tier, provider, instrument, schema)
    return sorted(Path(p) for p in globmod.glob(pattern))


def query_tier(
    lake: DataLakePaths,
    tier: str,
    sql: str = "SELECT * FROM lake",
    provider: str | None = None,
    instrument: str | None = None,
    schema: str | None = None,
) -> pd.DataFrame:
    """Runs `sql` (default: everything) over every parquet file matching
    the given tier/provider/instrument/schema as a single `lake` view — a
    day-partitioned dataset queries exactly like one file. Raises
    `FileNotFoundError` up front when nothing matches, rather than
    surfacing DuckDB's own no-files error.
    """
    partitions = list_partitions(lake, tier, provider, instrument, schema)
    if not partitions:
        pattern = tier_glob(lake, tier, provider, instrument, schema)
        raise FileNotFoundError(f"No partition files matched {pattern!r} in the data lake.")

    pattern = tier_glob(lake, tier, provider, instrument, schema)
    con = duckdb.connect(database=":memory:")
    try:
        escaped_pattern = pattern.replace("'", "''")
        con.execute(f"CREATE VIEW lake AS SELECT * FROM read_parquet('{escaped_pattern}', union_by_name=true)")
        return con.execute(sql).fetchdf()
    finally:
        con.close()
