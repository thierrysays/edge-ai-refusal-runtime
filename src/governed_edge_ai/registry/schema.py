"""Model card schema.

The card is the executable form of what the AI Act calls technical
documentation (Annex IV) and what ISO/IEC 42001 calls the AI system record.
The point of this project is that the card is not a Word file filed after the
fact: it is the object the runtime consults before it agrees to load anything.

Validation here is intentionally hand-written rather than delegated to a
schema library. On a constrained target (UNO Q, 4 GB, Debian) dependency
weight is a governance property in its own right: every transitive dependency
is a line in the SBOM you will later have to defend under the CRA.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..canonical import is_digest
from ..clock import parse_iso
from ..errors import ConfigurationError

SCHEMA_ID = "governed-edge-ai/model-card/v1"

RISK_TIERS = ("minimal", "limited", "high")

#: Controls this runtime knows how to enforce. A card may not demand a control
#: the runtime cannot provide, that combination fails closed rather than
#: silently degrading, which is the usual way paper controls become fiction.
KNOWN_CONTROLS = (
    "inference_journal",
    "policy_mediation",
    "stop_channel",
    "output_marking",
    "human_confirmation",
)

#: Minimum controls implied by a risk tier, regardless of what the card asks
#: for. A provider cannot opt out of these by omission.
TIER_BASELINE: dict[str, tuple[str, ...]] = {
    "minimal": (),
    "limited": ("output_marking",),
    "high": (
        "inference_journal",
        "policy_mediation",
        "stop_channel",
        "output_marking",
    ),
}

#: Number of distinct signer roles required to admit a model of each tier.
#: Two for high risk: separation of duties between the party that builds the
#: model and the party accountable for the risk (COBIT EDM/ISO 27001 A.5.3).
TIER_QUORUM: dict[str, int] = {"minimal": 1, "limited": 1, "high": 2}

_REQUIRED_TOP_LEVEL = (
    "schema",
    "model_id",
    "version",
    "artifact_digest",
    "risk_tier",
    "intended_purpose",
    "provider",
    "deployment",
    "oversight",
    "transparency",
    "valid_from",
    "valid_until",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigurationError(message)


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_card(card: Any) -> dict[str, Any]:
    """Structurally validate a model card, returning it unchanged.

    Raises:
        ConfigurationError: with a message naming the offending field. The
            message is surfaced verbatim in the admission decision, because an
            operator who cannot tell *why* a model was refused will disable the
            gate.
    """
    _require(isinstance(card, dict), "model card must be a JSON object")

    for field in _REQUIRED_TOP_LEVEL:
        _require(field in card, f"missing required field: {field}")

    _require(card["schema"] == SCHEMA_ID, f"unsupported schema: {card['schema']!r}")
    _require(
        isinstance(card["model_id"], str) and card["model_id"].strip() != "",
        "model_id must be a non-empty string",
    )
    _require(
        isinstance(card["version"], str) and card["version"].strip() != "",
        "version must be a non-empty string",
    )
    _require(
        is_digest(card["artifact_digest"]),
        "artifact_digest must be a sha256:<hex> digest",
    )
    _require(
        card["risk_tier"] in RISK_TIERS,
        f"risk_tier must be one of {RISK_TIERS}, got {card['risk_tier']!r}",
    )
    _require(
        isinstance(card["intended_purpose"], str)
        and len(card["intended_purpose"].strip()) >= 16,
        "intended_purpose must be a substantive description (>= 16 characters)",
    )

    provider = card["provider"]
    _require(isinstance(provider, dict), "provider must be an object")
    for field in ("name", "contact"):
        _require(
            isinstance(provider.get(field), str) and provider[field].strip() != "",
            f"provider.{field} is required",
        )

    deployment = card["deployment"]
    _require(isinstance(deployment, dict), "deployment must be an object")
    _require(
        _is_str_list(deployment.get("targets")) and deployment["targets"],
        "deployment.targets must be a non-empty list of device classes",
    )

    oversight = card["oversight"]
    _require(isinstance(oversight, dict), "oversight must be an object")
    _require(
        isinstance(oversight.get("human_in_the_loop"), bool),
        "oversight.human_in_the_loop must be a boolean",
    )

    transparency = card["transparency"]
    _require(isinstance(transparency, dict), "transparency must be an object")
    _require(
        isinstance(transparency.get("marks_synthetic_output"), bool),
        "transparency.marks_synthetic_output must be a boolean",
    )

    controls = card.get("controls_required", [])
    _require(_is_str_list(controls), "controls_required must be a list of strings")
    unknown = sorted(set(controls) - set(KNOWN_CONTROLS))
    _require(not unknown, f"unknown controls requested: {unknown}")

    for field in ("valid_from", "valid_until"):
        try:
            parse_iso(card[field])
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{field}: {exc}") from exc
    _require(
        parse_iso(card["valid_from"]) < parse_iso(card["valid_until"]),
        "valid_from must precede valid_until",
    )

    # An out-of-scope list is not decoration. Article 14 oversight is only
    # actionable if the operator has been told what the model is *not* for.
    out_of_scope = card.get("out_of_scope_uses", [])
    _require(_is_str_list(out_of_scope), "out_of_scope_uses must be a list of strings")
    if card["risk_tier"] == "high":
        _require(
            len(out_of_scope) >= 1,
            "a high-risk card must declare at least one out-of-scope use",
        )

    return dict(card)


def effective_controls(card: dict[str, Any]) -> tuple[str, ...]:
    """Controls that must be active for this card: baseline ∪ requested.

    The union, never the intersection. A card that asks for fewer controls than
    its tier baseline does not thereby obtain fewer controls.
    """
    requested: Iterable[str] = card.get("controls_required", [])
    baseline = TIER_BASELINE[card["risk_tier"]]
    merged = set(baseline) | set(requested)
    if card.get("transparency", {}).get("marks_synthetic_output"):
        merged.add("output_marking")
    if card.get("oversight", {}).get("human_in_the_loop"):
        merged.add("human_confirmation")
    return tuple(sorted(merged))


def required_quorum(card: dict[str, Any]) -> int:
    """Number of distinct signer roles required to admit this card."""
    return TIER_QUORUM[card["risk_tier"]]
