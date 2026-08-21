"""Hardware abstraction layer.

The governance core must not know whether it is driving a conveyor, an Alvik, or
nothing at all. Two reasons, one engineering and one governance:

* *Engineering*: the controls can be written, tested, and broken deliberately
  before the boards arrive, which is how this repository was in fact built.
* *Governance*: a control whose correctness depends on the device it runs on
  cannot be certified once and deployed to a fleet. The device profile is data;
  the control logic is the same everywhere.

A profile declares what a device class can actually enforce. That declaration is
what the admission gate consults, and it is deliberately conservative: a class
that has no stop relay does not list ``stop_channel``, and therefore cannot run
a high-risk model, however much the card would like it to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Relay(Protocol):
    """A two-state actuator wired so that de-energised means stopped."""

    def energised(self) -> bool: ...        # pragma: no cover - protocol
    def energise(self) -> None: ...         # pragma: no cover
    def de_energise(self) -> None: ...      # pragma: no cover


@runtime_checkable
class Sensor(Protocol):
    name: str

    def read(self) -> dict[str, Any]: ...   # pragma: no cover - protocol


@dataclass(frozen=True)
class DeviceProfile:
    """What a device class is, and what it can enforce."""

    device_class: str
    description: str
    available_controls: frozenset[str]
    #: Cost model used by budgets, in joules per unit of action. Measured on the
    #: bench where possible; declared as an estimate where not. The distinction
    #: is recorded because a budget calibrated on a guess is a guess.
    energy_model: dict[str, float]
    energy_model_source: str = "estimate"

    def to_record(self) -> dict[str, Any]:
        return {
            "device_class": self.device_class,
            "description": self.description,
            "available_controls": sorted(self.available_controls),
            "energy_model": dict(self.energy_model),
            "energy_model_source": self.energy_model_source,
        }


class Device(Protocol):
    """The surface the governed runtime is allowed to touch."""

    profile: DeviceProfile
    relay: Relay

    def sensors(self) -> dict[str, Sensor]: ...          # pragma: no cover
    def perform(self, action: str, params: dict[str, Any]) -> dict[str, Any]: ...
    def state(self) -> dict[str, Any]: ...               # pragma: no cover


class NotPortedError(NotImplementedError):
    """Raised by hardware backends that are declared but not yet wired.

    Carrying a precise porting note in the exception is intentional: an
    unimplemented backend that fails with a bare ``NotImplementedError`` teaches
    the next person nothing, and this repository is meant to be picked up by
    someone holding the same boards.
    """

    def __init__(self, device_class: str, what: str, how: str) -> None:
        super().__init__(
            f"{device_class}: {what} is not ported yet.\n"
            f"To port it: {how}"
        )
        self.device_class = device_class
