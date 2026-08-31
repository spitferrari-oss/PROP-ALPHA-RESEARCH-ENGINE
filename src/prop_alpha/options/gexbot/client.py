"""GEXBOT HTTP client (extension spec §24). Wraps GEXBOT's REST API
behind a minimal interface (`get_gex`, `get_levels`, `get_orderflow`,
`start_polling`) so the rest of this adapter never talks to an HTTP
library directly. Endpoint paths and the field names `parser.py` looks
for are this module's best-effort understanding of GEXBOT's API surface —
GEXBOT is a smaller, less-documented service than Databento, so treat
these as a starting point to verify against a real account/plan before
production use, not a confirmed contract (extension §26 itself warns
against assuming a metric's shape or endpoint).

Fully testable without network access or an API key (extension §134/§136):
`session` is dependency-injected — any object exposing a `.get(url,
params=..., headers=...)` method returning a response with
`.status_code`/`.json()` works, including a test fake. The real `requests`
session is constructed lazily, only when no session is supplied.

`start_polling` runs a background daemon thread — GEXBOT's plan/API tier
this adapter targets is REST/polling rather than websocket push, per this
module's best-effort understanding above. The polling loop itself isn't
exercised by the automated test suite beyond a short real-time smoke test
(no live network); `providers.gexbot.GexbotOptionsProvider.subscribe_live`
is otherwise tested via an injected fake client whose `start_polling`
calls back synchronously.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from prop_alpha.options.gexbot.auth import resolve_api_key

DEFAULT_BASE_URL = "https://api.gexbot.com"


class GexbotApiError(RuntimeError):
    pass


@dataclass
class PollHandle:
    _stop_event: threading.Event
    _thread: threading.Thread | None

    @property
    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)


class GexbotClient:
    name = "gexbot"

    def __init__(self, session=None, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL):
        self._session = session
        self._api_key = api_key
        self._base_url = base_url

    def _get_session(self):
        if self._session is not None:
            return self._session
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "The 'requests' package is not installed (pip install 'prop-alpha-engine[gexbot]'), "
                "and no session= was injected for testing."
            ) from exc
        self._session = requests.Session()
        return self._session

    def _get(self, path: str, params: dict | None = None) -> dict:
        api_key = resolve_api_key(self._api_key)
        session = self._get_session()
        response = session.get(
            f"{self._base_url}{path}", params=params, headers={"Authorization": f"Bearer {api_key}"},
        )
        status = getattr(response, "status_code", 200)
        if status >= 400:
            raise GexbotApiError(f"GEXBOT API error {status} for {path}: {getattr(response, 'text', '')}")
        return response.json()

    def get_gex(self, underlying: str) -> dict:
        return self._get(f"/gex/{underlying}")

    def get_levels(self, underlying: str) -> dict:
        return self._get(f"/gex/{underlying}/levels")

    def get_orderflow(self, underlying: str) -> dict:
        return self._get(f"/gex/{underlying}/flow")

    def start_polling(
        self, underlying: str, interval_seconds: float, callback: Callable[[dict], None],
    ) -> PollHandle:
        stop_event = threading.Event()

        def _loop():
            while not stop_event.is_set():
                try:
                    callback(self.get_gex(underlying))
                except Exception:
                    pass  # one failed poll doesn't kill the loop; health.py surfaces the error rate
                stop_event.wait(interval_seconds)

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()
        return PollHandle(_stop_event=stop_event, _thread=thread)
