"""Adversarial suite: attacks the controls rather than exercising them.

The rest of the suite asks whether a control fires when it should. This file
asks whether it can be made *not* to fire by someone trying — signature
transplant, key substitution, quorum-by-repetition, algorithm confusion,
backdating, chain reordering, and canonicalisation collisions.

Two of these tests are load-bearing in an unusual way. ``test_B4`` asserts that
a consistent forgery by the holder of the device key *succeeds*, because that is
the limitation ADR 0007 accepts and a test is the only place a limitation stays
honest. If it ever fails, the threat model changed and the ADR is stale.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from governed_edge_ai.canonical import canonical_bytes, digest
from governed_edge_ai.clock import FrozenClock
from governed_edge_ai.errors import SignatureInvalid
from governed_edge_ai.journal.chain import Journal, verify_journal
from governed_edge_ai.registry import (
    SigningKey,
    TrustStore,
    sign_card,
    verify_envelope,
)

NOW = datetime(2026, 8, 21, 9, 0, 0, tzinfo=timezone.utc)
FROM = datetime(2026, 1, 1, tzinfo=timezone.utc)
UNTIL = datetime(2027, 12, 31, tzinfo=timezone.utc)


# ---------------------------------------------------------------- signatures

def test_A1_signature_cannot_be_transplanted_to_another_card(
    high_risk_card, owner_key, risk_key, trust_store, clock
):
    """Lift signatures off a good card, staple them to a modified one."""
    good = sign_card(high_risk_card, [owner_key, risk_key], clock=clock)
    evil = copy.deepcopy(high_risk_card)
    evil["deployment"]["targets"].append("uno-r4-wifi")
    forged = {"schema": good["schema"], "card": evil, "signatures": good["signatures"]}
    with pytest.raises(SignatureInvalid):
        verify_envelope(forged, trust_store, NOW)


def test_A2_untrusted_key_is_refused_no_tofu(high_risk_card, trust_store, clock):
    """Sign with a key nobody trusts. There must be no trust-on-first-use."""
    rogue = SigningKey.generate("rogue-01", "risk_officer")
    envelope = sign_card(high_risk_card, [rogue], clock=clock)
    with pytest.raises(SignatureInvalid, match="unknown key_id"):
        verify_envelope(envelope, trust_store, NOW)


def test_A3_quorum_cannot_be_met_by_repeating_one_key(
    high_risk_card, owner_key, trust_store, clock
):
    """One compromised key must not satisfy a two-signature quorum alone."""
    env = sign_card(high_risk_card, [owner_key], clock=clock)
    env["signatures"].append(copy.deepcopy(env["signatures"][0]))
    with pytest.raises(SignatureInvalid, match="duplicate signature"):
        verify_envelope(env, trust_store, NOW)


def test_A4_backdated_signature_outside_key_validity_is_refused(
    high_risk_card, owner_key, risk_key
):
    store = TrustStore.from_keys(
        [owner_key, risk_key],
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        UNTIL,
    )
    old = FrozenClock(datetime(2026, 2, 1, tzinfo=timezone.utc))
    env = sign_card(high_risk_card, [owner_key, risk_key], clock=old)
    with pytest.raises(SignatureInvalid):
        verify_envelope(env, store, NOW)


def test_A5_future_dated_signature_is_refused(high_risk_card, owner_key, risk_key, trust_store):
    future = FrozenClock(NOW + timedelta(days=30))
    env = sign_card(high_risk_card, [owner_key, risk_key], clock=future)
    with pytest.raises(SignatureInvalid, match="future"):
        verify_envelope(env, trust_store, NOW)


def test_A6_alg_confusion_is_refused(high_risk_card, owner_key, risk_key, trust_store, clock):
    """Claim a different algorithm; there must be no negotiation."""
    env = sign_card(high_risk_card, [owner_key, risk_key], clock=clock)
    env["signatures"][0]["alg"] = "none"
    with pytest.raises(SignatureInvalid, match="unsupported signature algorithm"):
        verify_envelope(env, trust_store, NOW)


def test_A7_empty_signature_list_is_refused_not_treated_as_ok(
    high_risk_card, trust_store
):
    env = {"schema": "governed-edge-ai/signed-card/v1", "card": high_risk_card,
           "signatures": []}
    with pytest.raises(SignatureInvalid, match="no signatures"):
        verify_envelope(env, trust_store, NOW)


def test_A8_signed_at_mismatch_between_envelope_and_tbs_is_refused(
    high_risk_card, owner_key, risk_key, trust_store, clock
):
    """signed_at is inside the signed payload; moving it must break the signature."""
    env = sign_card(high_risk_card, [owner_key, risk_key], clock=clock)
    env["signatures"][0]["signed_at"] = "2026-08-21T08:59:59Z"
    with pytest.raises(SignatureInvalid, match="does not verify"):
        verify_envelope(env, trust_store, NOW)


def test_A9_key_id_swap_between_two_valid_signatures_is_refused(
    high_risk_card, owner_key, risk_key, trust_store, clock
):
    """key_id is bound into the signed payload, so swapping must not verify."""
    env = sign_card(high_risk_card, [owner_key, risk_key], clock=clock)
    env["signatures"][0]["key_id"], env["signatures"][1]["key_id"] = (
        env["signatures"][1]["key_id"], env["signatures"][0]["key_id"],
    )
    with pytest.raises(SignatureInvalid):
        verify_envelope(env, trust_store, NOW)


# ------------------------------------------------------------------ journal

def _mk_journal(tmp_path, device_key, clock, n=6):
    p = tmp_path / "j.jsonl"
    j = Journal(str(p), device_id="sim-01", device_key=device_key, clock=clock)
    j.append("session_open", {"n": 0})
    for i in range(1, n):
        j.append("policy_decision", {"n": i, "effect": "deny"})
    return p, j


def test_B1_reordering_two_entries_is_detected(tmp_path, device_key, clock):
    p, _ = _mk_journal(tmp_path, device_key, clock)
    lines = p.read_text().splitlines()
    lines[2], lines[3] = lines[3], lines[2]
    p.write_text("\n".join(lines) + "\n")
    rep = verify_journal(str(p))
    assert not rep.ok


def test_B2_deleting_a_middle_entry_is_detected(tmp_path, device_key, clock):
    p, _ = _mk_journal(tmp_path, device_key, clock)
    lines = p.read_text().splitlines()
    del lines[3]
    p.write_text("\n".join(lines) + "\n")
    rep = verify_journal(str(p))
    assert not rep.ok


def test_B3_flipping_deny_to_allow_is_detected(tmp_path, device_key, clock):
    p, _ = _mk_journal(tmp_path, device_key, clock)
    lines = [json.loads(x) for x in p.read_text().splitlines()]
    for r in lines:
        if r["body"].get("effect") == "deny":
            r["body"]["effect"] = "allow"
            break
    p.write_text("".join(
        json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in lines))
    rep = verify_journal(str(p))
    assert not rep.ok


def test_B4_KNOWN_LIMIT_full_rewrite_with_the_device_key_verifies(
    tmp_path, device_key, clock
):
    """ADR 0007: anyone holding the device key can rewrite consistently.

    This test PASSES to document the limitation. If it ever fails, the threat
    model changed and the ADR needs revisiting.
    """
    p, _ = _mk_journal(tmp_path, device_key, clock)
    p2 = tmp_path / "rewritten.jsonl"
    j2 = Journal(str(p2), device_id="sim-01", device_key=device_key, clock=clock)
    j2.append("session_open", {"n": 0})
    j2.append("policy_decision", {"n": 1, "effect": "allow"})  # was deny
    rep = verify_journal(str(p2))
    assert rep.ok, "a consistent forgery by the key holder is undetectable from the file"


def test_B5_garbage_line_does_not_crash_the_verifier(tmp_path, device_key, clock):
    p, _ = _mk_journal(tmp_path, device_key, clock)
    with p.open("a") as fh:
        fh.write("}{ not json at all\n")
    rep = verify_journal(str(p))
    assert not rep.ok


def test_B6_enormous_line_does_not_hang_the_verifier(tmp_path, device_key, clock):
    p, _ = _mk_journal(tmp_path, device_key, clock)
    with p.open("a") as fh:
        fh.write(json.dumps({"body": {"x": "A" * 2_000_000}}) + "\n")
    rep = verify_journal(str(p))
    assert not rep.ok


# ---------------------------------------------------------------- canonical

def test_C1_duplicate_json_keys_cannot_produce_two_readings(tmp_path):
    """Duplicate keys in raw JSON: last-wins in Python. Confirm it is not
    silently accepted as two different digests for the same bytes."""
    a = json.loads('{"x": 1, "x": 2}')
    assert a == {"x": 2}
    assert digest(a) == digest({"x": 2})


def test_C2_nan_and_infinity_are_refused(tmp_path):
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises((ValueError, TypeError)):
            canonical_bytes({"v": bad})


def test_C3_key_order_does_not_change_the_digest():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_C4_unicode_is_not_normalised_away():
    """Two different code-point sequences must not collide."""
    assert digest({"k": "é"}) != digest({"k": "é"})
