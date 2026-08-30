import pytest

from prop_alpha.data.quality_config import DataQualityConfig


def test_defaults_match_extension_spec_103():
    config = DataQualityConfig()
    assert config.minimum_score_for_research == 95.0
    assert config.minimum_score_for_paper == 97.0
    assert config.minimum_score_for_live == 99.0
    assert config.stale_thresholds.futures_seconds == 3.0
    assert config.stale_thresholds.options_seconds is None
    assert config.blocked_on.sequence_gap is True
    assert config.blocked_on.timestamp_error is True
    assert config.blocked_on.malformed_payload is True


def test_minimum_score_for_stage():
    config = DataQualityConfig()
    assert config.minimum_score_for_stage("research") == 95.0
    assert config.minimum_score_for_stage("paper") == 97.0
    assert config.minimum_score_for_stage("live") == 99.0


def test_minimum_score_for_unknown_stage_raises():
    with pytest.raises(ValueError, match="Unknown stage"):
        DataQualityConfig().minimum_score_for_stage("shadow")


def test_is_acceptable_for_respects_stage_threshold():
    config = DataQualityConfig()
    assert config.is_acceptable_for(95.0, "research")
    assert not config.is_acceptable_for(94.99, "research")
    assert config.is_acceptable_for(99.0, "live")
    assert not config.is_acceptable_for(98.99, "live")
