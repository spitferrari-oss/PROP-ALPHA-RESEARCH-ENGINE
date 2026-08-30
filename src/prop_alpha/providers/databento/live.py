"""Databento live adapter (extension spec §152 Phase C): the live third of
`FuturesDataProvider` (`subscribe_live`), built on the provider-agnostic
Live Data Engine (`data/live/*`, extension §12-16) rather than
reimplementing connection management/recording per vendor.

Fully testable without network access or an API key (extension §134/§136):
`live_client` is dependency-injected exactly like
`DatabentoHistoricalMixin`'s historical `client` — any object exposing
`.subscribe(...)`/`.add_callback(...)`/`.start()`/`.stop()` works,
including a test fake. The real `databento` package's `Live` client is
imported lazily, only when no client is supplied. Its exact call shape
here (`subscribe`/`add_callback`/`start`/`stop`) follows
`databento-python`'s documented callback-based usage as best known at the
time this was written; verify it against the installed SDK version before
using this against a real Databento account — this repo has no network
access to check it live.
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd

from prop_alpha.data.live.buffer import BufferedMessage, MessageBuffer
from prop_alpha.data.live.connection_manager import BackoffPolicy, ConnectionManager, ConnectionState
from prop_alpha.data.live.event_router import EventRouter
from prop_alpha.data.live.recorder import LiveRecorder, build_envelope
from prop_alpha.data.live.subscription_manager import SubscriptionKey, SubscriptionManager
from prop_alpha.providers.base import DataLevel
from prop_alpha.providers.databento.symbology import DEFAULT_SCHEMA_BY_LEVEL, resolve

DATABENTO_API_KEY_ENV = "DATABENTO_API_KEY"


def _coerce_timestamp(value) -> dt.datetime | None:
    """Databento's live records expose `ts_event`/`ts_recv` either as
    nanosecond epoch ints (raw DBN) or already-decoded `datetime`s
    depending on SDK version/decoding options — accept either, and
    anything else is treated as absent rather than guessed at.
    """
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    if isinstance(value, (int, float)):
        return pd.Timestamp(int(value), unit="ns", tz="UTC").to_pydatetime()
    return None


class _DatabentoLiveConnectable:
    """Adapts a raw Databento live client into the `Connectable` protocol
    `ConnectionManager` drives, so the connection manager never needs to
    know it's specifically a Databento client.
    """

    def __init__(self, client):
        self._client = client

    def connect(self) -> None:
        self._client.start()

    def disconnect(self) -> None:
        self._client.stop()


class _DatabentoSubscriptionHandle:
    def __init__(
        self,
        connection: ConnectionManager,
        subscription_manager: SubscriptionManager,
        key: SubscriptionKey,
    ):
        self._connection = connection
        self._subscription_manager = subscription_manager
        self._key = key
        self._closed = False

    @property
    def is_active(self) -> bool:
        return not self._closed and self._connection.state == ConnectionState.CONNECTED

    def close(self) -> None:
        if self._closed:
            return
        self._connection.disconnect()
        self._subscription_manager.unregister(self._key)
        self._closed = True


class DatabentoLiveMixin:
    """Implements `FuturesDataProvider.subscribe_live`. `recorder=`/
    `subscription_manager=`/`event_router=` are injectable so a caller (or
    `DatabentoProvider`, once historical+live are combined) can share one
    instance across every subscription from the same adapter, or a test
    can inspect them directly.
    """

    name = "databento"

    def __init__(
        self,
        live_client=None,
        api_key: str | None = None,
        recorder: LiveRecorder | None = None,
        subscription_manager: SubscriptionManager | None = None,
        event_router: EventRouter | None = None,
    ):
        self._live_client = live_client
        self._live_api_key = api_key
        self._recorder = recorder or LiveRecorder()
        self._subscription_manager = subscription_manager or SubscriptionManager()
        self._event_router = event_router or EventRouter()

    def _get_live_client(self):
        if self._live_client is not None:
            return self._live_client
        try:
            import databento
        except ImportError as exc:
            raise RuntimeError(
                "The 'databento' package is not installed (pip install "
                "'prop-alpha-engine[databento]'), and no live_client= was injected for testing."
            ) from exc
        api_key = self._live_api_key or os.environ.get(DATABENTO_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"No Databento API key: pass api_key= or set the {DATABENTO_API_KEY_ENV} "
                "environment variable. Never hardcode it in config or code (extension §25/§98)."
            )
        self._live_client = databento.Live(key=api_key)
        return self._live_client

    def subscribe_live(self, instrument: str, level: DataLevel, on_message):
        mapping = resolve(instrument)
        schema = DEFAULT_SCHEMA_BY_LEVEL[level]
        key = SubscriptionKey(provider=self.name, instrument=instrument, schema=schema)
        if self._subscription_manager.is_active(key):
            raise RuntimeError(
                f"Already subscribed to {key} — close the existing handle before subscribing "
                "again (extension §13: no accidental duplicate connections)."
            )

        client = self._get_live_client()
        connection = ConnectionManager(_DatabentoLiveConnectable(client), backoff=BackoffPolicy())
        buffer = MessageBuffer()

        def _on_raw_message(raw: dict) -> None:
            received_at = dt.datetime.now(dt.timezone.utc)
            sequence = raw.get("sequence")
            envelope = build_envelope(
                provider=self.name,
                instrument=instrument,
                schema=schema,
                payload=raw,
                timestamp_exchange=_coerce_timestamp(raw.get("ts_event")),
                timestamp_provider=_coerce_timestamp(raw.get("ts_recv")),
                sequence=sequence,
                received_at=received_at,
            )
            buffer.append(BufferedMessage(received_at=received_at, sequence=sequence, payload=raw))
            connection.on_heartbeat()
            self._recorder.record(envelope)
            self._event_router.route(envelope)
            on_message(raw)

        client.subscribe(
            dataset=mapping.dataset, symbols=[mapping.raw_symbol], schema=schema, stype_in=mapping.stype_in,
        )
        client.add_callback(_on_raw_message)
        connection.connect()

        self._subscription_manager.register(key, connection)
        return _DatabentoSubscriptionHandle(connection, self._subscription_manager, key)
