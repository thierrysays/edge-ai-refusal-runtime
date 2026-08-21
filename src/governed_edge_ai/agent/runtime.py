"""The governed runtime: the place where the controls are actually wired together.

Order matters, and it is not arbitrary:

1. **Stop channel first.** Nothing is evaluated while the cell is stopped. A
   system that reasons about a request it is not allowed to perform is a system
   that will eventually perform it.
2. **Policy second.** Default-deny; the decision is journalled whichever way it
   goes.
3. **Human oversight third**, and only for requests policy escalated. Escalating
   everything trains operators to approve everything, which is how oversight
   becomes a rubber stamp.
4. **Budget fourth.** Checked immediately before the effect, because a budget
   checked earlier can be overtaken by a concurrent spend.
5. **Actuation last**, through the hardware abstraction layer, whose own relay
   check is the final backstop.

Exhausting a budget engages the stop channel. That is a design choice worth
defending: an agent that has spent its allocation has demonstrated that its plan
and its allowance disagree, and the correct response to that disagreement is to
stop and involve a human, not to keep refusing individual requests while the
agent keeps trying.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..canonical import digest
from ..clock import Clock, SystemClock, iso
from ..errors import AdmissionDenied, BudgetExhausted
from ..journal import Journal
from ..marking import MarkedOutput, OutputMarker
from ..policy import ActuationRequest, BudgetLedger, Decision, PolicyEngine
from ..registry import RuntimeContext, TrustStore, admit
from ..registry.admission import AdmissionDecision
from ..oversight import Supervisor


@dataclass(frozen=True)
class ActionOutcome:
    """What happened to one actuation request, and why."""

    performed: bool
    effect: str
    request_digest: str
    reasons: tuple[str, ...]
    device_result: dict[str, Any] = field(default_factory=dict)
    journal_entry: str | None = None

    @property
    def refused(self) -> bool:
        return not self.performed


class GovernedRuntime:
    """Runs an admitted model against a device, under controls.

    The constructor does not admit anything. :meth:`open_session` does, and it
    raises if admission fails — there is no object state in which a model is
    loaded but ungoverned.
    """

    def __init__(
        self,
        *,
        envelope: dict[str, Any],
        trust_store: TrustStore,
        device: Any,
        journal: Journal,
        policy: PolicyEngine,
        budgets: BudgetLedger,
        supervisor: Supervisor,
        artifact_path: str | None = None,
        operator_id: str = "unattended",
        clock: Clock | None = None,
    ) -> None:
        self.envelope = envelope
        self.trust_store = trust_store
        self.device = device
        self.journal = journal
        self.policy = policy
        self.budgets = budgets
        self.supervisor = supervisor
        self.artifact_path = artifact_path
        self.operator_id = operator_id
        self.clock = clock or SystemClock()

        self.admission: AdmissionDecision | None = None
        self.marker: OutputMarker | None = None
        self._last_entry: str | None = None
        self.counters = {
            "inferences": 0,
            "requests": 0,
            "allowed": 0,
            "denied": 0,
            "escalated": 0,
            "escalations_approved": 0,
            "stops": 0,
        }

    # -------------------------------------------------------------------- session
    def open_session(self) -> AdmissionDecision:
        """Admit the model, or refuse to start."""
        profile = self.device.profile
        runtime_context = RuntimeContext(
            device_class=profile.device_class,
            available_controls=frozenset(profile.available_controls),
            operator_id=self.operator_id,
        )
        self.journal.append(
            "session_open",
            {
                "device": profile.to_record(),
                "policy": {"name": self.policy.name, "version": self.policy.version,
                           "rules": sorted(self.policy.rule_ids())},
                "budgets": self.budgets.to_record(),
                "supervisor": {
                    "confirmer": self.supervisor.confirmer.name,
                    "stop_channel": self.supervisor.stop_channel.status(),
                },
                "operator_id": self.operator_id,
                "opened_at": iso(self.clock.now()),
            },
        )

        decision = admit(
            self.envelope,
            self.trust_store,
            runtime_context,
            artifact_path=self.artifact_path,
            clock=self.clock,
        )
        self.journal.append("admission", decision.to_record())
        decision.raise_if_denied()

        card = self.envelope["card"]
        self.marker = OutputMarker(
            device_id=self.journal.device_id,
            model_id=card["model_id"],
            model_version=card["version"],
            card_digest=decision.card_digest or "",
            disclosure=card.get("transparency", {}).get("disclosure_text", ""),
            clock=self.clock,
        )
        self.admission = decision
        return decision

    def close_session(self) -> dict[str, Any]:
        record = {
            "closed_at": iso(self.clock.now()),
            "counters": dict(self.counters),
            "budgets": self.budgets.to_record(),
            "device_state": self.device.state(),
            "stop_channel": self.supervisor.stop_channel.status(),
        }
        self.journal.append("session_close", record)
        self.journal.checkpoint()
        return record

    # ------------------------------------------------------------------ inference
    def infer(self, observation: dict[str, Any], model: Any) -> MarkedOutput:
        """Run one inference, journal it, and mark the output."""
        if self.admission is None or self.marker is None:
            raise AdmissionDenied("no model has been admitted in this session")

        output = model.infer(observation)
        input_digest = digest(observation)
        marked = self.marker.mark(output, input_digest=input_digest)

        entry = self.journal.append(
            "inference",
            {
                "model_id": self.admission.model_id,
                "model_version": self.admission.version,
                "card_digest": self.admission.card_digest,
                "input_digest": input_digest,
                **marked.to_record(),
                # The payload is not journalled: digests are enough to prove what
                # happened, and a journal full of images is a journal nobody can
                # retain for the ten years the CRA expects of technical files.
                "summary": {
                    k: v for k, v in output.items() if k in ("defect", "confidence", "part")
                },
            },
        )
        self.counters["inferences"] += 1
        # The link runs journal → manifest, never both ways. A manifest that
        # embedded the hash of the entry that records the manifest's own digest
        # could not be computed, and an auditor who found one would be right to
        # distrust the whole file.
        self._last_entry = entry.hash
        return marked

    # ----------------------------------------------------------------- actuation
    def act(self, request: ActuationRequest) -> ActionOutcome:
        """Run one actuation request through every control, in order."""
        self.counters["requests"] += 1

        # 1 — stop channel
        if self.supervisor.stopped():
            return self._refuse(
                request,
                "deny",
                (f"stop channel engaged: "
                 f"{self.supervisor.stop_channel.status().get('reason') or 'stopped'}",),
                kind="stop",
            )

        # 2 — policy
        decision: Decision = self.policy.decide(request)
        self.journal.append(
            "policy_decision",
            {"request": request.to_dict(), **decision.to_record()},
        )
        if decision.effect == "deny":
            self.counters["denied"] += 1
            return ActionOutcome(
                performed=False,
                effect="deny",
                request_digest=request.digest,
                reasons=decision.reasons,
            )

        # 3 — human oversight
        if decision.needs_human:
            self.counters["escalated"] += 1
            record = self.supervisor.ask(request.to_dict(), decision.reasons)
            self.journal.append("oversight", record)
            if not record["approved"]:
                self.counters["denied"] += 1
                return ActionOutcome(
                    performed=False,
                    effect="require_human",
                    request_digest=request.digest,
                    reasons=decision.reasons
                    + (f"not approved by {record['operator_id']}",),
                )
            self.counters["escalations_approved"] += 1

        # 4 — budgets
        energy = self.device.profile.energy_model.get(request.action, 0.0)
        try:
            self.budgets.consume_many({"actions": 1, "energy_j": energy})
        except BudgetExhausted as exc:
            self.counters["denied"] += 1
            self.counters["stops"] += 1
            stop_record = self.supervisor.stop(str(exc))
            self.journal.append("stop", {**stop_record, "request": request.to_dict()})
            return ActionOutcome(
                performed=False,
                effect="deny",
                request_digest=request.digest,
                reasons=(str(exc), "stop channel engaged on budget exhaustion"),
            )

        # 5 — actuation
        result = self.device.perform(request.action, request.params)
        entry = self.journal.append(
            "actuation",
            {
                "request": request.to_dict(),
                "request_digest": request.digest,
                "result": result,
                "device_state": self.device.state(),
            },
        )
        if result.get("performed"):
            self.counters["allowed"] += 1
        else:
            self.counters["denied"] += 1
        return ActionOutcome(
            performed=bool(result.get("performed")),
            effect=decision.effect,
            request_digest=request.digest,
            reasons=decision.reasons
            if result.get("performed")
            else decision.reasons + (str(result.get("reason", "device refused")),),
            device_result=result,
            journal_entry=entry.hash,
        )

    # ---------------------------------------------------------------------- stop
    def stop(self, reason: str) -> ActionOutcome:
        """Engage the stop channel deliberately."""
        self.counters["stops"] += 1
        record = self.supervisor.stop(reason)
        self.device.relay.de_energise()
        entry = self.journal.append("stop", record)
        return ActionOutcome(
            performed=True,
            effect="deny",
            request_digest=digest({"stop": reason}),
            reasons=(reason,),
            journal_entry=entry.hash,
        )

    def resume(self, operator_id: str) -> dict[str, Any]:
        record = self.supervisor.resume(operator_id)
        self.device.relay.energise()
        self.journal.append("oversight", record)
        return record

    # -------------------------------------------------------------------- helpers
    def _refuse(
        self,
        request: ActuationRequest,
        effect: str,
        reasons: tuple[str, ...],
        *,
        kind: str,
    ) -> ActionOutcome:
        self.counters["denied"] += 1
        self.journal.append(
            kind,
            {"request": request.to_dict(), "effect": effect, "reasons": list(reasons)},
        )
        return ActionOutcome(
            performed=False,
            effect=effect,
            request_digest=request.digest,
            reasons=reasons,
        )

    # --------------------------------------------------------------------- report
    def report(self) -> dict[str, Any]:
        """A governance report, not an operations dashboard.

        The number that matters is ``denied``: prevented actions are the only
        direct evidence that a control is load-bearing.
        """
        return {
            "model": {
                "model_id": self.admission.model_id if self.admission else None,
                "version": self.admission.version if self.admission else None,
                "card_digest": self.admission.card_digest if self.admission else None,
                "obligations": list(self.admission.obligations) if self.admission else [],
            },
            "counters": dict(self.counters),
            "budgets": self.budgets.to_record(),
            "device_state": self.device.state(),
            "stop_channel": self.supervisor.stop_channel.status(),
            "journal": {
                "path": self.journal.path,
                "entries": self.journal.length,
                "head": self.journal.head,
            },
        }
