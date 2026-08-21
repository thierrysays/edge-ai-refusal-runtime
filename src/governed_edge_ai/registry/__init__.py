"""Executable model registry: cards, signatures, and the admission gate."""

from .admission import AdmissionDecision, RuntimeContext, admit
from .schema import (
    KNOWN_CONTROLS,
    RISK_TIERS,
    SCHEMA_ID,
    effective_controls,
    required_quorum,
    validate_card,
)
from .signing import (
    SigningKey,
    TrustStore,
    VerifiedSignature,
    sign_card,
    verify_envelope,
)

__all__ = [
    "AdmissionDecision",
    "RuntimeContext",
    "admit",
    "KNOWN_CONTROLS",
    "RISK_TIERS",
    "SCHEMA_ID",
    "effective_controls",
    "required_quorum",
    "validate_card",
    "SigningKey",
    "TrustStore",
    "VerifiedSignature",
    "sign_card",
    "verify_envelope",
]
