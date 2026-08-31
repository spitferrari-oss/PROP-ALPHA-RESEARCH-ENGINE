"""Options intelligence subsystem (extension spec §23 onward). Houses
provider-specific adapters (`options.gexbot`) and — in later extension
phases — the vendor-agnostic options snapshot model (Phase I, §28-29),
level engine (Phase K, §29), and cross-market synchronization with the
futures side (Phase J, §35-36). `providers.gexbot.GexbotOptionsProvider`
is the only thing the rest of PARE should import from this subsystem —
see that module's docstring.
"""
