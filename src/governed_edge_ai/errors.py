"""Governance failure modes.

Deliberately fine-grained. A control that fails with a generic exception is a
control you cannot report on: incident notification under NIS2 Article 23 and
serious-incident reporting under the AI Act both require you to say *which*
control failed, not merely that something went wrong.
"""

from __future__ import annotations


class GovernanceError(Exception):
    """Base class. Every refusal in this codebase derives from it."""

    #: Stable machine-readable code, used in journal records and reports.
    code = "governance_error"


class AdmissionDenied(GovernanceError):
    """A model was refused at the admission gate. Fail-closed by design."""

    code = "admission_denied"


class SignatureInvalid(GovernanceError):
    """A signature did not verify against any trusted key."""

    code = "signature_invalid"


class JournalIntegrityError(GovernanceError):
    """The hash chain is broken, truncated, or reordered."""

    code = "journal_integrity_error"


class PolicyDenied(GovernanceError):
    """The policy engine refused an actuation request."""

    code = "policy_denied"


class BudgetExhausted(PolicyDenied):
    """An agent exceeded an allocated budget (actions, energy, or wall clock)."""

    code = "budget_exhausted"


class OversightRequired(GovernanceError):
    """The request is admissible only with a human decision that was not given."""

    code = "oversight_required"


class KillSwitchEngaged(GovernanceError):
    """Actuation attempted while the stop channel was engaged."""

    code = "kill_switch_engaged"


class ConfigurationError(GovernanceError):
    """The governance configuration itself is invalid — also a fail-closed case."""

    code = "configuration_error"
