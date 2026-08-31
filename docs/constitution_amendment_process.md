# Research Constitution Amendment Process

The Research Constitution (`config/research_constitution.yaml`) is
machine-enforced: `src/prop_alpha/governance/constitution.py`'s
`assert_constitution_valid()` blocks `pae research full-run`, `pae
research discover`, and `pae research gex-templates` if the file doesn't
match its lock (`config/research_constitution.lock.yaml`). This means the
Constitution cannot be changed casually or silently — that is the point.

`config/research_constitution.yaml` itself declares this in its own
`constitution_control` block:

```yaml
constitution_control:
  self_amendment_allowed: false
  human_approval_required_for_changes: true
  hash_algorithm: SHA256
```

## What "self-amendment" means, and why it's forbidden

No agent, script, or automated process in this repository may edit
`config/research_constitution.yaml` and regenerate its own lock file as
part of routine operation. An agent (e.g. the Supervisor, or an LLM
session working in this repo) may **propose** an amendment — write up
what should change and why — but must not carry out the file edit,
hash regeneration, and lock update as a single unreviewed action. A
human must actually make (or explicitly approve, commit-by-commit) the
change.

## The required amendment steps, in order

1. **Deliberate human modification.** Edit `config/
   research_constitution.yaml` by hand (or with an agent's help, but with
   a human reviewing the diff before it's finalized) — never as an
   automatic side effect of running research.
2. **Version increment.** Bump `constitution.version` in the YAML.
   Semantic versioning is recommended (a wording clarification is a
   patch bump; adding/removing a hard gate or immutable principle is at
   least a minor bump; changing `constitution.id` or the meaning of an
   existing gate is a major bump) but the only thing the machinery
   actually checks is that the version string changed and that the lock
   file's `version` matches it.
3. **Regenerate the SHA256.** Run:

   ```bash
   pae constitution hash
   ```

   and copy the printed hash — this is exactly the value `governance.
   constitution.calculate_constitution_hash()` computes over the file's
   raw bytes.
4. **Regenerate the lock file.** Update `config/research_constitution.
   lock.yaml`'s `sha256`, `version`, and `locked_at` fields to match.
   `constitution_id` must also match `constitution.id` in the YAML file.
   Do this by hand or with a small script — there is deliberately no
   `pae constitution relock` command that does this in one step, because
   a one-command relock is exactly the kind of action that makes
   self-amendment easy to do by accident.
5. **Verify before committing.** Run:

   ```bash
   pae constitution verify
   ```

   and confirm `STATUS: CONSTITUTION VALID` before the change is
   committed. A commit that leaves the Constitution in an invalid state
   blocks every governance-gated research command for whoever pulls it
   next.
6. **Git commit.** Commit `research_constitution.yaml` and
   `research_constitution.lock.yaml` together, in the same commit, with a
   message that states what changed and why. Never commit one without
   the other.
7. **Audit record.** The next `pae research full-run` after the amendment
   will automatically capture the new `constitution_id`/`version`/`hash`
   in its `AuditEntry` (`agents/audit.py`) — there is no separate manual
   audit step required for this, but the amendment's own commit message
   is the durable record of *why* the change was made, since
   `AuditEntry` only records *which* Constitution a given experiment ran
   under, not the amendment's rationale.

## What agents may and may not do

- An agent (including an LLM session) **may**: read the Constitution,
  explain what it currently requires, propose specific wording/threshold
  changes with rationale, draft the diff for a human to review, and
  compute what the new hash *would* be for review purposes.
- An agent **may not**: commit a change to `research_constitution.yaml`
  and its lock file without a human in the loop reviewing that specific
  change, or present a self-authored amendment as already having taken
  effect before it's actually committed and verified.

## Testing a change without touching the real Constitution

Never modify `config/research_constitution.yaml` directly to test the
governance machinery. `tests/test_governance_constitution.py` demonstrates
the pattern: write a temporary constitution/lock pair under `tmp_path`,
verify the failure/success behavior against those files, and leave the
real files untouched. The hardening pass's own verification procedure
follows the same rule (see `reports/hardening_report.md`).
