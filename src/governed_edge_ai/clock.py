"""Injectable time.

Evidence that cannot be reproduced is not evidence. Every timestamp written to
the journal comes from a ``Clock``, so a test, or an auditor replaying a
scenario, can pin time and obtain byte-identical artefacts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:  # pragma: no cover - protocol definition
        ...


class SystemClock:
    """Wall clock, always timezone-aware UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    """Deterministic clock for tests and replay."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._now = start.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> datetime:
        """Advance the clock, e.g. ``advance(seconds=30)``."""
        self._now = self._now + timedelta(**kwargs)
        return self._now


def iso(moment: datetime) -> str:
    """RFC 3339 / ISO 8601 in UTC with a trailing ``Z``.

    Journal records are compared byte-for-byte across machines, so the string
    form is normalised here rather than at each call site.
    """
    if moment.tzinfo is None:
        raise ValueError("refusing to serialise a naive datetime")
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_iso(value: object) -> datetime:
    """Parse an RFC 3339 timestamp, accepting the ``Z`` suffix.

    The parameter is typed ``object`` rather than ``str`` on purpose. This
    function is reached from :func:`validate_card`, which parses a model card
    submitted by a provider, so the value has already crossed a trust boundary
    by the time it arrives. A mutation fuzzer found that a card carrying
    ``"valid_from": null`` raised ``AttributeError`` here rather than a stated
    refusal, which in the admission gate meant a stack trace where an operator
    needed a reason.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"timestamp must be a string, got {type(value).__name__}"
        )
    text = value.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"not an RFC 3339 timestamp: {value!r} ({exc})") from None
    if moment.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {value!r}")
    return moment.astimezone(timezone.utc)
