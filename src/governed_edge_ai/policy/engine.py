"""A small, total, default-deny policy engine.

Rules are data, not code. That is a governance requirement rather than an
architectural preference: a rule expressed as a Python callable cannot be
diffed by a risk officer, versioned in a change record, or shown to an auditor
as the thing that was actually in force on a given date.

Evaluation semantics, in full — they are short on purpose:

1. Every rule whose ``when`` clause matches the request contributes its effect.
2. The decision is the **strongest** contributed effect (``deny`` >
   ``require_human`` > ``allow``).
3. If no rule matches, the decision is **deny**. Silence is refusal.
4. Evaluation is total: an unparseable rule is a configuration error at load
   time, never a runtime surprise that quietly evaluates to false.

Point 3 is the one people argue about. The counter-argument is operational —
default-deny means every new action must be authorised before it can run, which
is friction. That friction is the product, not a side effect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from ..errors import ConfigurationError
from .decisions import EFFECTS, ActuationRequest, Decision, strongest

POLICY_SCHEMA = "governed-edge-ai/policy/v1"

_OPERATORS = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "matches", "exists")


def _compare(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "eq":
        return bool(actual == expected)
    if operator == "ne":
        return bool(actual != expected)
    if operator in ("gt", "gte", "lt", "lte"):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            return False
        return {
            "gt": actual > expected,
            "gte": actual >= expected,
            "lt": actual < expected,
            "lte": actual <= expected,
        }[operator]
    if operator == "in":
        return isinstance(expected, list) and actual in expected
    if operator == "not_in":
        return isinstance(expected, list) and actual not in expected
    if operator == "matches":
        return isinstance(actual, str) and re.fullmatch(str(expected), actual) is not None
    if operator == "exists":
        return bool(expected)
    raise ConfigurationError(f"unknown operator: {operator!r}")


@dataclass(frozen=True)
class Rule:
    id: str
    effect: str
    when: dict[str, Any]
    because: str
    obligations: tuple[str, ...] = ()

    def matches(self, request: ActuationRequest) -> bool:
        """All conditions must hold (conjunction). Absent attribute → no match.

        The exception is the ``exists`` operator, which is the only way to write
        a condition *about* absence — otherwise a typo in an attribute path would
        silently produce a rule that never fires, which is the most dangerous
        failure mode a policy language can have.
        """
        for path, condition in self.when.items():
            found, value = request.attribute(path)
            if isinstance(condition, dict):
                for operator, expected in condition.items():
                    if operator == "exists":
                        if _compare("exists", None, expected) != found:
                            return False
                        continue
                    if not found or not _compare(operator, value, expected):
                        return False
            else:
                if not found or value != condition:
                    return False
        return True


class PolicyEngine:
    """Holds a rule set and evaluates requests against it."""

    def __init__(self, document: dict[str, Any]) -> None:
        if document.get("schema") != POLICY_SCHEMA:
            raise ConfigurationError(f"policy schema must be {POLICY_SCHEMA!r}")
        raw_rules = document.get("rules")
        if not isinstance(raw_rules, list) or not raw_rules:
            raise ConfigurationError("a policy must contain at least one rule")

        self.name: str = document.get("name", "unnamed-policy")
        self.version: str = document.get("version", "0")
        self.rules: list[Rule] = [self._parse_rule(r) for r in raw_rules]

        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ConfigurationError(f"duplicate rule id: {rule.id!r}")
            seen.add(rule.id)

    @staticmethod
    def _parse_rule(raw: Any) -> Rule:
        if not isinstance(raw, dict):
            raise ConfigurationError("a rule must be an object")
        for field in ("id", "effect", "when", "because"):
            if field not in raw:
                raise ConfigurationError(f"rule missing {field!r}")
        if raw["effect"] not in EFFECTS:
            raise ConfigurationError(
                f"rule {raw['id']!r}: effect must be one of {EFFECTS}"
            )
        if not isinstance(raw["when"], dict) or not raw["when"]:
            raise ConfigurationError(
                f"rule {raw['id']!r}: 'when' must be a non-empty object. "
                "A rule that matches everything must say so explicitly."
            )
        if not isinstance(raw["because"], str) or len(raw["because"].strip()) < 8:
            raise ConfigurationError(
                f"rule {raw['id']!r}: 'because' must explain the rule to a human. "
                "An unexplained refusal gets overridden."
            )
        # Validate operators eagerly: a typo must fail at load, not at 3 a.m.
        for path, condition in raw["when"].items():
            if not isinstance(path, str) or not path:
                raise ConfigurationError(f"rule {raw['id']!r}: invalid attribute path")
            if isinstance(condition, dict):
                for operator in condition:
                    if operator not in _OPERATORS:
                        raise ConfigurationError(
                            f"rule {raw['id']!r}: unknown operator {operator!r}; "
                            f"expected one of {_OPERATORS}"
                        )
        obligations = raw.get("obligations", [])
        if not isinstance(obligations, list) or not all(
            isinstance(o, str) for o in obligations
        ):
            raise ConfigurationError(f"rule {raw['id']!r}: obligations must be strings")

        return Rule(
            id=raw["id"],
            effect=raw["effect"],
            when=raw["when"],
            because=raw["because"],
            obligations=tuple(obligations),
        )

    # ------------------------------------------------------------------ evaluate
    def decide(self, request: ActuationRequest) -> Decision:
        matched = [rule for rule in self.rules if rule.matches(request)]
        if not matched:
            return Decision(
                effect="deny",
                request_digest=request.digest,
                reasons=(
                    f"default deny: no rule in policy {self.name!r} v{self.version} "
                    f"authorises action {request.action!r} on target {request.target!r}",
                ),
            )
        effect = strongest([rule.effect for rule in matched])
        # Only the rules that produced the winning effect are cited: an operator
        # reading "denied because X, allowed because Y" learns nothing.
        decisive = [rule for rule in matched if rule.effect == effect]
        obligations: list[str] = []
        for rule in matched:
            for obligation in rule.obligations:
                if obligation not in obligations:
                    obligations.append(obligation)
        return Decision(
            effect=effect,
            request_digest=request.digest,
            matched_rules=tuple(rule.id for rule in decisive),
            reasons=tuple(f"{rule.id}: {rule.because}" for rule in decisive),
            obligations=tuple(sorted(obligations)),
        )

    # -------------------------------------------------------------------- import
    @classmethod
    def from_file(cls, path: str) -> "PolicyEngine":
        import json

        with open(path, "r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def rule_ids(self) -> Iterable[str]:
        return (rule.id for rule in self.rules)
