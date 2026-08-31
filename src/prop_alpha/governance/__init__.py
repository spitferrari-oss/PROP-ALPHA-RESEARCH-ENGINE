"""Machine-enforced governance for PARE (hardening pass Blocker A).

`constitution.py` is the control system: it loads the Research
Constitution (`config/research_constitution.yaml`), verifies it against
its lock file (`config/research_constitution.lock.yaml`), and exposes
`assert_constitution_valid()` as the single hard gate every research
command must pass before doing meaningful work. This does not replace or
duplicate the existing statistical/risk gates in `agents/` (Statistician/
Critic/Risk/Supervisor) or `discovery/hypothesis.py`'s Hypothesis Ledger —
it sits above them: those modules decide whether a *specific alpha* is
good enough; this module decides whether the *governance system itself*
is intact before any of that work is trusted.
"""
