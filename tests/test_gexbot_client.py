import time

import pytest

from prop_alpha.options.gexbot.auth import GEXBOT_API_KEY_ENV
from prop_alpha.options.gexbot.client import GexbotApiError, GexbotClient


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.response


def test_get_gex_builds_correct_url_and_auth_header():
    session = _FakeSession(_FakeResponse(payload={"gex": 1.0}))
    client = GexbotClient(session=session, api_key="test-key")
    result = client.get_gex("SPX")
    assert result == {"gex": 1.0}
    call = session.calls[0]
    assert call["url"] == "https://api.gexbot.com/gex/SPX"
    assert call["headers"]["Authorization"] == "Bearer test-key"


def test_get_levels_and_orderflow_use_distinct_paths():
    session = _FakeSession(_FakeResponse(payload={}))
    client = GexbotClient(session=session, api_key="test-key")
    client.get_levels("SPX")
    client.get_orderflow("SPX")
    assert session.calls[0]["url"].endswith("/gex/SPX/levels")
    assert session.calls[1]["url"].endswith("/gex/SPX/flow")


def test_error_status_raises_gexbot_api_error():
    session = _FakeSession(_FakeResponse(status_code=401, text="unauthorized"))
    client = GexbotClient(session=session, api_key="test-key")
    with pytest.raises(GexbotApiError, match="401"):
        client.get_gex("SPX")


def test_missing_api_key_raises_before_any_request(monkeypatch):
    monkeypatch.delenv(GEXBOT_API_KEY_ENV, raising=False)
    session = _FakeSession(_FakeResponse(payload={}))
    client = GexbotClient(session=session, api_key=None)
    with pytest.raises(RuntimeError, match="No GEXBOT API key"):
        client.get_gex("SPX")
    assert session.calls == []


def test_no_session_and_requests_not_installed_raises_clear_runtime_error():
    client = GexbotClient(session=None, api_key="test-key")
    with pytest.raises(RuntimeError, match="not installed"):
        client.get_gex("SPX")


def test_start_polling_calls_back_repeatedly_and_stops_on_close():
    session = _FakeSession(_FakeResponse(payload={"gex": 1.0}))
    client = GexbotClient(session=session, api_key="test-key")
    calls = []
    handle = client.start_polling("SPX", interval_seconds=0.01, callback=calls.append)
    time.sleep(0.05)
    handle.close()

    n_at_close = len(calls)
    assert n_at_close >= 2
    assert not handle.is_active

    time.sleep(0.05)
    assert len(calls) == n_at_close  # no more callbacks after close
