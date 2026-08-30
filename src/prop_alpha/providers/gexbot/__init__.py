"""GEXBOT adapter (extension spec §3, §23-27, options data provider).

Empty on purpose: `client.py`/`auth.py`/`models.py`/`parser.py` implementing
`OptionsDataProvider` against GEXBOT's actual API are Phase H — see §152's
implementation order. `normalizer.py`/`collector.py`/`features.py`/
`levels.py`/`orderflow.py`/`health.py` follow in Phases I/K once the raw
adapter exists to normalize output from.
"""
