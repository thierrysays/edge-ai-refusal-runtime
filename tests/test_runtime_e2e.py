"""End-to-end tests on the governed runtime.

These assert on the *world* — what the cell did — not on log lines. A governance
test that only checks that something was logged is testing the logger.
"""

from __future__ import annotations

import pytest

from governed_edge_ai.agent import build_bench, run_scenario
from governed_edge_ai.errors import AdmissionDenied
from governed_edge_ai.journal import read_journal, verify_journal
from governed_edge_ai.policy import ActuationRequest
from governed_edge_ai.registry import TrustStore


def start(bench, operator="operator-01"):
    bench.runtime.open_session()
    bench.runtime.resume(operator)
    return bench.runtime


def req(**kwargs) -> ActuationRequest:
    defaults = {
        "action": "set_speed",
        "target": "cell",
        "params": {"speed": 0.3},
        "requester": "agent",
        "rationale": "nominal operation",
    }
    return ActuationRequest(**{**defaults, **kwargs})


# ------------------------------------------------------------------ the cell
def test_the_cell_cannot_start_itself(tmp_path):
    bench = build_bench(str(tmp_path))
    bench.runtime.open_session()
    outcome = bench.runtime.act(req())
    assert outcome.refused
    assert "stop channel engaged" in outcome.reasons[0]
    assert bench.cell.speed == 0.0
    assert bench.cell.processed == []


def test_an_operator_release_is_what_starts_it(tmp_path):
    bench = build_bench(str(tmp_path))
    runtime = start(bench)
    assert runtime.act(req()).performed
    assert bench.cell.speed == pytest.approx(0.3)


def test_speed_outside_the_declared_envelope_never_reaches_the_device(tmp_path):
    bench = build_bench(str(tmp_path))
    runtime = start(bench)
    runtime.act(req())
    outcome = runtime.act(req(params={"speed": 0.9}, rationale="behind on throughput"))
    assert outcome.refused
    assert bench.cell.speed == pytest.approx(0.3)   # the world did not change


def test_foreign_targets_are_refused(tmp_path):
    bench = build_bench(str(tmp_path))
    runtime = start(bench)
    outcome = runtime.act(req(target="paint-booth"))
    assert outcome.refused
    assert "out of scope" in outcome.reasons[0]


def test_an_unexplained_action_is_refused(tmp_path):
    bench = build_bench(str(tmp_path))
    runtime = start(bench)
    outcome = runtime.act(
        req(action="divert_part", params={"serial": "P1", "confidence": 0.99}, rationale="")
    )
    assert outcome.refused
    assert bench.cell.diverted == []


# --------------------------------------------------------------- human oversight
def test_low_confidence_diversion_requires_a_human_and_is_refused_when_absent(tmp_path):
    bench = build_bench(str(tmp_path), confirmations=[])   # nobody answers
    runtime = start(bench)
    runtime.act(req())
    outcome = runtime.act(
        req(action="divert_part", params={"serial": "P1", "confidence": 0.55},
            rationale="uncertain defect call")
    )
    assert outcome.refused
    assert outcome.effect == "require_human"
    assert bench.cell.diverted == []
    assert runtime.counters["escalated"] == 1
    assert runtime.counters["escalations_approved"] == 0


def test_low_confidence_diversion_proceeds_when_a_human_approves(tmp_path):
    bench = build_bench(str(tmp_path), confirmations=[True])
    runtime = start(bench)
    runtime.act(req())
    outcome = runtime.act(
        req(action="divert_part", params={"serial": "P1", "confidence": 0.55},
            rationale="uncertain defect call")
    )
    assert outcome.performed
    assert bench.cell.diverted == ["P1"]


def test_the_machine_may_not_clear_its_own_fault(tmp_path):
    bench = build_bench(str(tmp_path), confirmations=[False])
    runtime = start(bench)
    runtime.act(req())
    runtime.act(req(action="stop_conveyor", params={"reason": "fault"},
                    rationale="upstream fault detected"))
    assert bench.cell.relay.energised() is False
    # Even asking to resume is refused: the stop channel gates everything.
    outcome = runtime.act(req(action="resume_conveyor", params={"speed": 0.3},
                              rationale="the fault looks cleared"))
    assert outcome.refused
    assert bench.cell.conveyor_running is False


# -------------------------------------------------------------------- budgets
def test_budget_exhaustion_stops_the_cell(tmp_path):
    bench = build_bench(str(tmp_path), budgets={"actions": 2.0, "energy_j": 100.0})
    runtime = start(bench)
    assert runtime.act(req()).performed
    assert runtime.act(
        req(action="divert_part", params={"serial": "P1", "confidence": 0.95},
            rationale="confident defect")
    ).performed
    outcome = runtime.act(
        req(action="divert_part", params={"serial": "P2", "confidence": 0.95},
            rationale="confident defect")
    )
    assert outcome.refused
    assert "exhausted" in outcome.reasons[0]
    assert runtime.supervisor.stopped()
    assert bench.cell.diverted == ["P1"]


def test_energy_budget_is_enforced_separately(tmp_path):
    bench = build_bench(str(tmp_path), budgets={"actions": 50.0, "energy_j": 1.0})
    runtime = start(bench)
    assert runtime.act(req()).performed              # set_speed costs 0.5 J
    outcome = runtime.act(
        req(action="divert_part", params={"serial": "P1", "confidence": 0.95},
            rationale="confident defect")           # costs 2.0 J
    )
    assert outcome.refused
    assert "energy_j" in outcome.reasons[0]


# ------------------------------------------------------------------- admission
def test_a_device_without_a_stop_channel_cannot_open_a_session(tmp_path):
    from governed_edge_ai.hal.base import DeviceProfile

    bench = build_bench(str(tmp_path))
    crippled = DeviceProfile(
        device_class="sim",
        description="a cell whose relay was removed",
        available_controls=frozenset({"inference_journal", "policy_mediation",
                                      "output_marking", "human_confirmation"}),
        energy_model=bench.cell.profile.energy_model,
    )
    bench.cell.profile = crippled
    with pytest.raises(AdmissionDenied) as excinfo:
        bench.runtime.open_session()
    assert "stop_channel" in str(excinfo.value)


def test_refused_admission_is_still_journalled(tmp_path):
    from governed_edge_ai.hal.base import DeviceProfile

    bench = build_bench(str(tmp_path))
    bench.cell.profile = DeviceProfile(
        device_class="sim", description="no controls at all",
        available_controls=frozenset(), energy_model={},
    )
    with pytest.raises(AdmissionDenied):
        bench.runtime.open_session()
    kinds = [entry.kind for entry in read_journal(bench.journal.path)]
    assert kinds == ["session_open", "admission"]
    admission = list(read_journal(bench.journal.path))[1]
    assert admission.body["admitted"] is False
    assert admission.body["reasons"]


def test_no_inference_is_possible_before_admission(tmp_path):
    bench = build_bench(str(tmp_path))
    with pytest.raises(AdmissionDenied):
        bench.runtime.infer({"part": "P1"}, bench.model)


# --------------------------------------------------------------------- evidence
def test_scenario_produces_a_verifiable_journal(tmp_path):
    result = run_scenario(str(tmp_path), parts=16)
    report = verify_journal(result["journal_path"], TrustStore(result["trust_store"]))
    assert report.ok, report.summary()
    assert report.checkpoints == 1


def test_scenario_is_deterministic(tmp_path):
    a = run_scenario(str(tmp_path / "a"), parts=16)
    b = run_scenario(str(tmp_path / "b"), parts=16)
    assert a["trace"] == b["trace"]
    assert a["report"]["counters"] == b["report"]["counters"]
    assert a["report"]["device_state"] == b["report"]["device_state"]


def test_scenario_refuses_more_than_it_permits_by_design(tmp_path):
    result = run_scenario(str(tmp_path), parts=16)
    counters = result["report"]["counters"]
    assert counters["denied"] == 4
    assert counters["escalated"] == 1
    assert counters["inferences"] == 10


def test_every_actuation_has_a_journal_entry(tmp_path):
    result = run_scenario(str(tmp_path), parts=16)
    entries = list(read_journal(result["journal_path"]))
    decisions = [e for e in entries if e.kind == "policy_decision"]
    actuations = [e for e in entries if e.kind == "actuation"]
    # Every performed action is preceded by a recorded decision; there are more
    # decisions than actuations precisely because refusals never actuate.
    assert len(decisions) > len(actuations)
    for entry in actuations:
        assert entry.body["request_digest"]
        assert "device_state" in entry.body


def test_journal_records_carry_no_payload(tmp_path):
    """Retention discipline: ten years of technical file, no images inside it."""
    result = run_scenario(str(tmp_path), parts=16)
    for entry in read_journal(result["journal_path"]):
        if entry.kind == "inference":
            assert set(entry.body["summary"]) <= {"defect", "confidence", "part"}
            assert "ground_truth_defective" not in str(entry.body)
