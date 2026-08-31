"""Real GEXBOT provider contract verification (hardening pass Blocker G,
Step 22-26).

Distinct from `health.compute_health` (Phase H's already-existing
connected/authenticated/error-rate snapshot, computed from *usage* — n_
polls/n_errors accumulated over a running polling session). This module
performs a one-shot, explicit contract check: authenticate, make one
documented/safe call (`GexbotClient.get_gex`), and inspect the actual
response shape against `parser._FIELD_ALIASES` field by field, reporting
what's really there. It never guesses at an undocumented endpoint and
never fabricates a capability — a metric the real response doesn't
contain is reported `UNKNOWN`, never silently marked `AVAILABLE`; a
capability that structurally doesn't exist anywhere in this repo
(historical data, order flow parsing) is reported `NOT_IMPLEMENTED`
regardless of whether the network call itself succeeds.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from prop_alpha.options.gexbot.client import GexbotClient
from prop_alpha.options.gexbot.parser import _FIELD_ALIASES
from prop_alpha.providers.base import ProviderContractState

DEFAULT_CAPABILITY_REPORT_DIR = Path("provider_capability_reports")


@dataclass(frozen=True)
class ProviderCapabilityReport:
    provider: str
    underlying: str
    checked_at: str
    authentication: str  # PASS / FAIL
    metric_availability: dict[str, str]  # metric name -> AVAILABLE / UNKNOWN / NOT_CHECKED
    historical_capability: str  # always NOT_IMPLEMENTED — structural fact, not network-dependent
    orderflow_capability: str  # always NOT_IMPLEMENTED — structural fact, not network-dependent
    contract_state: str  # ProviderContractState value
    error: str | None = None


def verify_provider_contract(
    client: GexbotClient | None = None,
    underlying: str = "SPX",
    api_key: str | None = None,
) -> ProviderCapabilityReport:
    """Never raises — every failure mode (missing `requests` package, no
    API key resolvable, network error, HTTP error, unexpected response
    shape) is caught and reported as a non-`LIVE_VERIFIED` contract
    state with `error` explaining why, so a caller can always render a
    report rather than crash. Nothing here simulates a successful
    verification when the real call didn't happen.
    """
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
    client = client or GexbotClient(api_key=api_key)
    not_checked = {name: "NOT_CHECKED" for name in _FIELD_ALIASES}

    try:
        raw = client.get_gex(underlying)
    except Exception as exc:  # noqa: BLE001 - any real-world failure reports UNAVAILABLE, never a fabricated pass
        return ProviderCapabilityReport(
            provider="gexbot", underlying=underlying, checked_at=checked_at,
            authentication="FAIL", metric_availability=not_checked,
            historical_capability="NOT_IMPLEMENTED", orderflow_capability="NOT_IMPLEMENTED",
            contract_state=ProviderContractState.UNAVAILABLE.value, error=str(exc),
        )

    if not isinstance(raw, dict):
        return ProviderCapabilityReport(
            provider="gexbot", underlying=underlying, checked_at=checked_at,
            authentication="PASS", metric_availability=not_checked,
            historical_capability="NOT_IMPLEMENTED", orderflow_capability="NOT_IMPLEMENTED",
            contract_state=ProviderContractState.DEGRADED.value,
            error=f"Response was not a JSON object (got {type(raw).__name__}); cannot inspect field availability.",
        )

    metric_availability = {
        name: ("AVAILABLE" if any(alias in raw for alias in aliases) else "UNKNOWN")
        for name, aliases in _FIELD_ALIASES.items()
    }
    any_available = any(v == "AVAILABLE" for v in metric_availability.values())
    contract_state = ProviderContractState.LIVE_VERIFIED if any_available else ProviderContractState.DEGRADED

    return ProviderCapabilityReport(
        provider="gexbot", underlying=underlying, checked_at=checked_at,
        authentication="PASS", metric_availability=metric_availability,
        historical_capability="NOT_IMPLEMENTED", orderflow_capability="NOT_IMPLEMENTED",
        contract_state=contract_state.value, error=None,
    )


def save_capability_report(
    report: ProviderCapabilityReport, out_dir: str | Path = DEFAULT_CAPABILITY_REPORT_DIR,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_timestamp = report.checked_at.replace(":", "").replace("+00:00", "Z")
    path = out_dir / f"gexbot_{report.underlying}_{safe_timestamp}.json"
    path.write_text(json.dumps(asdict(report), indent=2))
    return path
