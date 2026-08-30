from prop_alpha.agents.gates import Finding, Gate
from prop_alpha.agents.supervisor import FAIL_VERDICT, PASS_VERDICT, review


def test_all_pass_no_findings_gives_pass_verdict():
    gates = [Gate("A", "PASS", "ok"), Gate("B", "PASS", "ok"), Gate("C", "NOT_EVALUATED", "no engine")]
    verdict = review(gates, [])
    assert verdict.verdict == PASS_VERDICT
    assert verdict.blocking_reasons == []
    assert verdict.not_evaluated_gates == ["C"]


def test_any_failed_evaluated_gate_blocks():
    gates = [Gate("A", "PASS", "ok"), Gate("B", "FAIL", "bad"), Gate("C", "NOT_EVALUATED", "no engine")]
    verdict = review(gates, [])
    assert verdict.verdict == FAIL_VERDICT
    assert any("Gate B FAILED" in r for r in verdict.blocking_reasons)


def test_not_evaluated_gate_never_blocks_by_itself():
    gates = [Gate("A", "PASS", "ok"), Gate("B", "NOT_EVALUATED", "no engine")]
    verdict = review(gates, [])
    assert verdict.verdict == PASS_VERDICT


def test_high_severity_finding_blocks_even_with_all_gates_passing():
    gates = [Gate("A", "PASS", "ok")]
    findings = [Finding("HIDDEN_CORRELATION", "HIGH", "too correlated with baseline")]
    verdict = review(gates, findings)
    assert verdict.verdict == FAIL_VERDICT
    assert any("HIDDEN_CORRELATION" in r for r in verdict.blocking_reasons)


def test_low_and_medium_findings_do_not_block():
    gates = [Gate("A", "PASS", "ok")]
    findings = [Finding("LOW_SAMPLE", "MEDIUM", "thin sample"), Finding("X", "LOW", "minor")]
    verdict = review(gates, findings)
    assert verdict.verdict == PASS_VERDICT
    assert verdict.findings == findings  # still surfaced, just not blocking


def test_disclaimer_always_present_and_mentions_human_review():
    verdict = review([Gate("A", "PASS", "ok")], [])
    assert "human review" in verdict.disclaimer
    assert "real-money ready" in verdict.disclaimer
