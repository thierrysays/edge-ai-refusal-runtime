"""Device profiles for the boards this project targets.

These profiles are data, and they are the honest part of the repository: they
record what each board *can* enforce, which is not the same as what a model card
would like it to enforce. The admission gate consults them, so a profile that
overstates a device's capability is not a documentation error, it is a control
failure.

Backends raise :class:`~.base.NotPortedError` with a specific porting note until
the board is on the bench. Nothing here pretends to drive hardware it has not
driven.

Target inventory (August 2026): UNO Q 4 GB, VENTUNO Q, UNO R4 WiFi with the
Plug and Make Kit Modulino nodes, Alvik, Nesso N1.

A profile states a *capability*, never a job. ``available_controls`` answers
"could this board enforce this control if asked", which is the only question the
admission gate has. It does not answer "what is this board for". The sibling
`governed-edge-ai` repository answers that second question for one particular
rig, and answers it more strictly: there, the UNO Q is the witness and enforces
nothing, and no board both decides and enforces. Both statements are true at
once because they are about different things, and reading a capability set as a
role assignment is the misreading this paragraph exists to prevent.
"""

from __future__ import annotations

from typing import Any

from .base import DeviceProfile, NotPortedError

# ---------------------------------------------------------------------- profiles

UNO_Q = DeviceProfile(
    device_class="uno-q",
    description=(
        "Arduino UNO Q 4 GB, Qualcomm Dragonwing QRB2210 running Debian, "
        "paired with an STM32U585 real-time microcontroller. Linux gives it a "
        "durable filesystem, so it can hold the journal; Qwiic gives it the "
        "Modulino nodes for the stop relay and the confirmation button."
    ),
    available_controls=frozenset(
        {
            "inference_journal",
            "policy_mediation",
            "stop_channel",
            "output_marking",
            "human_confirmation",
        }
    ),
    energy_model={"inference": 0.9, "set_speed": 0.5, "divert_part": 2.0,
                  "stop_conveyor": 0.2, "resume_conveyor": 1.0},
    energy_model_source="estimate, not yet measured on the bench",
)

VENTUNO_Q = DeviceProfile(
    device_class="ventuno-q",
    description=(
        "Arduino VENTUNO Q, Qualcomm Dragonwing IQ8 with an NPU rated around "
        "40 TOPS, 16 GB RAM, and an STM32H5 on Zephyr for actuation. Linux plus "
        "CAN-FD plus ROS 2: the only board here that can run a real vision model "
        "and drive machinery from the same enclosure."
    ),
    available_controls=frozenset(
        {
            "inference_journal",
            "policy_mediation",
            "stop_channel",
            "output_marking",
            "human_confirmation",
        }
    ),
    energy_model={"inference": 2.4, "set_speed": 0.5, "divert_part": 2.0,
                  "stop_conveyor": 0.2, "resume_conveyor": 1.0},
    energy_model_source="estimate, not yet measured on the bench",
)

UNO_R4_WIFI = DeviceProfile(
    device_class="uno-r4-wifi",
    description=(
        "Arduino UNO R4 WiFi with Plug and Make Kit Modulino nodes. A "
        "microcontroller, not a computer: it can mediate policy and drive the "
        "latch relay, but it has no durable append-only storage, so it cannot "
        "hold the inference journal on its own."
    ),
    # Deliberately missing 'inference_journal'. Adding an SD shield or shipping
    # records to a paired UNO Q would change this line, and only then.
    available_controls=frozenset(
        {"policy_mediation", "stop_channel", "human_confirmation", "output_marking"}
    ),
    energy_model={"set_speed": 0.4, "divert_part": 1.8, "stop_conveyor": 0.1,
                  "resume_conveyor": 0.8},
    energy_model_source="estimate, not yet measured on the bench",
)

ALVIK = DeviceProfile(
    device_class="alvik",
    description=(
        "Arduino Alvik, mobile robot on a Nano ESP32, MicroPython. Used here as "
        "the actuated system for oversight demonstrations, and as the STEM "
        "platform: the same robot, the same stop channel, two audiences."
    ),
    available_controls=frozenset({"policy_mediation", "stop_channel"}),
    energy_model={"drive": 3.0, "turn": 1.5, "stop": 0.1},
    energy_model_source="estimate, not yet measured on the bench",
)

NESSO_N1 = DeviceProfile(
    device_class="nesso-n1",
    description=(
        "Arduino Nesso N1, ESP32-C6 with Wi-Fi 6, BLE, 802.15.4 and a LoRa "
        "radio, plus a touchscreen and two buttons. Its value here is the "
        "out-of-band path: an oversight console and a stop signal that do not "
        "depend on the network the governed system is using."
    ),
    available_controls=frozenset({"human_confirmation", "stop_channel"}),
    energy_model={"notify": 0.2, "confirm": 0.1},
    energy_model_source="estimate, not yet measured on the bench",
)

PROFILES: dict[str, DeviceProfile] = {
    profile.device_class: profile
    for profile in (UNO_Q, VENTUNO_Q, UNO_R4_WIFI, ALVIK, NESSO_N1)
}


def profile_for(device_class: str) -> DeviceProfile:
    try:
        return PROFILES[device_class]
    except KeyError:
        raise KeyError(
            f"unknown device class {device_class!r}; known: {sorted(PROFILES)}"
        ) from None


# ----------------------------------------------------------------- unported stubs

class _UnportedDevice:
    """Declares a profile, refuses to pretend it can actuate."""

    profile: DeviceProfile
    porting_note: str

    def __init__(self) -> None:
        self.relay = _UnportedRelay(self.profile.device_class, self.porting_note)

    def sensors(self) -> dict[str, Any]:
        raise NotPortedError(self.profile.device_class, "sensor access", self.porting_note)

    def perform(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotPortedError(
            self.profile.device_class, f"action {action!r}", self.porting_note
        )

    def state(self) -> dict[str, Any]:
        return {"device_class": self.profile.device_class, "ported": False}


class _UnportedRelay:
    def __init__(self, device_class: str, note: str) -> None:
        self._device_class = device_class
        self._note = note

    def energised(self) -> bool:
        # An unported relay reports "not energised" (stopped) rather than
        # raising. Fail-safe beats fail-loud for the stop path.
        return False

    def energise(self) -> None:
        raise NotPortedError(self._device_class, "relay energise", self._note)

    def de_energise(self) -> None:
        return None  # already stopped


class UnoQDevice(_UnportedDevice):
    profile = UNO_Q
    porting_note = (
        "on the UNO Q, run this package under Debian and drive the Modulino "
        "Latch Relay over Qwiic I2C from the Linux side; keep the journal on "
        "the eMMC, and expose the Article 14 stop as a GPIO read so that a "
        "crashed Python process leaves the relay de-energised."
    )


class VentunoQDevice(_UnportedDevice):
    profile = VENTUNO_Q
    porting_note = (
        "on the VENTUNO Q, keep this package on the Linux side and put the "
        "actuation loop on the STM32H5 under Zephyr; the stop channel belongs "
        "on the microcontroller, not on Linux, so that a kernel stall cannot "
        "keep the machine running. Bridge them over the Arduino Core IPC and "
        "mirror the relay state into the journal on every transition."
    )


class UnoR4WifiDevice(_UnportedDevice):
    profile = UNO_R4_WIFI
    porting_note = (
        "the UNO R4 WiFi cannot hold the journal: port the policy engine and the "
        "stop channel only, and ship every decision record over Wi-Fi to a "
        "paired UNO Q that owns the chain. Treat a lost link as a stop."
    )


class AlvikDevice(_UnportedDevice):
    profile = ALVIK
    porting_note = (
        "Alvik runs MicroPython: reimplement the request/decision structures as "
        "plain dicts, keep the policy rules as a JSON file on the flash, and let "
        "the robot refuse to move when the heartbeat from the supervising board "
        "goes stale."
    )


class NessoN1Device(_UnportedDevice):
    profile = NESSO_N1
    porting_note = (
        "use the Nesso N1 as the oversight console: render the escalation on the "
        "touchscreen, take approval from a physical button, and carry both over "
        "LoRa so the oversight path survives the failure of the main network."
    )


DEVICES = {
    "uno-q": UnoQDevice,
    "ventuno-q": VentunoQDevice,
    "uno-r4-wifi": UnoR4WifiDevice,
    "alvik": AlvikDevice,
    "nesso-n1": NessoN1Device,
}
