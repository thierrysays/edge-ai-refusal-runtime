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


def parse_iso(value: str) -> datetime:
    """Parse an RFC 3339 timestamp, accepting the ``Z`` suffix."""
    text = value.replace("Z", "+00:00")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {value!r}")
    return moment.astimezone(timezone.utc)
