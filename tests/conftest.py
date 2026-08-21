from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

import pytest

from governed_edge_ai.clock import FrozenClock
from governed_edge_ai.registry import RuntimeContext, SigningKey, TrustStore, sign_card

NOW = datetime(2026, 8, 21, 9, 0, 0, tzinfo=timezone.utc)
KEY_FROM = datetime(2026, 1, 1, tzinfo=timezone.utc)
KEY_UNTIL = datetime(2027, 12, 31, tzinfo=timezone.utc)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


@pytest.fixture
def owner_key() -> SigningKey:
    return SigningKey.generate("model-owner-01", "model_owner")


@pytest.fixture
def risk_key() -> SigningKey:
    return SigningKey.generate("risk-officer-01", "risk_officer")


@pytest.fixture
def device_key() -> SigningKey:
    return SigningKey.generate("device-uno-q-01", "operator")


@pytest.fixture
def trust_store(owner_key, risk_key, device_key) -> TrustStore:
    return TrustStore.from_keys([owner_key, risk_key, device_key], KEY_FROM, KEY_UNTIL)


@pytest.fixture
def artifact(tmp_path):
    """A stand-in for model weights, plus its digest."""
    from governed_edge_ai.canonical import digest_file

    path = tmp_path / "model.bin"
    path.write_bytes(b"weights-of-a-very-small-defect-detector")
    return str(path), digest_file(str(path))


@pytest.fixture
def high_risk_card(artifact) -> dict[str, Any]:
    _, artifact_digest = artifact
    return {
        "schema": "governed-edge-ai/model-card/v1",
        "model_id": "weld-defect-detector",
        "version": "1.4.0",
        "artifact_digest": artifact_digest,
        "risk_tier": "high",
        "intended_purpose": (
            "Detect visual weld defects on a production line and stop the "
            "conveyor when a defect is detected."
        ),
        "out_of_scope_uses": [
            "Any assessment of the operator rather than the weld.",
            "Safety certification of the finished assembly.",
        ],
        "provider": {"name": "Atelier Lacretelle", "contact": "governance@example.org"},
        "deployment": {"targets": ["ventuno-q", "sim"], "runtime": "onnx"},
        "data": {"training_data_summary": "12k labelled weld images", "personal_data": False},
        "evaluation": {
            "metrics": {"precision": 0.94, "recall": 0.89},
            "evaluated_at": "2026-07-30T00:00:00Z",
            "known_limitations": ["Degrades below 200 lux."],
        },
        "oversight": {"human_in_the_loop": True, "stop_channel_required": True},
        "transparency": {
            "marks_synthetic_output": True,
            "disclosure_text": "Automated visual inspection — AI generated result.",
        },
        "controls_required": ["inference_journal", "policy_mediation"],
        "valid_from": "2026-08-01T00:00:00Z",
        "valid_until": "2027-08-01T00:00:00Z",
    }


@pytest.fixture
def limited_risk_card(high_risk_card) -> dict[str, Any]:
    card = copy.deepcopy(high_risk_card)
    card["risk_tier"] = "limited"
    card["model_id"] = "shift-summary-writer"
    return card


@pytest.fixture
def full_runtime() -> RuntimeContext:
    return RuntimeContext.of(
        "sim",
        "inference_journal",
        "policy_mediation",
        "stop_channel",
        "output_marking",
        "human_confirmation",
        operator_id="operator-01",
    )


@pytest.fixture
def signed_high_risk(high_risk_card, owner_key, risk_key, clock):
    return sign_card(high_risk_card, [owner_key, risk_key], clock=clock)
