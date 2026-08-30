"""Databento adapter (extension spec §3-4, primary futures data provider).

`historical.py` (`DatabentoHistoricalMixin`, Phase B), `live.py`
(`DatabentoLiveMixin`, Phase C), and `symbology.py` (instrument mapping)
are implemented; `DatabentoProvider` below combines the first two into the
first genuinely complete `FuturesDataProvider` this repo has.
"""
from __future__ import annotations

from prop_alpha.providers.base import FuturesDataProvider
from prop_alpha.providers.databento.historical import DatabentoHistoricalMixin
from prop_alpha.providers.databento.live import DatabentoLiveMixin


class DatabentoProvider(DatabentoHistoricalMixin, DatabentoLiveMixin, FuturesDataProvider):
    """The complete Databento `FuturesDataProvider`: `get_historical`/
    `get_instrument_definition`/`get_trading_calendar` from
    `DatabentoHistoricalMixin` (Phase B), `subscribe_live` from
    `DatabentoLiveMixin` (Phase C). `client`/`live_client` are separate
    injectable dependencies since Databento's historical and live clients
    are themselves distinct SDK objects; `api_key` is shared unless a
    dependency-injected client makes it unnecessary.
    """

    def __init__(
        self,
        client=None,
        live_client=None,
        api_key: str | None = None,
        recorder=None,
        subscription_manager=None,
        event_router=None,
    ):
        DatabentoHistoricalMixin.__init__(self, client=client, api_key=api_key)
        DatabentoLiveMixin.__init__(
            self,
            live_client=live_client,
            api_key=api_key,
            recorder=recorder,
            subscription_manager=subscription_manager,
            event_router=event_router,
        )
