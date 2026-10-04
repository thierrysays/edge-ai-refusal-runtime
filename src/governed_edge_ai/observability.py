"""Optional crash telemetry: Sentry, wired at the tool's boundary only.

This module sits deliberately outside the control order in
``agent/runtime.py``. Sentry is never consulted by ``GovernedRuntime.act()``,
and its presence, absence, or failure changes nothing about what a request is
refused for: a governance decision that could be influenced by whether a
telemetry vendor is reachable would defeat the point of governance being
independently verifiable from the journal alone. A ``GovernanceError`` is
expected, evidence-bearing behaviour, already recorded in the journal, and is
never reported here as an error; only an exception that escapes the CLI
unhandled, a bug rather than a refusal, is.

Off unless ``SENTRY_DSN`` is set: this keeps the default install at the one
runtime dependency declared in ``pyproject.toml``. Add the ``observability``
extra (``pip install -e ".[observability]"``) to pull in ``sentry-sdk``; a
process without the extra, or without the environment variable, behaves
exactly as it did before this module existed. Every failure mode here -
missing SDK, malformed configuration, an unreachable collector - is swallowed
rather than raised, for the same reason: this is not a control, and it must
never be able to act like one, including by crashing the tool that carries
the controls.

What leaves the process is deliberately thin. `journal/` never writes a
payload, only its digest (invariant 7); this module holds itself to the same
rule for the one artefact it produces, stripping request bodies and stack
frame locals before anything is sent, since a frame can hold a model card, a
signing key, or an actuation request.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from .errors import GovernanceError

_ENABLED = False


def init_sentry(release: str | None = None) -> bool:
    """Initialise Sentry from the environment, or do nothing at all.

    Returns whether it actually initialised. Both silent cases - no DSN, and
    an SDK that is not installed - return ``False``, so a caller that only
    checks the environment variable cannot mistake "configured" for
    "reporting".
    """
    global _ENABLED
    _ENABLED = False

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        print(
            'SENTRY_DSN is set but sentry-sdk is not installed; install the '
            '"observability" extra to enable it. Continuing without it.',
            file=sys.stderr,
        )
        return False

    try:
        traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0"))
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
            release=os.environ.get("SENTRY_RELEASE", release),
            traces_sample_rate=traces_sample_rate,
            send_default_pii=False,
            include_local_variables=False,
            before_send=_scrub,
        )
    except Exception as exc:  # never let telemetry setup crash the tool
        print(f"sentry-sdk failed to initialise ({exc}); continuing without it.",
              file=sys.stderr)
        return False

    _ENABLED = True
    return True


def _scrub(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Strip everything but the shape of the crash before it is sent.

    Defence in depth alongside ``include_local_variables=False``: this runs
    even if a future SDK version changes what it collects by default.
    """
    event.pop("request", None)
    event["extra"] = {}
    for exc in event.get("exception", {}).get("values", []):
        for frame in exc.get("stacktrace", {}).get("frames", []):
            frame.pop("vars", None)
    return event


def report_crash(exc: BaseException) -> None:
    """Report an unexpected exception, never a governance refusal.

    A no-op whenever Sentry was never enabled, and swallows any failure of
    its own: reporting a crash must never itself be a second crash.
    """
    if not _ENABLED or isinstance(exc, GovernanceError):
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception as report_exc:  # reporting a crash must never cause a second one
        print(f"sentry-sdk failed to report a crash ({report_exc}); continuing.",
              file=sys.stderr)
