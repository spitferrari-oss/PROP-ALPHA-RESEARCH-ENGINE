"""Live Data Engine (extension spec §12): connection lifecycle, duplicate-
subscription prevention, message recording, in-process event dispatch, and
health reporting — provider-agnostic, so `providers.databento.live` (and
any future vendor's live adapter) drives the same components instead of
reimplementing connection management per vendor.
"""
