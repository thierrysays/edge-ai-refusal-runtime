"""Stop channels.

AI Act Article 14 requires that a high-risk system can be interrupted by a human
"through a stop button or a similar procedure". The clause is usually satisfied
on paper by an application-level flag — which is to say, by asking the software
that may be misbehaving to please stop misbehaving.

This module treats the stop channel as an independent subsystem with three
properties:

* **Fail-safe.** Loss of the heartbeat engages the stop. Silence means stop,
  not continue: a supervisor that has crashed must not thereby grant permission.
* **Independent.** ``HardwareStopChannel`` reads a physical input (a latch relay
  on a Modulino, in the target build) whose state does not depend on the process
  making the decisions.
* **Composable, disjunctively.** A composite channel is engaged if *any* member
  is engaged. Adding a channel can only ever make the system easier to stop.

Re-arming is deliberately asymmetric: engaging requires nothing, releasing
requires a named operator. Stopping must be cheaper than starting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..clock import Clock, SystemClock, iso
from ..errors import ConfigurationError


class StopChannel(Protocol):
    name: str

    def engaged(self) -> bool: ...          # pragma: no cover - protocol
    def engage(self, reason: str) -> None: ...   # pragma: no cover
    def release(self, operator_id: str) -> None: ...  # pragma: no cover
    def status(self) -> dict[str, Any]: ...  # pragma: no cover


@dataclass
class SoftwareStopChannel:
    """An in-process stop flag. The weakest channel; never the only one."""

    name: str = "software"
    _engaged: bool = field(default=False, init=False)
    _reason: str = field(default="", init=False)
    _released_by: str | None = field(default=None, init=False)

    def engaged(self) -> bool:
        return self._engaged

    def engage(self, reason: str) -> None:
        self._engaged = True
        self._reason = reason
        self._released_by = None

    def release(self, operator_id: str) -> None:
        if not operator_id or operator_id == "unattended":
            raise ConfigurationError(
                "a stop channel may only be released by a named operator"
            )
        self._engaged = False
        self._released_by = operator_id

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "engaged": self._engaged,
            "reason": self._reason,
            "released_by": self._released_by,
        }


@dataclass
class HeartbeatStopChannel:
    """Deadman switch: engaged unless recently fed.

    The default state is *engaged*. A system that has never proved a supervisor
    is watching has not earned the right to actuate.
    """

    timeout_seconds: float
    clock: Clock = field(default_factory=SystemClock)
    name: str = "heartbeat"
    _last_beat: Any = field(default=None, init=False)
    _forced: bool = field(default=False, init=False)
    _reason: str = field(default="no heartbeat received since start", init=False)

    def beat(self) -> None:
        self._last_beat = self.clock.now()

    def engaged(self) -> bool:
        if self._forced:
            return True
        if self._last_beat is None:
            return True
        elapsed = (self.clock.now() - self._last_beat).total_seconds()
        if elapsed > self.timeout_seconds:
            self._reason = (
                f"heartbeat stale: {elapsed:.1f}s since last beat, "
                f"timeout {self.timeout_seconds:.1f}s"
            )
            return True
        return False

    def engage(self, reason: str) -> None:
        self._forced = True
        self._reason = reason

    def release(self, operator_id: str) -> None:
        if not operator_id or operator_id == "unattended":
            raise ConfigurationError(
                "a stop channel may only be released by a named operator"
            )
        self._forced = False
        self.beat()

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "engaged": self.engaged(),
            "reason": self._reason if self.engaged() else "",
            "last_beat": iso(self._last_beat) if self._last_beat else None,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class HardwareStopChannel:
    """Reads a physical stop input through the hardware abstraction layer.

    On the target build this is a Modulino latch relay wired so that the
    de-energised state is *stopped*: a cut cable, a flat battery, or a crashed
    process all produce a stop rather than a run. In simulation the same
    contract is honoured by :class:`~governed_edge_ai.hal.sim.SimulatedRelay`.
    """

    relay: Any
    name: str = "hardware"
    _forced: bool = field(default=False, init=False)
    _reason: str = field(default="", init=False)

    def engaged(self) -> bool:
        # ``energised`` False == circuit open == stopped.
        return self._forced or not self.relay.energised()

    def engage(self, reason: str) -> None:
        self._forced = True
        self._reason = reason
        self.relay.de_energise()

    def release(self, operator_id: str) -> None:
        if not operator_id or operator_id == "unattended":
            raise ConfigurationError(
                "a stop channel may only be released by a named operator"
            )
        self._forced = False
        self._reason = ""
        self.relay.energise()

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "engaged": self.engaged(),
            "reason": self._reason,
            "relay_energised": self.relay.energised(),
        }


@dataclass
class CompositeStopChannel:
    """Engaged if any member channel is engaged."""

    channels: list[StopChannel]
    name: str = "composite"

    def __post_init__(self) -> None:
        if not self.channels:
            raise ConfigurationError(
                "a composite stop channel with no members would never stop anything"
            )

    def engaged(self) -> bool:
        return any(channel.engaged() for channel in self.channels)

    def engaged_channels(self) -> list[str]:
        return [c.name for c in self.channels if c.engaged()]

    def engage(self, reason: str) -> None:
        for channel in self.channels:
            channel.engage(reason)

    def release(self, operator_id: str) -> None:
        for channel in self.channels:
            channel.release(operator_id)

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "engaged": self.engaged(),
            "engaged_channels": self.engaged_channels(),
            "members": [c.status() for c in self.channels],
        }
