"""CLI tests — the path an auditor actually takes."""

from __future__ import annotations

import json
import os

from governed_edge_ai.cli import main


def test_demo_then_independent_verify(tmp_path, capsys):
    out = str(tmp_path / "run")
    assert main(["demo", "--out", out, "--parts", "16"]) == 0
    captured = capsys.readouterr().out
    assert "refused      : 4" in captured

    journal = os.path.join(out, "journal.jsonl")
    store = os.path.join(out, "trust-store.json")
    assert main(["verify", "--journal", journal, "--trust-store", store]) == 0
    assert "journal verified" in capsys.readouterr().out


def test_verify_fails_on_a_tampered_journal(tmp_path, capsys):
    out = str(tmp_path / "run")
    main(["demo", "--out", out, "--parts", "16"])
    capsys.readouterr()

    journal = os.path.join(out, "journal.jsonl")
    lines = [json.loads(line) for line in open(journal, encoding="utf-8") if line.strip()]
    for record in lines:
        if record["kind"] == "policy_decision" and record["body"]["effect"] == "deny":
            record["body"]["effect"] = "allow"     # the edit somebody would make
            break
    with open(journal, "w", encoding="utf-8") as handle:
        for record in lines:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    assert main(["verify", "--journal", journal]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_keygen_truststore_sign_admit_round_trip(tmp_path, capsys):
    owner = str(tmp_path / "owner.json")
    risk = str(tmp_path / "risk.json")
    assert main(["keygen", "--key-id", "owner-1", "--role", "model_owner", "--out", owner]) == 0
    assert main(["keygen", "--key-id", "risk-1", "--role", "risk_officer", "--out", risk]) == 0

    store = str(tmp_path / "store.json")
    assert main(["truststore", "--key", owner, "--key", risk, "--out", store]) == 0

    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"weights")

    from governed_edge_ai.agent.scenario import demo_card

    card_path = str(tmp_path / "card.json")
    with open(card_path, "w", encoding="utf-8") as handle:
        json.dump(demo_card("sha256:" + "00" * 32), handle)

    envelope = str(tmp_path / "envelope.json")
    assert main(["sign", "--card", card_path, "--key", owner, "--key", risk,
                 "--artifact", str(artifact), "--out", envelope]) == 0
    capsys.readouterr()

    # ventuno-q is an authorised target and declares every control.
    assert main(["admit", "--envelope", envelope, "--trust-store", store,
                 "--device", "ventuno-q", "--artifact", str(artifact)]) == 0
    assert "ADMITTED" in capsys.readouterr().out

    # uno-r4-wifi cannot hold the journal, so the same card is refused.
    assert main(["admit", "--envelope", envelope, "--trust-store", store,
                 "--device", "uno-r4-wifi", "--artifact", str(artifact)]) == 1
    output = capsys.readouterr().out
    assert "REFUSED" in output
    assert "inference_journal" in output


def test_devices_and_policy_listings(tmp_path, capsys):
    assert main(["devices"]) == 0
    listing = capsys.readouterr().out
    for device_class in ("uno-q", "ventuno-q", "uno-r4-wifi", "alvik", "nesso-n1"):
        assert device_class in listing

    policy = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "policies", "inspection.json"
    )
    assert main(["policy", "--policy", policy]) == 0
    assert "default: deny" in capsys.readouterr().out
