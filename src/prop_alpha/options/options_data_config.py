"""Loader for `config/options_data.yaml` (hardening pass Step 20/32):
the GEXBOT metric inventory (which metrics this repo tracks and whether
each is native to a snapshot) plus the options feature contract — every
derived options feature this repo computes declares its source, formula,
and `missing_data_behavior`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_OPTIONS_DATA_CONFIG_PATH = Path("config/options_data.yaml")


@dataclass(frozen=True)
class OptionsFeatureContract:
    name: str
    source: str
    formula: str
    native_or_derived: str
    minimum_data_quality: str
    maximum_data_age_seconds: float | None
    missing_data_behavior: str


def load_options_data_config(path: str | Path = DEFAULT_OPTIONS_DATA_CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_gexbot_metric_inventory(path: str | Path = DEFAULT_OPTIONS_DATA_CONFIG_PATH) -> dict[str, dict]:
    return load_options_data_config(path).get("gexbot", {}).get("metrics", {})


def load_options_feature_contracts(
    path: str | Path = DEFAULT_OPTIONS_DATA_CONFIG_PATH,
) -> list[OptionsFeatureContract]:
    raw = load_options_data_config(path).get("features", [])
    return [
        OptionsFeatureContract(
            name=f["name"], source=f["source"], formula=f["formula"],
            native_or_derived=f["native_or_derived"], minimum_data_quality=f["minimum_data_quality"],
            maximum_data_age_seconds=f.get("maximum_data_age_seconds"),
            missing_data_behavior=f["missing_data_behavior"],
        )
        for f in raw
    ]
