"""In-process event dispatch (extension spec §126: prepare the
architecture for a future message broker without introducing one
prematurely — "La prima implementazione può essere locale/in-process").
Routes each recorded `LiveMessageEnvelope` to every handler registered for
its (provider, instrument, schema), or to a wildcard registered with any
field left `None`.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from prop_alpha.data.live.recorder import LiveMessageEnvelope

Handler = Callable[[LiveMessageEnvelope], None]


class EventRouter:
    def __init__(self):
        self._handlers: dict[tuple, list[Handler]] = defaultdict(list)

    def subscribe(
        self,
        handler: Handler,
        provider: str | None = None,
        instrument: str | None = None,
        schema: str | None = None,
    ) -> None:
        self._handlers[(provider, instrument, schema)].append(handler)

    def route(self, envelope: LiveMessageEnvelope) -> None:
        candidate_keys = [
            (envelope.provider, envelope.instrument, envelope.schema),
            (envelope.provider, envelope.instrument, None),
            (envelope.provider, None, None),
            (None, None, None),
        ]
        dispatched = set()
        for key in candidate_keys:
            for handler in self._handlers.get(key, []):
                if id(handler) in dispatched:
                    continue  # a handler registered under >1 matching key fires once per event
                dispatched.add(id(handler))
                handler(envelope)
