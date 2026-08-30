"""Duplicate-stream prevention (extension spec §13: "Non deve creare
connessioni multiple accidentalmente"). Tracks active live subscriptions by
(provider, instrument, schema) so a provider adapter can never accidentally
open two connections for the same feed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubscriptionKey:
    provider: str
    instrument: str
    schema: str


class DuplicateSubscriptionError(RuntimeError):
    pass


class SubscriptionManager:
    def __init__(self):
        self._active: dict[SubscriptionKey, object] = {}

    def register(self, key: SubscriptionKey, handle: object) -> None:
        if key in self._active:
            raise DuplicateSubscriptionError(
                f"Already subscribed to {key} — close the existing handle before subscribing again."
            )
        self._active[key] = handle

    def unregister(self, key: SubscriptionKey) -> None:
        self._active.pop(key, None)

    def is_active(self, key: SubscriptionKey) -> bool:
        return key in self._active

    def active_keys(self) -> list[SubscriptionKey]:
        return list(self._active)
