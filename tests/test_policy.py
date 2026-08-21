"""Policy engine and budget tests.

The property under test throughout is *default deny*. Almost every real policy
incident is not a wrong rule but a missing one, and a permit-by-default engine
turns every missing rule into a silent authorisation.
"""

from __future__ import annotations

import pytest

from governed_edge_ai.errors import BudgetExhausted, ConfigurationError
from governed_edge_ai.policy import ActuationRequest, BudgetLedger, PolicyEngine

BASE = {
    "schema": "governed-edge-ai/policy/v1",
    "name": "test-policy",
    "version": "1",
}


def engine(*rules) -> PolicyEngine:
    return PolicyEngine({**BASE, "rules": list(rules)})


def rule(rule_id, effect, when, because="a sufficiently explanatory reason", **extra):
    return {"id": rule_id, "effect": effect, "when": when, "because": because, **extra}


def request(**kwargs) -> ActuationRequest:
    defaults = {
        "action": "set_speed",
        "target": "cell",
        "params": {"speed": 0.3},
        "requester": "agent",
        "rationale": "because the shift started",
    }
    return ActuationRequest(**{**defaults, **kwargs})


# ---------------------------------------------------------------- default deny
def test_empty_match_is_deny():
    policy = engine(rule("allow-stop", "allow", {"action": "stop_conveyor"}))
    decision = policy.decide(request(action="launch_missiles"))
    assert decision.effect == "deny"
    assert "default deny" in decision.reasons[0]
    assert decision.matched_rules == ()


def test_deny_overrides_allow():
    policy = engine(
        rule("allow-speed", "allow", {"action": "set_speed"}),
        rule("deny-fast", "deny", {"params.speed": {"gt": 0.4}}),
    )
    assert policy.decide(request(params={"speed": 0.3})).effect == "allow"
    assert policy.decide(request(params={"speed": 0.9})).effect == "deny"


def test_require_human_overrides_allow_but_not_deny():
    policy = engine(
        rule("allow-speed", "allow", {"action": "set_speed"}),
        rule("escalate", "require_human", {"params.speed": {"gt": 0.2}}),
        rule("deny-fast", "deny", {"params.speed": {"gt": 0.5}}),
    )
    assert policy.decide(request(params={"speed": 0.1})).effect == "allow"
    assert policy.decide(request(params={"speed": 0.3})).effect == "require_human"
    assert policy.decide(request(params={"speed": 0.9})).effect == "deny"


def test_only_decisive_rules_are_cited():
    policy = engine(
        rule("allow-speed", "allow", {"action": "set_speed"}),
        rule("deny-fast", "deny", {"params.speed": {"gt": 0.4}}, because="too fast to inspect"),
    )
    decision = policy.decide(request(params={"speed": 0.9}))
    assert decision.matched_rules == ("deny-fast",)
    assert "too fast to inspect" in decision.reasons[0]


# ------------------------------------------------------------------- matching
def test_missing_attribute_does_not_match():
    """A rule on an attribute the request does not carry must not fire.

    This is what makes a typo in an attribute path safe: the rule simply never
    matches, and default-deny catches the request instead of a stale allow.
    """
    policy = engine(rule("allow", "allow", {"params.torque": {"lt": 10}}))
    assert policy.decide(request()).effect == "deny"


def test_exists_operator_reasons_about_absence():
    policy = engine(
        rule("allow", "allow", {"action": "set_speed", "params.speed": {"exists": True}}),
        rule("deny-missing", "deny", {"params.speed": {"exists": False}}),
    )
    assert policy.decide(request(params={"speed": 0.2})).effect == "allow"
    assert policy.decide(request(params={})).effect == "deny"


def test_type_mismatch_does_not_silently_compare():
    policy = engine(rule("allow", "allow", {"params.speed": {"lt": 1.0}}))
    assert policy.decide(request(params={"speed": "fast"})).effect == "deny"


def test_boolean_is_not_a_number():
    """``True < 1.0`` is true in Python. It must not be true in a policy."""
    policy = engine(rule("allow", "allow", {"params.speed": {"lt": 1.0}}))
    assert policy.decide(request(params={"speed": True})).effect == "deny"


def test_nested_parameter_paths():
    policy = engine(rule("allow", "allow", {"params.limits.max": {"lte": 5}}))
    assert policy.decide(request(params={"limits": {"max": 3}})).effect == "allow"
    assert policy.decide(request(params={"limits": {"max": 9}})).effect == "deny"


def test_not_in_and_matches_operators():
    policy = engine(
        rule("deny-foreign", "deny", {"target": {"not_in": ["cell"]}}),
        rule("allow-cell", "allow", {"target": "cell"}),
        rule("deny-blank-rationale", "deny", {"rationale": {"matches": r"\s*"}}),
    )
    assert policy.decide(request()).effect == "allow"
    assert policy.decide(request(target="paint-booth")).effect == "deny"
    assert policy.decide(request(rationale="   ")).effect == "deny"


def test_obligations_accumulate_across_matched_rules():
    policy = engine(
        rule("allow", "allow", {"action": "set_speed"}, obligations=["log_operator"]),
        rule("also", "allow", {"target": "cell"}, obligations=["notify_supervisor"]),
    )
    decision = policy.decide(request())
    assert decision.obligations == ("log_operator", "notify_supervisor")


# ----------------------------------------------------------- loading and rigour
@pytest.mark.parametrize(
    "bad, expected",
    [
        ({"rules": []}, "at least one rule"),
        ({"rules": [{"id": "x"}]}, "missing"),
        ({"rules": [rule("x", "maybe", {"action": "a"})]}, "effect must be"),
        ({"rules": [rule("x", "allow", {})]}, "non-empty object"),
        ({"rules": [rule("x", "allow", {"action": "a"}, because="short")]}, "explain"),
        ({"rules": [rule("x", "allow", {"action": {"weird": 1}})]}, "unknown operator"),
        (
            {"rules": [rule("x", "allow", {"action": "a"}), rule("x", "deny", {"action": "b"})]},
            "duplicate rule id",
        ),
    ],
)
def test_invalid_policies_fail_at_load(bad, expected):
    with pytest.raises(ConfigurationError) as excinfo:
        PolicyEngine({**BASE, **bad})
    assert expected in str(excinfo.value)


def test_wrong_schema_is_refused():
    with pytest.raises(ConfigurationError):
        PolicyEngine({"schema": "something/else", "rules": [rule("x", "allow", {"a": 1})]})


def test_shipped_inspection_policy_loads_and_is_default_deny():
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "policies", "inspection.json"
    )
    policy = PolicyEngine.from_file(path)
    assert len(policy.rules) >= 6
    unknown = ActuationRequest(
        action="open_gate", target="cell", rationale="it seemed useful"
    )
    assert policy.decide(unknown).effect == "deny"


# --------------------------------------------------------------------- budgets
def test_budget_consumes_and_reports(clock):
    ledger = BudgetLedger(limits={"actions": 3, "energy_j": 10.0}, clock=clock)
    ledger.consume("actions", 1)
    ledger.consume("energy_j", 4.5)
    assert ledger.spent("actions") == 1
    assert ledger.remaining("energy_j") == pytest.approx(5.5)


def test_budget_exhaustion_raises_and_changes_nothing(clock):
    ledger = BudgetLedger(limits={"actions": 2}, clock=clock)
    ledger.consume("actions", 2)
    with pytest.raises(BudgetExhausted):
        ledger.consume("actions", 1)
    assert ledger.spent("actions") == 2


def test_undeclared_budget_is_refused(clock):
    ledger = BudgetLedger(limits={"actions": 5}, clock=clock)
    with pytest.raises(BudgetExhausted) as excinfo:
        ledger.consume("tokens", 1)
    assert "undeclared budget" in str(excinfo.value)


def test_consume_many_is_all_or_nothing(clock):
    ledger = BudgetLedger(limits={"actions": 5, "energy_j": 1.0}, clock=clock)
    with pytest.raises(BudgetExhausted):
        ledger.consume_many({"actions": 1, "energy_j": 99.0})
    assert ledger.spent("actions") == 0
    assert ledger.spent("energy_j") == 0


def test_window_resets_the_ledger(clock):
    ledger = BudgetLedger(limits={"actions": 2}, window_seconds=60, clock=clock)
    ledger.consume("actions", 2)
    with pytest.raises(BudgetExhausted):
        ledger.consume("actions", 1)
    clock.advance(seconds=61)
    ledger.consume("actions", 1)
    assert ledger.to_record()["renewals"] == 1


def test_negative_limits_and_spends_are_configuration_errors(clock):
    with pytest.raises(ConfigurationError):
        BudgetLedger(limits={"actions": -1}, clock=clock)
    ledger = BudgetLedger(limits={"actions": 5}, clock=clock)
    with pytest.raises(ConfigurationError):
        ledger.consume("actions", -3)
