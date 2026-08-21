"""Stop channels, human oversight, and Article 50 marking."""

from __future__ import annotations

import pytest

from governed_edge_ai.errors import ConfigurationError
from governed_edge_ai.hal.sim import SimulatedRelay
from governed_edge_ai.marking import OutputMarker, verify_marking
from governed_edge_ai.oversight import (
    AbsentOperator,
    CompositeStopChannel,
    HardwareStopChannel,
    HeartbeatStopChannel,
    ScriptedConfirmer,
    SoftwareStopChannel,
    Supervisor,
)


# ---------------------------------------------------------------- stop channels
def test_software_channel_engages_and_releases():
    channel = SoftwareStopChannel()
    assert not channel.engaged()
    channel.engage("test")
    assert channel.engaged()
    channel.release("operator-01")
    assert not channel.engaged()


def test_release_requires_a_named_operator():
    channel = SoftwareStopChannel()
    channel.engage("test")
    with pytest.raises(ConfigurationError):
        channel.release("unattended")
    with pytest.raises(ConfigurationError):
        channel.release("")
    assert channel.engaged()


def test_heartbeat_channel_starts_engaged(clock):
    """A supervisor that has never checked in has not earned a running machine."""
    channel = HeartbeatStopChannel(timeout_seconds=5, clock=clock)
    assert channel.engaged()
    channel.beat()
    assert not channel.engaged()


def test_heartbeat_engages_when_stale(clock):
    channel = HeartbeatStopChannel(timeout_seconds=5, clock=clock)
    channel.beat()
    clock.advance(seconds=4)
    assert not channel.engaged()
    clock.advance(seconds=2)
    assert channel.engaged()
    assert "stale" in channel.status()["reason"]


def test_hardware_channel_follows_the_relay():
    relay = SimulatedRelay()
    channel = HardwareStopChannel(relay)
    assert channel.engaged()          # de-energised == stopped
    relay.energise()
    assert not channel.engaged()
    channel.engage("emergency")
    assert channel.engaged()
    assert not relay.energised()      # engaging actually opens the circuit


def test_composite_is_engaged_if_any_member_is(clock):
    software = SoftwareStopChannel()
    relay = SimulatedRelay()
    relay.energise()
    hardware = HardwareStopChannel(relay)
    composite = CompositeStopChannel([software, hardware])
    assert not composite.engaged()

    relay.de_energise()
    assert composite.engaged()
    assert composite.engaged_channels() == ["hardware"]

    relay.energise()
    software.engage("operator pressed stop")
    assert composite.engaged()
    assert composite.engaged_channels() == ["software"]


def test_empty_composite_is_a_configuration_error():
    with pytest.raises(ConfigurationError):
        CompositeStopChannel([])


def test_adding_a_channel_can_only_make_stopping_easier(clock):
    """Monotonicity property: no member can veto another member's stop."""
    relay = SimulatedRelay()
    relay.energise()
    members = [SoftwareStopChannel(), HardwareStopChannel(relay),
               HeartbeatStopChannel(timeout_seconds=5, clock=clock)]
    composite = CompositeStopChannel(members)
    # the heartbeat has never beaten, so the composite is engaged regardless
    assert composite.engaged()


# ------------------------------------------------------------- human oversight
def test_absent_operator_refuses(clock):
    supervisor = Supervisor(stop_channel=SoftwareStopChannel(), clock=clock)
    record = supervisor.ask({"action": "divert_part"}, ("low confidence",))
    assert record["approved"] is False
    assert record["operator_id"] == "unattended"


def test_scripted_confirmer_runs_out_and_then_refuses(clock):
    supervisor = Supervisor(
        stop_channel=SoftwareStopChannel(),
        confirmer=ScriptedConfirmer(answers=[True]),
        clock=clock,
    )
    assert supervisor.ask({}, ())["approved"] is True
    second = supervisor.ask({}, ())
    assert second["approved"] is False
    assert second["operator_id"] == "unattended"


def test_supervisor_stop_and_resume_are_journal_ready(clock):
    supervisor = Supervisor(stop_channel=SoftwareStopChannel(), clock=clock)
    stopped = supervisor.stop("budget exhausted")
    assert stopped["event"] == "stop_engaged"
    assert supervisor.stopped()
    resumed = supervisor.resume("operator-01")
    assert resumed["operator_id"] == "operator-01"
    assert not supervisor.stopped()


# --------------------------------------------------------------------- marking
@pytest.fixture
def marker(clock):
    return OutputMarker(
        device_id="sim-cell-01",
        model_id="weld-defect-detector",
        model_version="1.4.0",
        card_digest="sha256:" + "aa" * 32,
        disclosure="Automated visual inspection — AI generated result.",
        clock=clock,
    )


def test_marking_binds_the_output(marker):
    marked = marker.mark({"part": "P0001", "defect": True})
    ok, reason = verify_marking(marked.manifest, marked.output)
    assert ok, reason


def test_marking_does_not_validate_a_different_output(marker):
    marked = marker.mark({"part": "P0001", "defect": True})
    ok, reason = verify_marking(marked.manifest, {"part": "P0001", "defect": False})
    assert not ok
    assert "digest mismatch" in reason


def test_manifest_carries_no_payload(marker):
    """Provenance must be publishable without disclosing the input."""
    marked = marker.mark(
        {"part": "P0001", "defect": True}, input_digest="sha256:" + "bb" * 32
    )
    serialised = str(marked.manifest)
    assert "P0001" not in serialised
    assert marked.manifest["input_digest"].startswith("sha256:")
    assert marked.manifest["synthetic"] is True


def test_journal_record_omits_the_payload(marker):
    marked = marker.mark({"part": "P0001", "defect": True})
    record = marked.to_record()
    assert set(record) == {"output_digest", "manifest_digest", "disclosure"}


def test_bytes_outputs_are_supported(marker):
    marked = marker.mark(b"\x89PNG fake image bytes")
    ok, _ = verify_marking(marked.manifest, b"\x89PNG fake image bytes")
    assert ok


@pytest.mark.parametrize(
    "manifest",
    [
        {"schema": "something/else"},
        {"schema": "governed-edge-ai/provenance/v1"},
        "not a manifest",
    ],
)
def test_malformed_manifests_are_rejected(manifest):
    ok, _ = verify_marking(manifest, {"anything": 1})
    assert not ok
