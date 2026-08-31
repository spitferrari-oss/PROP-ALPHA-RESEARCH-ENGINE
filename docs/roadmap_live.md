# Roadmap to Live

This hardening pass ends at stage 1. Stages 2 and onward are separate,
later implementation work — none of it is started, and none of it should
be inferred as "mostly done" from anything built in this pass. Building
governance, honesty, and safe scaffolding around the existing pipeline
(stage 1) is a prerequisite for the stages that follow, not a shortcut
through them.

1. **Hardened offline engine** — *this hardening pass.* Machine-enforced
   Research Constitution, explicit no-trade gate, daily state machine,
   honest provider-capability reporting, execution kept structurally
   disabled, parameter sensitivity and leakage checking, deterministic
   test markers, reproducibility verified. Runs entirely offline on
   synthetic data. **Status after this pass: READY** (as an offline
   research/governance harness — see `reports/hardening_report.md` for
   the full breakdown).

2. **Historical real data** — real Databento historical bars actually
   ingested into the data lake (`pae data ingest`) and verified against
   the installed SDK's real call shape (`providers/databento/historical.py`'s
   own docstring flags this as unverified today — no network access in
   this environment has ever exercised it against a real account).
   **Status: NOT VERIFIED.**

3. **Historical futures research** — running the existing Discovery
   Engine / Alpha backtests against stage 2's real data instead of the
   synthetic demo dataset. The core pipeline (`pae research full-run`/
   `discover`) already works on any correctly-shaped OHLCV frame; nothing
   in it is synthetic-data-specific. **Status: NOT STARTED** (blocked on
   stage 2).

4. **Verified GEXBOT integration** — `pae options verify-provider`
   actually run against a real GEXBOT account, with `options/gexbot/
   parser.py`'s `_FIELD_ALIASES` corrected against the real response
   shape if they differ, and the provider's `ProviderContractState`
   genuinely reaching `LIVE_VERIFIED`. **Status: NOT VERIFIED** — the
   capability-reporting machinery this hardening pass built
   (`options/gexbot/capability.py`) exists and is tested, but has never
   been run against a real GEXBOT endpoint in this environment (no
   network access, no API key).

5. **Proprietary futures/options recording** — real, sustained use of
   `pae data record` (futures) and the options recorder
   (`options/recording/`, this hardening pass) against stages 2 and 4's
   live connections, building up PARE's own historical archive where the
   vendors' own history is unavailable or limited (GEXBOT has no
   historical endpoint at all, extension §62). **Status: NOT STARTED.**

6. **Historical replay with real data** — `pae replay run` (Phase N)
   already works against any correctly-shaped lake partition; this stage
   is running it against stage 5's real recordings instead of synthetic/
   mock ones. **Status: NOT STARTED** (blocked on stage 5; the replay
   engine itself is READY).

7. **Live market-data recording** — sustained, monitored real-time
   recording sessions (not a one-shot smoke test), with the Data Center
   (`pae data-center status`) actually showing `data_source=REAL` under
   real operating conditions over time, not just a single successful
   poll. **Status: NOT STARTED.**

8. **Live shadow** — `pae live-shadow start` (this hardening pass) run
   against a real, sustained live provider connection with a real alpha
   wired into `no_trade_state_builder`/`proposal_generator` (today's
   default wiring intentionally proposes nothing). **Status: NOT
   STARTED** — the architecture is `READY`; a real alpha and a real
   sustained connection are not.

9. **Live paper** — the Live/Paper Monitor (`paper/monitor.py`) actually
   evaluating stage 8's real live-shadow proposals over time (today it
   evaluates the OOS-replay shadow log, `paper/shadow.py`, which stays
   exactly as it is — see hardening report for why that's still correct
   and not something this pass should have touched).
   **Status: NOT STARTED.**

10. **Prop-specific execution adapter** — a real `execution.base.
    ExecutionGateway` implementation for an actual prop-firm/broker API,
    behind the same interface `execution/paper.py` already implements.
    **Explicitly out of scope for this hardening pass and the one before
    it.** **Status: NOT IMPLEMENTED.**

11. **Human approval live** — `LiveShadowMode.LIVE_HUMAN_APPROVAL`
    (already representable as a label in this hardening pass) wired to
    stage 10's real gateway, gated by an actual human `apply_feedback`
    decision before anything reaches the gateway. **Status: NOT
    IMPLEMENTED.**

12. **Semi-automatic** — a defined subset of trades auto-routed to
    stage 10's gateway (e.g. below a size/risk threshold) while others
    still require stage 11's human approval. **Status: NOT IMPLEMENTED.**

13. **Fully automatic** — `LiveShadowMode.LIVE_AUTO` (already
    representable as a label, and explicitly verified in this hardening
    pass's own tests to never cause any execution on its own) actually
    driving stage 10's gateway without human approval, only after every
    prior stage has been run for a meaningful track record.
    **Explicitly out of scope for the foreseeable future — this is the
    stage with the highest consequence of being wrong, and should not be
    reached without a separate, deliberate decision process outside of
    routine development work.**

## What this hardening pass deliberately did not do

- Connect to any real prop/broker account.
- Send, simulate-as-live, or otherwise route a real order.
- Verify the Databento or GEXBOT adapters against a real account (no
  network access in this environment; both remain `NOT_VERIFIED` by
  design — see `reports/hardening_baseline.md` and `reports/
  hardening_report.md`).
- Add a config toggle that could flip execution on — `execution.gateway.
  LIVE_EXECUTION_ENABLED` is a hardcoded constant, not a setting.

The next stage of work should start at stage 2 (real historical data)
and stage 4 (verified GEXBOT integration) — both require real network
access and real credentials this environment doesn't have, so neither
could be completed here regardless of how much code was written.
