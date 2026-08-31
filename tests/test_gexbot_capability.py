import json

import pytest

from prop_alpha.options.gexbot.capability import (
    ProviderCapabilityReport,
    save_capability_report,
    verify_provider_contract,
)
from prop_alpha.options.gexbot.client import GexbotClient
from prop_alpha.providers.base import ProviderContractState


class _FakeSession:
    def __init__(self, response_json, status_code=200, raise_exc=None):
        self._response_json = response_json
        self._status_code = status_code
        self._raise_exc = raise_exc

    def get(self, url, params=None, headers=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(self._response_json, self._status_code)


class _FakeResponse:
    def __init__(self, response_json, status_code):
        self._response_json = response_json
        self.status_code = status_code
        self.text = "error" if status_code >= 400 else ""

    def json(self):
        return self._response_json


_FULL_RESPONSE = {
    "timestamp": "2024-01-02T10:00:00Z",
    "spot": 4500.0, "gex": 1.5e9, "dex": 2.0e8, "gamma_flip": 4490.0,
    "major_positive_gamma": 4550.0, "major_negative_gamma": 4450.0,
    "vanna": 1e6, "charm": 1e6, "vomma": 1e6, "skew": 0.1,
    "options_volume": 100000, "open_interest": 500000,
}


def test_verify_provider_contract_full_response_is_live_verified():
    client = GexbotClient(session=_FakeSession(_FULL_RESPONSE), api_key="test-key")
    report = verify_provider_contract(client, underlying="SPX")
    assert report.authentication == "PASS"
    assert report.contract_state == ProviderContractState.LIVE_VERIFIED.value
    assert report.metric_availability["gex"] == "AVAILABLE"
    assert report.metric_availability["dex"] == "AVAILABLE"
    assert report.error is None


def test_verify_provider_contract_partial_response_marks_missing_unknown():
    partial = {"spot": 4500.0, "gex": 1.5e9}
    client = GexbotClient(session=_FakeSession(partial), api_key="test-key")
    report = verify_provider_contract(client, underlying="SPX")
    assert report.metric_availability["gex"] == "AVAILABLE"
    assert report.metric_availability["vanna"] == "UNKNOWN"
    assert report.metric_availability["charm"] == "UNKNOWN"


def test_verify_provider_contract_never_fabricates_orderflow_or_historical():
    client = GexbotClient(session=_FakeSession(_FULL_RESPONSE), api_key="test-key")
    report = verify_provider_contract(client, underlying="SPX")
    assert report.historical_capability == "NOT_IMPLEMENTED"
    assert report.orderflow_capability == "NOT_IMPLEMENTED"


def test_verify_provider_contract_http_error_is_unavailable_not_fabricated():
    client = GexbotClient(session=_FakeSession({}, status_code=401), api_key="test-key")
    report = verify_provider_contract(client, underlying="SPX")
    assert report.authentication == "FAIL"
    assert report.contract_state == ProviderContractState.UNAVAILABLE.value
    assert report.error is not None
    assert all(v == "NOT_CHECKED" for v in report.metric_availability.values())


def test_verify_provider_contract_missing_api_key_is_unavailable():
    client = GexbotClient(session=_FakeSession(_FULL_RESPONSE), api_key=None)
    report = verify_provider_contract(client, underlying="SPX")
    assert report.contract_state == ProviderContractState.UNAVAILABLE.value
    assert report.authentication == "FAIL"


def test_verify_provider_contract_non_dict_response_is_degraded():
    client = GexbotClient(session=_FakeSession(["not", "a", "dict"]), api_key="test-key")
    report = verify_provider_contract(client, underlying="SPX")
    assert report.contract_state == ProviderContractState.DEGRADED.value
    assert report.authentication == "PASS"


def test_verify_provider_contract_empty_but_valid_response_is_degraded():
    client = GexbotClient(session=_FakeSession({}), api_key="test-key")
    report = verify_provider_contract(client, underlying="SPX")
    assert report.contract_state == ProviderContractState.DEGRADED.value
    assert all(v == "UNKNOWN" for v in report.metric_availability.values())


def test_save_capability_report_writes_readable_json(tmp_path):
    report = ProviderCapabilityReport(
        provider="gexbot", underlying="SPX", checked_at="2024-01-02T10:00:00+00:00",
        authentication="PASS", metric_availability={"gex": "AVAILABLE"},
        historical_capability="NOT_IMPLEMENTED", orderflow_capability="NOT_IMPLEMENTED",
        contract_state="LIVE_VERIFIED", error=None,
    )
    path = save_capability_report(report, out_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["contract_state"] == "LIVE_VERIFIED"
    assert data["metric_availability"]["gex"] == "AVAILABLE"
