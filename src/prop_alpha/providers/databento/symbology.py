"""Databento symbology mapping (extension spec §4): the generic instrument
symbols PARE strategies/config use (NQ, ES, DAX, ...) vs. Databento's own
dataset/raw-symbol/`stype_in` conventions. This is the ONLY place that
vendor-specific symbol knowledge lives — `historical.py`/`live.py` never
hardcode a dataset code or raw symbol string themselves.

The default mappings below cover the extension §4 instrument list (NQ,
MNQ, ES, MES, DAX/FDAX/FDXM, YM, MYM) using Databento's continuous-contract
symbology (`stype_in="continuous"`, raw symbols like `"NQ.c.0"`) against
CME Globex (`GLBX.MDP3`) and Eurex (`XEUR.EOBI`). These are best-effort
defaults, not guaranteed current against Databento's live catalog — a
request for an unmapped or since-changed symbol fails with a clear
`DATASET_REQUIRED`-style error (spec §123's own principle: never guess
silently) rather than being retried against a made-up fallback. Extension
§4 requires new instruments to be addable "senza modificare il core":
`register_mapping` does exactly that.
"""
from __future__ import annotations

from dataclasses import dataclass

from prop_alpha.providers.base import DataLevel


@dataclass(frozen=True)
class DatabentoInstrumentMapping:
    generic_symbol: str
    dataset: str
    raw_symbol: str
    stype_in: str = "continuous"
    exchange: str = "CME"
    asset_class: str = "FUTURE"
    currency: str = "USD"
    tick_size: float = 0.25
    point_value: float = 20.0
    multiplier: float = 1.0
    timezone: str = "America/New_York"


# Default Databento schema per DataLevel (extension §5) when the caller
# doesn't pass an explicit `schema=`. `ohlcv-1m` for L1 matches this
# repo's existing M15/M1-bar pipeline; L2-L4 map to Databento's own
# trades/MBP-10/MBO schemas.
DEFAULT_SCHEMA_BY_LEVEL: dict[DataLevel, str] = {
    DataLevel.L1: "ohlcv-1m",
    DataLevel.L2: "trades",
    DataLevel.L3: "mbp-10",
    DataLevel.L4: "mbo",
}

_MAPPINGS: dict[str, DatabentoInstrumentMapping] = {}


def _seed_defaults() -> None:
    cme = dict(dataset="GLBX.MDP3", exchange="CME", currency="USD", timezone="America/New_York")
    eurex = dict(dataset="XEUR.EOBI", exchange="EUREX", currency="EUR", timezone="Europe/Berlin")

    defaults = [
        DatabentoInstrumentMapping(generic_symbol="NQ", raw_symbol="NQ.c.0", tick_size=0.25, point_value=20.0, **cme),
        DatabentoInstrumentMapping(generic_symbol="MNQ", raw_symbol="MNQ.c.0", tick_size=0.25, point_value=2.0, **cme),
        DatabentoInstrumentMapping(generic_symbol="ES", raw_symbol="ES.c.0", tick_size=0.25, point_value=50.0, **cme),
        DatabentoInstrumentMapping(generic_symbol="MES", raw_symbol="MES.c.0", tick_size=0.25, point_value=5.0, **cme),
        DatabentoInstrumentMapping(generic_symbol="YM", raw_symbol="YM.c.0", tick_size=1.0, point_value=5.0, **cme),
        DatabentoInstrumentMapping(generic_symbol="MYM", raw_symbol="MYM.c.0", tick_size=1.0, point_value=0.5, **cme),
        DatabentoInstrumentMapping(generic_symbol="DAX", raw_symbol="FDAX.c.0", tick_size=0.5, point_value=25.0, **eurex),
        DatabentoInstrumentMapping(generic_symbol="FDAX", raw_symbol="FDAX.c.0", tick_size=0.5, point_value=25.0, **eurex),
        DatabentoInstrumentMapping(generic_symbol="FDXM", raw_symbol="FDXM.c.0", tick_size=1.0, point_value=5.0, **eurex),
    ]
    for mapping in defaults:
        _MAPPINGS[mapping.generic_symbol] = mapping


_seed_defaults()


def register_mapping(mapping: DatabentoInstrumentMapping) -> None:
    """Add or override an instrument mapping without touching this module's
    code (extension §4).
    """
    _MAPPINGS[mapping.generic_symbol] = mapping


def resolve(instrument: str) -> DatabentoInstrumentMapping:
    try:
        return _MAPPINGS[instrument.upper()]
    except KeyError:
        raise ValueError(
            f"DATASET_REQUIRED: no Databento symbology mapping for '{instrument}'. "
            "Register one via providers.databento.symbology.register_mapping() before "
            "requesting historical/live data for it — never guessing a raw symbol."
        ) from None


def known_instruments() -> list[str]:
    return sorted(_MAPPINGS)
