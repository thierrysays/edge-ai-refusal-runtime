"""Budgets: the part of agent governance that policy rules cannot express.

A rule set answers "is this action permitted?". It cannot answer "is this the
four-hundredth permitted action in ninety seconds?", and unbounded repetition
of individually-legitimate actions is how an autonomous system does damage
without ever violating a rule.

Three properties are deliberate:

* **Fail-closed on unknown kinds.** Consuming a budget that was never declared
  is a refusal. Otherwise an agent invents a resource name and spends without
  limit.
* **Atomic check-then-consume.** A consumption that would exceed the limit
  changes nothing. Partial spends leave a ledger that does not reconcile.
* **Exhaustion is a stop, not a slowdown.** There is no throttling mode. A
  budget that degrades gracefully is a budget nobody notices they blew.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..clock import Clock, SystemClock, iso
from ..errors import BudgetExhausted, ConfigurationError


@dataclass
class BudgetLedger:
    """Named resource limits with a tumbling window.

    Args:
        limits: e.g. ``{"actions": 20, "energy_j": 500.0, "distance_m": 8.0}``.
        window_seconds: if set, all counters reset once the window elapses.
            Without it, the ledger covers the whole session.
    """

    limits: dict[str, float]
    window_seconds: float | None = None
    clock: Clock = field(default_factory=SystemClock)
    _spent: dict[str, float] = field(default_factory=dict, init=False)
    _window_start: Any = field(default=None, init=False)
    _renewals: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.limits:
            raise ConfigurationError("a ledger must declare at least one limit")
        for name, limit in self.limits.items():
            if not isinstance(limit, (int, float)) or isinstance(limit, bool):
                raise ConfigurationError(f"limit {name!r} must be numeric")
            if limit < 0:
                raise ConfigurationError(f"limit {name!r} must not be negative")
        self._spent = dict.fromkeys(self.limits, 0.0)
        self._window_start = self.clock.now()

    # ------------------------------------------------------------------ windows
    def _roll_window(self) -> None:
        if self.window_seconds is None:
            return
        elapsed = (self.clock.now() - self._window_start).total_seconds()
        if elapsed >= self.window_seconds:
            self._spent = dict.fromkeys(self.limits, 0.0)
            self._window_start = self.clock.now()
            self._renewals += 1

    # ------------------------------------------------------------------ queries
    def spent(self, kind: str) -> float:
        self._roll_window()
        return self._spent.get(kind, 0.0)

    def remaining(self, kind: str) -> float:
        self._roll_window()
        if kind not in self.limits:
            return 0.0
        return max(0.0, self.limits[kind] - self._spent[kind])

    def would_exceed(self, kind: str, amount: float) -> bool:
        self._roll_window()
        if kind not in self.limits:
            return True
        return self._spent[kind] + amount > self.limits[kind]

    # ------------------------------------------------------------------ mutation
    def consume(self, kind: str, amount: float) -> float:
        """Consume ``amount`` of ``kind``, or refuse and change nothing."""
        self._roll_window()
        if kind not in self.limits:
            raise BudgetExhausted(
                f"undeclared budget {kind!r}: an agent may only spend resources "
                f"that were allocated to it (declared: {sorted(self.limits)})"
            )
        if amount < 0:
            raise ConfigurationError("budget consumption must not be negative")
        projected = self._spent[kind] + amount
        if projected > self.limits[kind]:
            raise BudgetExhausted(
                f"budget {kind!r} exhausted: {self._spent[kind]:g} spent, "
                f"{amount:g} requested, limit {self.limits[kind]:g}"
            )
        self._spent[kind] = projected
        return self.limits[kind] - projected

    def consume_many(self, costs: dict[str, float]) -> None:
        """All-or-nothing consumption across several budgets."""
        self._roll_window()
        for kind, amount in costs.items():
            if kind not in self.limits:
                raise BudgetExhausted(f"undeclared budget {kind!r}")
            if self._spent[kind] + amount > self.limits[kind]:
                raise BudgetExhausted(
                    f"budget {kind!r} exhausted: {self._spent[kind]:g} spent, "
                    f"{amount:g} requested, limit {self.limits[kind]:g}"
                )
        for kind, amount in costs.items():
            self._spent[kind] += amount

    # -------------------------------------------------------------------- report
    def to_record(self) -> dict[str, Any]:
        self._roll_window()
        return {
            "limits": dict(self.limits),
            "spent": {k: round(v, 6) for k, v in self._spent.items()},
            "remaining": {k: round(self.remaining(k), 6) for k in self.limits},
            "window_seconds": self.window_seconds,
            "window_start": iso(self._window_start),
            "renewals": self._renewals,
        }
