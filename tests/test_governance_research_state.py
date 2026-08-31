import pytest
import yaml

from prop_alpha.governance.research_state import (
    RESEARCH_STATE_ORDER,
    TERMINAL_STATE,
    ResearchStateError,
    assert_valid_transition,
    validate_transition,
)


def test_state_order_matches_the_real_constitution_file():
    with open("config/research_constitution.yaml") as f:
        body = yaml.safe_load(f)["constitution"]
    constitution_states = body["research_states"]
    assert list(RESEARCH_STATE_ORDER) + [TERMINAL_STATE] == constitution_states


def test_one_step_forward_is_allowed():
    result = validate_transition("HYPOTHESIS", "BACKTESTED")
    assert result.allowed is True


def test_every_consecutive_pair_in_order_is_allowed():
    for old_state, new_state in zip(RESEARCH_STATE_ORDER, RESEARCH_STATE_ORDER[1:]):
        result = validate_transition(old_state, new_state)
        assert result.allowed is True, f"{old_state} -> {new_state} should be allowed"


def test_skipping_hypothesis_directly_to_live_is_forbidden():
    result = validate_transition("HYPOTHESIS", "LIVE")
    assert result.allowed is False
    assert "skips required intermediate gate" in result.reason


def test_skipping_research_to_live_short_form_is_forbidden():
    # "RESEARCH"-stage in the spec's language maps to BACKTESTED/OUT_OF_SAMPLE here
    result = validate_transition("BACKTESTED", "LIVE")
    assert result.allowed is False


def test_no_op_transition_is_allowed():
    result = validate_transition("WALK_FORWARD", "WALK_FORWARD")
    assert result.allowed is True


def test_backward_move_is_allowed():
    result = validate_transition("WALK_FORWARD", "BACKTESTED")
    assert result.allowed is True


def test_retire_is_always_allowed_from_non_terminal_state():
    for state in RESEARCH_STATE_ORDER:
        result = validate_transition(state, TERMINAL_STATE)
        assert result.allowed is True


def test_retired_is_terminal_no_transition_out():
    result = validate_transition(TERMINAL_STATE, "HYPOTHESIS")
    assert result.allowed is False
    assert "terminal" in result.reason


def test_unknown_state_names_are_rejected():
    result = validate_transition("HYPOTHESIS", "SUPER_LIVE")
    assert result.allowed is False
    assert "unknown" in result.reason


def test_assert_valid_transition_raises_on_illegal_move():
    with pytest.raises(ResearchStateError, match="skips required intermediate gate"):
        assert_valid_transition("HYPOTHESIS", "LIVE")


def test_assert_valid_transition_returns_check_on_legal_move():
    result = assert_valid_transition("HYPOTHESIS", "BACKTESTED")
    assert result.allowed is True
