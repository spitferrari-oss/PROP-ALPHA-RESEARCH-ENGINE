from prop_alpha.data.recording_config import DEFAULT_OUTCOME_HORIZONS, RecordingConfig


def test_defaults_match_extension_spec_101():
    config = RecordingConfig()
    assert config.enabled is True
    assert config.canonical_timezone == "UTC"
    assert config.futures_snapshot_frequency == "1s"
    assert config.options_snapshot_frequency == "provider_native"
    assert config.outcome_horizons == DEFAULT_OUTCOME_HORIZONS


def test_to_yaml_and_from_yaml_round_trip(tmp_path):
    config = RecordingConfig(enabled=False, futures_snapshot_frequency="5s", outcome_horizons=("1m", "10m"))
    path = tmp_path / "recording.yaml"
    config.to_yaml(path)
    loaded = RecordingConfig.from_yaml(path)
    assert loaded == config


def test_yaml_file_has_recording_key_and_every_field(tmp_path):
    path = tmp_path / "recording.yaml"
    RecordingConfig().to_yaml(path)
    text = path.read_text()
    assert text.startswith("recording:")
    for field_name in (
        "enabled", "canonical_timezone", "futures_snapshot_frequency",
        "options_snapshot_frequency", "outcome_horizons",
    ):
        assert f"{field_name}:" in text
