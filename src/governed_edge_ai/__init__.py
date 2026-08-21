"""governed-edge-ai — governance controls that either fire, or do not.

A small runtime that refuses to execute an AI model unless the model's card is
signed, current, bound to the artefact on disk, and enforceable by this device;
that records every inference in a tamper-evident journal; that mediates every
physical actuation through a policy engine with budgets; and that can be
stopped by a channel independent of the software making the decisions.

The thesis is that governance fails less from absent frameworks than from
absent instrumentation: a written control is unfalsifiable, a wired control
either fires or it does not.
"""

__version__ = "0.1.0"

from .canonical import canonical_bytes, digest, digest_bytes, digest_file
from .clock import FrozenClock, SystemClock, iso, parse_iso
from .errors import (
    AdmissionDenied,
    BudgetExhausted,
    ConfigurationError,
    GovernanceError,
    JournalIntegrityError,
    KillSwitchEngaged,
    OversightRequired,
    PolicyDenied,
    SignatureInvalid,
)

__all__ = [
    "__version__",
    "canonical_bytes",
    "digest",
    "digest_bytes",
    "digest_file",
    "FrozenClock",
    "SystemClock",
    "iso",
    "parse_iso",
    "AdmissionDenied",
    "BudgetExhausted",
    "ConfigurationError",
    "GovernanceError",
    "JournalIntegrityError",
    "KillSwitchEngaged",
    "OversightRequired",
    "PolicyDenied",
    "SignatureInvalid",
]
