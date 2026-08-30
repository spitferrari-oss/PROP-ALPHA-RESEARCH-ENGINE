import datetime as dt

from prop_alpha.data.live.event_router import EventRouter
from prop_alpha.data.live.recorder import build_envelope


def _envelope(provider="databento", instrument="NQ", schema="trades"):
    return build_envelope(
        provider=provider, instrument=instrument, schema=schema, payload={},
        received_at=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
    )


def test_exact_key_handler_receives_matching_event():
    router = EventRouter()
    received = []
    router.subscribe(received.append, provider="databento", instrument="NQ", schema="trades")
    router.route(_envelope())
    assert len(received) == 1


def test_exact_key_handler_does_not_receive_other_instruments():
    router = EventRouter()
    received = []
    router.subscribe(received.append, provider="databento", instrument="NQ", schema="trades")
    router.route(_envelope(instrument="ES"))
    assert received == []


def test_instrument_wildcard_receives_any_schema():
    router = EventRouter()
    received = []
    router.subscribe(received.append, provider="databento", instrument="NQ")
    router.route(_envelope(schema="trades"))
    router.route(_envelope(schema="mbp-10"))
    assert len(received) == 2


def test_global_wildcard_receives_everything():
    router = EventRouter()
    received = []
    router.subscribe(received.append)
    router.route(_envelope(instrument="NQ"))
    router.route(_envelope(instrument="ES", schema="mbo"))
    assert len(received) == 2


def test_handler_registered_under_multiple_matching_keys_fires_once():
    router = EventRouter()
    received = []

    def handler(envelope):
        received.append(envelope)

    router.subscribe(handler, provider="databento", instrument="NQ", schema="trades")
    router.subscribe(handler, provider="databento", instrument="NQ")
    router.subscribe(handler)
    router.route(_envelope())
    assert len(received) == 1
