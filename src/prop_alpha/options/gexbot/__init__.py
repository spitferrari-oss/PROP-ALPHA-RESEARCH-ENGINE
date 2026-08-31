"""GEXBOT adapter internals (extension spec §24, Phase H): the raw
client/auth/parsing/model/health layer where GEXBOT-specific knowledge
lives. `providers.gexbot.GexbotOptionsProvider` composes these into the
`OptionsDataProvider` interface (extension §2) the rest of PARE actually
depends on — nothing outside this package and `providers.gexbot` should
import `options.gexbot.*` directly.

`normalizer.py` (the vendor-agnostic options snapshot model, Phase I,
§28-29), `levels.py`/`features.py` (Options Level Engine / options feature
engine, Phase K, §29-34), `orderflow.py` (options order flow detail,
tied to whichever endpoint Phase K's research actually needs), and
`collector.py` (a Phase F-style scheduled recorder for options snapshots)
are not built yet — see extension §152's phase order.
"""
