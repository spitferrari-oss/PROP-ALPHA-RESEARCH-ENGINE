"""GEXBOT adapter internals (extension spec §24, Phase H): the raw
client/auth/parsing/model/health layer where GEXBOT-specific knowledge
lives. `providers.gexbot.GexbotOptionsProvider` composes these — plus the
vendor-agnostic `options.normalize`/`options.levels` (Phase I) — into the
`OptionsDataProvider` interface (extension §2) the rest of PARE actually
depends on — nothing outside this package and `providers.gexbot` should
import `options.gexbot.*` directly.

The vendor-agnostic normalizer and Options Level Engine turned out to
belong one level up, at `options.normalize`/`options.levels`, not inside
this package — a snapshot model that's supposed to be the same shape
regardless of provider can't live inside one provider's own subpackage.
Still not built: `options/gexbot/features.py` (options feature engine,
Phase K, §31-34), `options/gexbot/orderflow.py` (options order flow
parsing, Phase K, §34), and `options/gexbot/collector.py` (a Phase
F-style scheduled recorder for options snapshots) — see extension §152's
phase order.
"""
