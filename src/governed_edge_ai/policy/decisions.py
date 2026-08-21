"""Requests and decisions.

An actuation request is the unit of governance in this project. Nothing moves,
switches, or writes without one, and every request produces a decision that is
written to the journal whether it was allowed or refused.

Refusals are the interesting half. Most governance dashboards count what
happened; almost none count what was *prevented*, which is the only number that
tells you whether a control is load-bearing or decorative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..canonical import digest

#: Effects, weakest to strongest. Combination is by maximum: a single deny
#: overrides any number of allows (deny-overrides), and require_human overrides
#: allow. There is no "permit-overrides" mode and there will not be one.
EFFECTS = ("allow", "require_human", "deny")
_EFFECT_RANK = {effect: rank for rank, effect in enumerate(EFFECTS)}


def strongest(effects: list[str]) -> str:
    if not effects:
        return "deny"
    return max(effects, key=lambda e: _EFFECT_RANK[e])


@dataclass(frozen=True)
class ActuationRequest:
    """Something an agent wants the physical world to do."""

    action: str
    target: str
    params: dict[str, Any] = field(default_factory=dict)
    requester: str = "agent"
    model_id: str | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "params": self.params,
            "requester": self.requester,
            "model_id": self.model_id,
            "rationale": self.rationale,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_dict())

    def attribute(self, path: str) -> tuple[bool, Any]:
        """Resolve a dotted attribute path against the request.

        Returns ``(found, value)`` so that a rule can distinguish "absent" from
        "present and null" — a distinction that decides whether a default-deny
        rule fires.
        """
        if path in ("action", "target", "requester", "model_id", "rationale"):
            return True, getattr(self, path)
        if path.startswith("params."):
            cursor: Any = self.params
            for part in path.split(".")[1:]:
                if not isinstance(cursor, dict) or part not in cursor:
                    return False, None
                cursor = cursor[part]
            return True, cursor
        return False, None


@dataclass(frozen=True)
class Decision:
    """Why the request was allowed, refused, or escalated."""

    effect: str
    request_digest: str
    matched_rules: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    obligations: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"

    @property
    def needs_human(self) -> bool:
        return self.effect == "require_human"

    def to_record(self) -> dict[str, Any]:
        return {
            "effect": self.effect,
            "request_digest": self.request_digest,
            "matched_rules": list(self.matched_rules),
            "reasons": list(self.reasons),
            "obligations": list(self.obligations),
        }
