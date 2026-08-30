import pytest

from prop_alpha.providers.base import DataLevel
from prop_alpha.providers.databento.symbology import (
    DatabentoInstrumentMapping,
    DEFAULT_SCHEMA_BY_LEVEL,
    known_instruments,
    register_mapping,
    resolve,
)


@pytest.mark.parametrize("symbol", ["NQ", "MNQ", "ES", "MES", "DAX", "FDAX", "FDXM", "YM", "MYM"])
def test_extension_spec_instrument_list_is_resolvable(symbol):
    mapping = resolve(symbol)
    assert mapping.generic_symbol == symbol
    assert mapping.dataset
    assert mapping.raw_symbol


def test_resolve_is_case_insensitive():
    assert resolve("nq").generic_symbol == "NQ"


def test_resolve_unknown_instrument_raises_dataset_required_error():
    with pytest.raises(ValueError, match="DATASET_REQUIRED"):
        resolve("NOT_A_REAL_INSTRUMENT")


def test_register_mapping_adds_new_instrument_without_touching_module_code():
    mapping = DatabentoInstrumentMapping(
        generic_symbol="RTY", dataset="GLBX.MDP3", raw_symbol="RTY.c.0",
        tick_size=0.1, point_value=50.0,
    )
    register_mapping(mapping)
    assert resolve("RTY") is mapping
    assert "RTY" in known_instruments()


def test_default_schema_by_level_covers_every_data_level():
    assert set(DEFAULT_SCHEMA_BY_LEVEL) == {DataLevel.L1, DataLevel.L2, DataLevel.L3, DataLevel.L4}
