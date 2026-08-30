import pytest

from prop_alpha.data.live.subscription_manager import (
    DuplicateSubscriptionError,
    SubscriptionKey,
    SubscriptionManager,
)


def test_register_and_is_active():
    manager = SubscriptionManager()
    key = SubscriptionKey(provider="databento", instrument="NQ", schema="trades")
    manager.register(key, handle=object())
    assert manager.is_active(key)
    assert key in manager.active_keys()


def test_duplicate_registration_raises():
    manager = SubscriptionManager()
    key = SubscriptionKey(provider="databento", instrument="NQ", schema="trades")
    manager.register(key, handle=object())
    with pytest.raises(DuplicateSubscriptionError):
        manager.register(key, handle=object())


def test_unregister_allows_resubscription():
    manager = SubscriptionManager()
    key = SubscriptionKey(provider="databento", instrument="NQ", schema="trades")
    manager.register(key, handle=object())
    manager.unregister(key)
    assert not manager.is_active(key)
    manager.register(key, handle=object())  # must not raise
    assert manager.is_active(key)


def test_unregister_unknown_key_is_a_no_op():
    manager = SubscriptionManager()
    key = SubscriptionKey(provider="databento", instrument="NQ", schema="trades")
    manager.unregister(key)  # must not raise
    assert not manager.is_active(key)


def test_distinct_instruments_do_not_collide():
    manager = SubscriptionManager()
    key_nq = SubscriptionKey(provider="databento", instrument="NQ", schema="trades")
    key_es = SubscriptionKey(provider="databento", instrument="ES", schema="trades")
    manager.register(key_nq, handle=object())
    manager.register(key_es, handle=object())  # must not raise
    assert set(manager.active_keys()) == {key_nq, key_es}
