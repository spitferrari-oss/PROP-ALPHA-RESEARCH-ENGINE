import pytest

from prop_alpha.options.gexbot.auth import GEXBOT_API_KEY_ENV, resolve_api_key


def test_explicit_key_wins_over_env(monkeypatch):
    monkeypatch.setenv(GEXBOT_API_KEY_ENV, "env-key")
    assert resolve_api_key("explicit-key") == "explicit-key"


def test_falls_back_to_env_var(monkeypatch):
    monkeypatch.setenv(GEXBOT_API_KEY_ENV, "env-key")
    assert resolve_api_key(None) == "env-key"


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv(GEXBOT_API_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError, match="No GEXBOT API key"):
        resolve_api_key(None)
