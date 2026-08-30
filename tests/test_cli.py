"""CLI tests, the path an auditor actually takes."""

from __future__ import annotations

import json
import os
import sys
import types

import pytest

from governed_edge_ai import observability
from governed_edge_ai.cli import main
from governed_edge_ai.errors import AdmissionDenied


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


# --------------------------------------------------------- observability (Sentry)
# Not a governance control (see `observability.py`), so these live here rather
# than being named in CONTROL_MAP.md: `test_cli.py` is the harness layer.

@pytest.fixture(autouse=True)
def _reset_sentry_env(monkeypatch):
    for var in ("SENTRY_DSN", "SENTRY_ENVIRONMENT", "SENTRY_RELEASE",
                "SENTRY_TRACES_SAMPLE_RATE"):
        monkeypatch.delenv(var, raising=False)
    yield
    observability._ENABLED = False


def _install_fake_sentry_sdk(monkeypatch):
    calls: dict = {"init": None, "captured": []}
    fake = types.ModuleType("sentry_sdk")
    fake.init = lambda **kwargs: calls.__setitem__("init", kwargs)  # type: ignore[attr-defined]
    fake.capture_exception = lambda exc: calls["captured"].append(exc)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    return calls


def test_init_sentry_is_a_silent_no_op_without_a_dsn():
    assert observability.init_sentry() is False
    assert observability._ENABLED is False


def test_init_sentry_warns_but_does_not_crash_without_the_sdk_installed(
    monkeypatch, capsys
):
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # forces ImportError
    assert observability.init_sentry() is False
    assert "observability" in capsys.readouterr().err


def test_init_sentry_initialises_when_the_dsn_and_sdk_are_present(monkeypatch):
    calls = _install_fake_sentry_sdk(monkeypatch)
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")

    assert observability.init_sentry(release="governed-edge-ai@0.1.0") is True
    assert observability._ENABLED is True
    assert calls["init"]["dsn"] == "https://public@o0.ingest.sentry.io/1"
    assert calls["init"]["environment"] == "test"
    assert calls["init"]["release"] == "governed-edge-ai@0.1.0"
    # No payload leaves this module by default: no PII, no local variables.
    assert calls["init"]["send_default_pii"] is False
    assert calls["init"]["include_local_variables"] is False
    assert calls["init"]["before_send"] is observability._scrub


def test_init_sentry_fails_closed_on_bad_configuration(monkeypatch, capsys):
    _install_fake_sentry_sdk(monkeypatch)
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "not-a-number")

    assert observability.init_sentry() is False
    assert observability._ENABLED is False
    assert "failed to initialise" in capsys.readouterr().err


def test_scrub_strips_the_request_and_frame_locals():
    event = {
        "request": {"data": "sensitive"},
        "exception": {
            "values": [
                {"stacktrace": {"frames": [{"filename": "x.py", "vars": {"key": "secret"}}]}}
            ]
        },
    }
    scrubbed = observability._scrub(event, {})
    assert scrubbed is not None
    assert "request" not in scrubbed
    assert scrubbed["extra"] == {}
    frame = scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "vars" not in frame
    assert frame["filename"] == "x.py"


def test_report_crash_is_a_no_op_when_sentry_was_never_enabled(monkeypatch):
    calls = _install_fake_sentry_sdk(monkeypatch)
    observability._ENABLED = False
    observability.report_crash(ValueError("boom"))
    assert calls["captured"] == []


def test_report_crash_skips_governance_refusals(monkeypatch):
    calls = _install_fake_sentry_sdk(monkeypatch)
    observability._ENABLED = True
    observability.report_crash(AdmissionDenied("refused, evidence is what matters"))
    assert calls["captured"] == []


def test_report_crash_reports_a_genuine_crash(monkeypatch):
    calls = _install_fake_sentry_sdk(monkeypatch)
    observability._ENABLED = True
    exc = ValueError("boom")
    observability.report_crash(exc)
    assert calls["captured"] == [exc]


def test_main_reports_an_unexpected_crash_and_still_lets_it_propagate(monkeypatch):
    calls = _install_fake_sentry_sdk(monkeypatch)
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/1")

    class _ExplodingParser:
        def parse_args(self, argv=None):
            return types.SimpleNamespace(func=self._boom)

        @staticmethod
        def _boom(_args):
            raise ValueError("unexpected")

    monkeypatch.setattr("governed_edge_ai.cli.build_parser", _ExplodingParser)

    with pytest.raises(ValueError, match="unexpected"):
        main(["devices"])
    assert len(calls["captured"]) == 1
    assert str(calls["captured"][0]) == "unexpected"
