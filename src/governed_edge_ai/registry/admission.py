"""The admission gate.

One function decides whether a model may run on this device. It is the single
place where "the paperwork is in order" stops being a metaphor.

Design commitments:

* **Fail-closed.** Every unexpected condition is a refusal. There is no
  ``--force`` and no degraded mode that keeps the model running without its
  controls; a control that can be waived under operational pressure is a
  control that will be waived under operational pressure.
* **Decisions are data.** ``admit()`` returns an :class:`AdmissionDecision`
  rather than raising, so that refusals can be journalled and counted. Refusals
  you cannot count are refusals you cannot manage.
* **Reasons are plural.** All failed checks are reported, not just the first.
  An operator who has to re-run the gate five times to discover five problems
  will find a way around the gate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from ..canonical import digest, digest_file
from ..clock import Clock, SystemClock, iso, parse_iso
from ..errors import AdmissionDenied, ConfigurationError, SignatureInvalid
from .schema import KNOWN_CONTROLS, effective_controls, required_quorum, validate_card
from .signing import TrustStore, VerifiedSignature, verify_envelope


@dataclass(frozen=True)
class RuntimeContext:
    """What this particular device can actually enforce.

    ``available_controls`` is the honest inventory of the runtime, not an
    aspiration. If ``stop_channel`` is absent because no relay is wired, a
    high-risk card must not be admitted — which is exactly the situation the
    simulation backend is there to make visible before the hardware exists.
    """

    device_class: str
    available_controls: frozenset[str]
    operator_id: str = "unattended"

    def __post_init__(self) -> None:
        unknown = sorted(set(self.available_controls) - set(KNOWN_CONTROLS))
        if unknown:
            raise ConfigurationError(f"runtime declares unknown controls: {unknown}")

    @classmethod
    def of(
        cls, device_class: str, *controls: str, operator_id: str = "unattended"
    ) -> "RuntimeContext":
        return cls(
            device_class=device_class,
            available_controls=frozenset(controls),
            operator_id=operator_id,
        )


@dataclass(frozen=True)
class AdmissionDecision:
    """The gate's verdict, in a form that can be written to the journal."""

    admitted: bool
    model_id: str | None
    version: str | None
    card_digest: str | None
    device_class: str
    evaluated_at: str
    obligations: tuple[str, ...] = ()
    signers: tuple[tuple[str, str], ...] = ()   # (key_id, role)
    reasons: tuple[str, ...] = ()
    checks: tuple[tuple[str, bool], ...] = ()   # (check_name, passed)

    def to_record(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "model_id": self.model_id,
            "version": self.version,
            "card_digest": self.card_digest,
            "device_class": self.device_class,
            "evaluated_at": self.evaluated_at,
            "obligations": list(self.obligations),
            "signers": [{"key_id": k, "role": r} for k, r in self.signers],
            "reasons": list(self.reasons),
            "checks": [{"name": n, "passed": p} for n, p in self.checks],
        }

    def raise_if_denied(self) -> "AdmissionDecision":
        if not self.admitted:
            joined = "; ".join(self.reasons) or "no reason recorded"
            raise AdmissionDenied(
                f"model {self.model_id or '<unknown>'} refused: {joined}"
            )
        return self


class _Checklist:
    """Accumulates named checks so the decision carries its own audit trail."""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool]] = []
        self.reasons: list[str] = []

    def check(self, name: str, condition: bool, reason: str) -> bool:
        self.results.append((name, condition))
        if not condition:
            self.reasons.append(reason)
        return condition

    def fail(self, name: str, reason: str) -> None:
        self.results.append((name, False))
        self.reasons.append(reason)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok in self.results)


def admit(
    envelope: Any,
    trust_store: TrustStore,
    runtime: RuntimeContext,
    *,
    artifact_path: str | None = None,
    clock: Clock | None = None,
) -> AdmissionDecision:
    """Evaluate a signed model card against this runtime.

    Args:
        envelope: a signed card envelope (see :mod:`.signing`).
        trust_store: the closed set of acceptable signing keys.
        runtime: what this device can enforce.
        artifact_path: path to the model weights. If ``None``, the artefact
            binding check is *failed*, not skipped — a card whose artefact was
            never checked has not been checked.
        clock: injectable time source.

    Returns:
        An :class:`AdmissionDecision`. Never raises for a governance failure;
        raises only for programming errors.
    """
    clock = clock or SystemClock()
    now = clock.now()
    sheet = _Checklist()

    signers: list[VerifiedSignature] = []
    try:
        signers = verify_envelope(envelope, trust_store, now)
        sheet.check("signatures_verify", True, "")
    except SignatureInvalid as exc:
        sheet.fail("signatures_verify", str(exc))
    except ValueError as exc:  # malformed timestamps inside the envelope
        sheet.fail("signatures_verify", f"malformed signature metadata: {exc}")

    card = envelope.get("card") if isinstance(envelope, dict) else None
    if not isinstance(card, dict):
        sheet.fail("card_structure", "envelope does not contain a model card")
        return _decision(None, runtime, now, sheet, signers, ())

    try:
        validate_card(card)
        sheet.check("card_structure", True, "")
    except ConfigurationError as exc:
        sheet.fail("card_structure", f"invalid model card: {exc}")
        return _decision(card, runtime, now, sheet, signers, ())

    # --- quorum and separation of duties -------------------------------------
    quorum = required_quorum(card)
    roles = {s.role for s in signers}
    sheet.check(
        "signer_quorum",
        len(roles) >= quorum,
        f"risk tier {card['risk_tier']!r} requires {quorum} distinct signer role(s), "
        f"got {sorted(roles) or 'none'}",
    )
    if card["risk_tier"] == "high":
        sheet.check(
            "risk_officer_signature",
            "risk_officer" in roles,
            "a high-risk model card must be countersigned by a risk_officer",
        )

    # --- temporal validity ----------------------------------------------------
    valid_from = parse_iso(card["valid_from"])
    valid_until = parse_iso(card["valid_until"])
    sheet.check(
        "card_in_validity_window",
        valid_from <= now <= valid_until,
        f"card valid from {iso(valid_from)} to {iso(valid_until)}, now {iso(now)}",
    )

    # --- deployment target ----------------------------------------------------
    targets = card["deployment"]["targets"]
    sheet.check(
        "deployment_target",
        runtime.device_class in targets or "any" in targets,
        f"card authorises {targets}, this device is {runtime.device_class!r}",
    )

    # --- artefact binding -----------------------------------------------------
    if artifact_path is None:
        sheet.fail(
            "artifact_binding",
            "no artefact supplied: the card's artifact_digest could not be checked",
        )
    elif not os.path.exists(artifact_path):
        sheet.fail("artifact_binding", f"artefact not found at {artifact_path!r}")
    else:
        actual = digest_file(artifact_path)
        sheet.check(
            "artifact_binding",
            actual == card["artifact_digest"],
            f"artefact digest mismatch: card declares {card['artifact_digest']}, "
            f"file is {actual}",
        )

    # --- enforceable controls -------------------------------------------------
    obligations = effective_controls(card)
    missing = sorted(set(obligations) - set(runtime.available_controls))
    sheet.check(
        "controls_enforceable",
        not missing,
        f"runtime cannot enforce required control(s): {missing}",
    )

    return _decision(card, runtime, now, sheet, signers, obligations)


def _decision(
    card: dict[str, Any] | None,
    runtime: RuntimeContext,
    now: datetime,
    sheet: _Checklist,
    signers: Sequence[VerifiedSignature],
    obligations: tuple[str, ...],
) -> AdmissionDecision:
    return AdmissionDecision(
        admitted=sheet.passed,
        model_id=(card or {}).get("model_id"),
        version=(card or {}).get("version"),
        card_digest=digest(card) if card is not None else None,
        device_class=runtime.device_class,
        evaluated_at=iso(now),
        obligations=obligations if sheet.passed else (),
        signers=tuple((s.key_id, s.role) for s in signers),
        reasons=tuple(sheet.reasons),
        checks=tuple(sheet.results),
    )
