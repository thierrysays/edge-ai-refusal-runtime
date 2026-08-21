"""Simulated inspection cell.

A conveyor carries parts past a camera. A model classifies each part. Defective
parts must be diverted; a run of defects means something upstream is wrong and
the line should stop. Every physical effect is a state change here, so tests can
assert on the world rather than on log lines.

The simulation is deterministic: parts come from a seeded sequence, so a demo
run produces byte-identical journals on any machine. Determinism is what makes
the journal reviewable by someone who was not there.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .base import DeviceProfile, NotPortedError

SIM_PROFILE = DeviceProfile(
    device_class="sim",
    description="Simulated weld-inspection cell: conveyor, camera, diverter, stop relay.",
    available_controls=frozenset(
        {
            "inference_journal",
            "policy_mediation",
            "stop_channel",
            "output_marking",
            "human_confirmation",
        }
    ),
    energy_model={
        "set_speed": 0.5,
        "divert_part": 2.0,
        "stop_conveyor": 0.2,
        "resume_conveyor": 1.0,
        "inference": 0.35,
    },
    energy_model_source="synthetic (simulation only — not measured)",
)


@dataclass
class SimulatedRelay:
    """Latch relay stand-in. Starts de-energised: the cell starts stopped."""

    _energised: bool = field(default=False, init=False)
    switch_count: int = field(default=0, init=False)

    def energised(self) -> bool:
        return self._energised

    def energise(self) -> None:
        if not self._energised:
            self.switch_count += 1
        self._energised = True

    def de_energise(self) -> None:
        if self._energised:
            self.switch_count += 1
        self._energised = False


@dataclass
class Part:
    serial: str
    defective: bool
    lux: int


class CameraSensor:
    """Yields the next part on the belt, or nothing when the belt is stopped."""

    name = "camera"

    def __init__(self, cell: "SimulatedCell") -> None:
        self.cell = cell

    def read(self) -> dict[str, Any]:
        part = self.cell.next_part()
        if part is None:
            return {"sensor": "camera", "part": None, "reason": "conveyor stopped"}
        return {
            "sensor": "camera",
            "part": part.serial,
            "ground_truth_defective": part.defective,
            "lux": part.lux,
        }


class SimulatedCell:
    """The device the governed runtime drives."""

    profile = SIM_PROFILE

    def __init__(self, *, seed: int = 20260821, defect_rate: float = 0.25) -> None:
        self.relay = SimulatedRelay()
        self._rng = random.Random(seed)
        self._defect_rate = defect_rate
        self._counter = 0
        self.speed = 0.0
        self.conveyor_running = False
        self.diverted: list[str] = []
        self.processed: list[str] = []
        self.stops: list[str] = []
        self.energy_spent = 0.0

    # ------------------------------------------------------------------ sensors
    def sensors(self) -> dict[str, Any]:
        return {"camera": CameraSensor(self)}

    def next_part(self) -> Part | None:
        if not self.conveyor_running or not self.relay.energised():
            return None
        self._counter += 1
        part = Part(
            serial=f"P{self._counter:04d}",
            defective=self._rng.random() < self._defect_rate,
            lux=self._rng.choice([180, 320, 450, 500]),
        )
        self.processed.append(part.serial)
        return part

    # ---------------------------------------------------------------- actuation
    def perform(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a physical action. Refuses everything while the relay is open.

        This refusal is the last line of defence, below the policy engine and
        below the supervisor: even if every software control were bypassed, an
        open relay still means nothing moves.
        """
        if not self.relay.energised() and action != "stop_conveyor":
            return {
                "performed": False,
                "action": action,
                "reason": "stop relay is de-energised; the cell is physically stopped",
            }

        cost = self.profile.energy_model.get(action)
        if cost is None:
            return {
                "performed": False,
                "action": action,
                "reason": f"unknown action {action!r} for device class 'sim'",
            }
        self.energy_spent += cost

        if action == "set_speed":
            self.speed = float(params.get("speed", 0.0))
            self.conveyor_running = self.speed > 0
            return {"performed": True, "action": action, "speed": self.speed}
        if action == "divert_part":
            serial = str(params.get("serial", "unknown"))
            self.diverted.append(serial)
            return {"performed": True, "action": action, "serial": serial}
        if action == "stop_conveyor":
            self.conveyor_running = False
            self.speed = 0.0
            self.stops.append(str(params.get("reason", "unspecified")))
            self.relay.de_energise()
            return {"performed": True, "action": action}
        if action == "resume_conveyor":
            self.conveyor_running = True
            self.speed = float(params.get("speed", 0.2))
            return {"performed": True, "action": action, "speed": self.speed}
        raise NotPortedError("sim", action, "add a branch to SimulatedCell.perform")

    # -------------------------------------------------------------------- state
    def state(self) -> dict[str, Any]:
        return {
            "device_class": self.profile.device_class,
            "relay_energised": self.relay.energised(),
            "relay_switches": self.relay.switch_count,
            "conveyor_running": self.conveyor_running,
            "speed": self.speed,
            "processed": len(self.processed),
            "diverted": list(self.diverted),
            "stops": list(self.stops),
            "energy_spent_j": round(self.energy_spent, 4),
        }


class SimulatedModel:
    """A stand-in classifier with a knob for the two failure modes that matter.

    ``miss_rate`` produces false negatives (a defect called good) and
    ``false_alarm_rate`` produces false positives. Both are governance events,
    not merely accuracy numbers: one is a safety failure, the other is the
    reason operators start ignoring the system.
    """

    def __init__(
        self, *, seed: int = 7, miss_rate: float = 0.0, false_alarm_rate: float = 0.0
    ) -> None:
        self._rng = random.Random(seed)
        self.miss_rate = miss_rate
        self.false_alarm_rate = false_alarm_rate

    def infer(self, observation: dict[str, Any]) -> dict[str, Any]:
        truth = bool(observation.get("ground_truth_defective"))
        predicted = truth
        if truth and self._rng.random() < self.miss_rate:
            predicted = False
        elif not truth and self._rng.random() < self.false_alarm_rate:
            predicted = True
        # Confidence is degraded in low light, mirroring the card's declared
        # limitation ("degrades below 200 lux") so the demo can exercise it.
        lux = int(observation.get("lux", 500))
        confidence = 0.95 if lux >= 200 else 0.55
        return {
            "part": observation.get("part"),
            "defect": predicted,
            "confidence": confidence,
            "lux": lux,
        }
