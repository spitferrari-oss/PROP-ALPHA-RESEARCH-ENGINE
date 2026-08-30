"""Databento adapter (extension spec §3-4, primary futures data provider).

`historical.py` (`DatabentoHistoricalMixin`, extension §152 Phase B) and
`symbology.py` (instrument mapping) are implemented. `live.py`
(`subscribe_live`, Phase C) is not yet — `DatabentoHistoricalMixin` is a
plain mixin, not a `FuturesDataProvider` subclass, until Phase C's live
mixin exists to combine with it into a genuinely complete provider; see
`historical.py`'s module docstring.
"""
