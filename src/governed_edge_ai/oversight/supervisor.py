"""Human oversight, modelled as something that can be absent.

The default confirmer is :class:`AbsentOperator`, which refuses. This is the
single most consequential default in the codebase, so it is worth stating the
argument plainly: an escalation that nobody answers is a refusal, not a
permission. Systems that treat an unanswered escalation as approval are
performing oversight theatre, the escalation exists to produce a record, not a
decision.

The cost is real. A production line whose operator has stepped away stops. That
cost is the honest price of the Article 14 claim, and pricing it is part of what
this project is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..clock import Clock, SystemClock, iso
from .killswitch import StopChannel


class Confirmer(Protocol):
    """Supplies a human decision on an escalated request."""

    name: str

    def confirm(
        self, request_summary: dict[str, Any], reasons: tuple[str, ...]
    ) -> tuple[bool, str]:
        """Return ``(approved, operator_id)``."""
        ...  # pragma: no cover - protocol


@dataclass
class AbsentOperator:
    """No human is present. Every escalation is refused."""

    name: str = "absent"

    def confirm(
        self, request_summary: dict[str, Any], reasons: tuple[str, ...]
    ) -> tuple[bool, str]:
        return False, "unattended"


@dataclass
class CallbackConfirmer:
    """Delegates to a callable, a console prompt, an MQTT round trip, a button.

    On the target build this is the Modulino Buttons node: approval is a
    physical press, which cannot be produced by the model asking for it.
    """

    callback: Callable[[dict[str, Any], tuple[str, ...]], bool]
    operator_id: str
    name: str = "callback"

    def confirm(
        self, request_summary: dict[str, Any], reasons: tuple[str, ...]
    ) -> tuple[bool, str]:
        approved = bool(self.callback(request_summary, reasons))
        return approved, self.operator_id


@dataclass
class ScriptedConfirmer:
    """Deterministic confirmer for tests and replayable demonstrations."""

    answers: list[bool]
    operator_id: str = "operator-01"
    name: str = "scripted"
    _index: int = field(default=0, init=False)

    def confirm(
        self, request_summary: dict[str, Any], reasons: tuple[str, ...]
    ) -> tuple[bool, str]:
        if self._index >= len(self.answers):
            # Running out of scripted answers means the operator went away.
            return False, "unattended"
        answer = self.answers[self._index]
        self._index += 1
        return answer, self.operator_id


@dataclass
class Supervisor:
    """Binds the stop channel and the human confirmer into one oversight surface."""

    stop_channel: StopChannel
    confirmer: Confirmer = field(default_factory=AbsentOperator)
    clock: Clock = field(default_factory=SystemClock)

    def stopped(self) -> bool:
        return self.stop_channel.engaged()

    def stop(self, reason: str) -> dict[str, Any]:
        self.stop_channel.engage(reason)
        return {
            "event": "stop_engaged",
            "reason": reason,
            "at": iso(self.clock.now()),
            "status": self.stop_channel.status(),
        }

    def resume(self, operator_id: str) -> dict[str, Any]:
        self.stop_channel.release(operator_id)
        return {
            "event": "stop_released",
            "operator_id": operator_id,
            "at": iso(self.clock.now()),
            "status": self.stop_channel.status(),
        }

    def ask(
        self, request_summary: dict[str, Any], reasons: tuple[str, ...]
    ) -> dict[str, Any]:
        """Escalate to a human and return a journal-ready record."""
        approved, operator_id = self.confirmer.confirm(request_summary, reasons)
        return {
            "event": "oversight_decision",
            "approved": bool(approved),
            "operator_id": operator_id,
            "confirmer": self.confirmer.name,
            "asked_at": iso(self.clock.now()),
            "reasons": list(reasons),
            "request": request_summary,
        }
