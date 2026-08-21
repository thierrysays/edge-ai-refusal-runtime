"""Admission gate tests.

The tests that matter here are the *negative* ones. A gate that admits a good
model proves nothing; a gate that admits a bad one is worse than no gate at all,
because it manufactures assurance. Each refusal below corresponds to a control
claimed in docs/CONTROL_MAP.md, if a test is deleted, the claim goes with it.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from governed_edge_ai.clock import FrozenClock
from governed_edge_ai.errors import AdmissionDenied
from governed_edge_ai.registry import RuntimeContext, TrustStore, admit, sign_card
from governed_edge_ai.registry.signing import TRUST_STORE_SCHEMA, SigningKey

from .conftest import KEY_FROM, KEY_UNTIL, NOW


def reasons(decision) -> str:
    return " | ".join(decision.reasons)


# --------------------------------------------------------------------- happy path
def test_admits_a_properly_signed_high_risk_model(
    signed_high_risk, trust_store, full_runtime, artifact, clock
):
    path, _ = artifact
    decision = admit(
        signed_high_risk, trust_store, full_runtime, artifact_path=path, clock=clock
    )
    assert decision.admitted, reasons(decision)
    assert decision.model_id == "weld-defect-detector"
    # Baseline controls for the high tier are imposed even though the card only
    # asked for two of them.
    assert set(decision.obligations) >= {
        "inference_journal",
        "policy_mediation",
        "stop_channel",
        "output_marking",
    }
    assert ("risk-officer-01", "risk_officer") in decision.signers


def test_decision_is_serialisable_for_the_journal(
    signed_high_risk, trust_store, full_runtime, artifact, clock
):
    path, _ = artifact
    record = admit(
        signed_high_risk, trust_store, full_runtime, artifact_path=path, clock=clock
    ).to_record()
    assert record["admitted"] is True
    assert {c["name"] for c in record["checks"]} >= {
        "signatures_verify",
        "card_structure",
        "signer_quorum",
        "artifact_binding",
        "controls_enforceable",
    }


# ------------------------------------------------------------------ separation of duties
def test_high_risk_needs_two_distinct_roles(
    high_risk_card, owner_key, trust_store, full_runtime, artifact, clock
):
    envelope = sign_card(high_risk_card, [owner_key], clock=clock)
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "requires 2 distinct signer role(s)" in reasons(decision)
    assert "countersigned by a risk_officer" in reasons(decision)


def test_two_signatures_from_the_same_role_do_not_form_a_quorum(
    high_risk_card, trust_store, full_runtime, artifact, clock
):
    second_owner = SigningKey.generate("model-owner-02", "model_owner")
    store = TrustStore(
        {
            "schema": TRUST_STORE_SCHEMA,
            "keys": trust_store.to_document()["keys"]
            + [second_owner.public_entry(KEY_FROM, KEY_UNTIL)],
        }
    )
    owner = SigningKey.generate("model-owner-01", "model_owner")
    # Sign with two model owners; the real owner-01 key differs from the store's,
    # so use the two keys we actually registered.
    envelope = sign_card(high_risk_card, [second_owner], clock=clock)
    path, _ = artifact
    decision = admit(envelope, store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "risk_officer" in reasons(decision)
    del owner


def test_limited_risk_needs_only_one_signature(
    limited_risk_card, owner_key, trust_store, full_runtime, artifact, clock
):
    envelope = sign_card(limited_risk_card, [owner_key], clock=clock)
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert decision.admitted, reasons(decision)


# ------------------------------------------------------------------------ signatures
def test_tampered_card_breaks_the_signature(
    signed_high_risk, trust_store, full_runtime, artifact, clock
):
    envelope = copy.deepcopy(signed_high_risk)
    envelope["card"]["risk_tier"] = "minimal"  # the classic downgrade attack
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "does not verify" in reasons(decision)


def test_signature_cannot_be_transplanted_between_cards(
    signed_high_risk, limited_risk_card, trust_store, full_runtime, artifact, clock
):
    envelope = {
        "schema": signed_high_risk["schema"],
        "card": limited_risk_card,
        "signatures": signed_high_risk["signatures"],
    }
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "does not verify" in reasons(decision)


def test_unknown_signing_key_is_refused(
    high_risk_card, trust_store, full_runtime, artifact, clock
):
    stranger = SigningKey.generate("not-in-the-store", "risk_officer")
    envelope = sign_card(high_risk_card, [stranger], clock=clock)
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "unknown key_id" in reasons(decision)


def test_revoked_key_is_refused(
    high_risk_card, owner_key, risk_key, full_runtime, artifact, clock
):
    document = TrustStore.from_keys(
        [owner_key, risk_key], KEY_FROM, KEY_UNTIL
    ).to_document()
    for entry in document["keys"]:
        if entry["key_id"] == "risk-officer-01":
            entry["revoked_at"] = "2026-08-10T00:00:00Z"
    store = TrustStore(document)
    envelope = sign_card(high_risk_card, [owner_key, risk_key], clock=clock)
    path, _ = artifact
    decision = admit(envelope, store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "revoked" in reasons(decision)


def test_duplicate_signature_from_one_key_does_not_inflate_the_quorum(
    high_risk_card, owner_key, trust_store, full_runtime, artifact, clock
):
    envelope = sign_card(high_risk_card, [owner_key], clock=clock)
    envelope["signatures"].append(copy.deepcopy(envelope["signatures"][0]))
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "duplicate signature" in reasons(decision)


def test_future_dated_signature_is_refused(
    high_risk_card, owner_key, risk_key, trust_store, full_runtime, artifact
):
    future = FrozenClock(datetime(2026, 12, 1, tzinfo=timezone.utc))
    envelope = sign_card(high_risk_card, [owner_key, risk_key], clock=future)
    path, _ = artifact
    decision = admit(
        envelope, trust_store, full_runtime, artifact_path=path, clock=FrozenClock(NOW)
    )
    assert not decision.admitted
    assert "dated in the future" in reasons(decision)


# ------------------------------------------------------------------- artefact binding
def test_artefact_digest_mismatch_is_refused(
    signed_high_risk, trust_store, full_runtime, tmp_path, clock
):
    impostor = tmp_path / "other.bin"
    impostor.write_bytes(b"different weights entirely")
    decision = admit(
        signed_high_risk,
        trust_store,
        full_runtime,
        artifact_path=str(impostor),
        clock=clock,
    )
    assert not decision.admitted
    assert "artefact digest mismatch" in reasons(decision)


def test_absent_artefact_is_a_failure_not_a_skip(
    signed_high_risk, trust_store, full_runtime, clock
):
    decision = admit(signed_high_risk, trust_store, full_runtime, clock=clock)
    assert not decision.admitted
    assert "could not be checked" in reasons(decision)


def test_missing_artefact_file_is_refused(
    signed_high_risk, trust_store, full_runtime, clock
):
    decision = admit(
        signed_high_risk,
        trust_store,
        full_runtime,
        artifact_path="/nonexistent/model.bin",
        clock=clock,
    )
    assert not decision.admitted
    assert "artefact not found" in reasons(decision)


# ------------------------------------------------------------------------- validity
def test_expired_card_is_refused(
    high_risk_card, owner_key, risk_key, trust_store, full_runtime, artifact
):
    late = FrozenClock(datetime(2027, 9, 1, tzinfo=timezone.utc))
    envelope = sign_card(high_risk_card, [owner_key, risk_key], clock=FrozenClock(NOW))
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=late)
    assert not decision.admitted
    assert "card valid from" in reasons(decision)


# ------------------------------------------------------------ target and enforceability
def test_wrong_device_class_is_refused(
    signed_high_risk, trust_store, artifact, clock
):
    runtime = RuntimeContext.of(
        "uno-r4-wifi",
        "inference_journal",
        "policy_mediation",
        "stop_channel",
        "output_marking",
        "human_confirmation",
    )
    path, _ = artifact
    decision = admit(signed_high_risk, trust_store, runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "this device is 'uno-r4-wifi'" in reasons(decision)


def test_runtime_without_stop_channel_cannot_run_a_high_risk_model(
    signed_high_risk, trust_store, artifact, clock
):
    """The load-bearing test of the whole project.

    A device with no way to stop the model is not a device that may run a
    high-risk model, however impeccable its paperwork.
    """
    runtime = RuntimeContext.of(
        "sim", "inference_journal", "policy_mediation", "output_marking"
    )
    path, _ = artifact
    decision = admit(signed_high_risk, trust_store, runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "stop_channel" in reasons(decision)


def test_raise_if_denied_raises_with_all_reasons(
    signed_high_risk, trust_store, clock
):
    runtime = RuntimeContext.of("sim")
    decision = admit(signed_high_risk, trust_store, runtime, clock=clock)
    with pytest.raises(AdmissionDenied) as excinfo:
        decision.raise_if_denied()
    assert "weld-defect-detector" in str(excinfo.value)


# -------------------------------------------------------------------- malformed input
@pytest.mark.parametrize(
    "mutation, expected",
    [
        ({"intended_purpose": "too short"}, "intended_purpose"),
        ({"risk_tier": "catastrophic"}, "risk_tier"),
        ({"artifact_digest": "not-a-digest"}, "artifact_digest"),
        ({"out_of_scope_uses": []}, "out-of-scope"),
        ({"controls_required": ["telepathy"]}, "unknown controls"),
        ({"valid_until": "2026-01-01T00:00:00Z"}, "valid_from must precede"),
    ],
)
def test_structurally_invalid_cards_are_refused(
    high_risk_card, owner_key, risk_key, trust_store, full_runtime, artifact,
    clock, mutation, expected,
):
    card = {**copy.deepcopy(high_risk_card), **mutation}
    envelope = sign_card(card, [owner_key, risk_key], clock=clock)
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert expected in reasons(decision)


def test_envelope_without_signatures_is_refused(
    high_risk_card, trust_store, full_runtime, artifact, clock
):
    envelope = {
        "schema": "governed-edge-ai/signed-card/v1",
        "card": high_risk_card,
        "signatures": [],
    }
    path, _ = artifact
    decision = admit(envelope, trust_store, full_runtime, artifact_path=path, clock=clock)
    assert not decision.admitted
    assert "no signatures" in reasons(decision)


def test_garbage_input_is_refused_not_crashed(trust_store, full_runtime, clock):
    decision = admit({"nonsense": True}, trust_store, full_runtime, clock=clock)
    assert not decision.admitted
