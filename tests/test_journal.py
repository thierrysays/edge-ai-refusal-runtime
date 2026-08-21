"""Journal integrity tests.

Each test corresponds to a way a log gets quietly rewritten in practice:
an entry edited, an entry removed, entries reordered, a whole file replaced.
The requirement is not that these be impossible, on a Linux SBC with root
access they are not, but that they be *named* when they happen.
"""

from __future__ import annotations

import json

import pytest

from governed_edge_ai.errors import JournalIntegrityError
from governed_edge_ai.journal import (
    GENESIS_HASH,
    Journal,
    inclusion_proof,
    merkle_root,
    read_journal,
    verify_inclusion,
    verify_journal,
)
from governed_edge_ai.registry import TrustStore

from .conftest import KEY_FROM, KEY_UNTIL


def make_journal(tmp_path, clock, device_key=None, entries: int = 5) -> Journal:
    journal = Journal(
        str(tmp_path / "journal.jsonl"),
        device_id="uno-q-lab-01",
        clock=clock,
        device_key=device_key,
        fsync=False,
    )
    for index in range(entries):
        journal.append("inference", {"index": index, "verdict": "pass"})
        clock.advance(seconds=1)
    return journal


def rewrite(path: str, mutate) -> None:
    lines = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    mutated = mutate(lines)
    with open(path, "w", encoding="utf-8") as handle:
        for obj in mutated:
            handle.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")


# ------------------------------------------------------------------- happy path
def test_fresh_journal_verifies(tmp_path, clock):
    journal = make_journal(tmp_path, clock)
    report = verify_journal(journal.path)
    assert report.ok, report.summary()
    assert report.entries == 5
    assert report.head == journal.head


def test_first_entry_chains_to_genesis(tmp_path, clock):
    journal = make_journal(tmp_path, clock, entries=1)
    first = next(read_journal(journal.path))
    assert first.prev_hash == GENESIS_HASH
    assert first.seq == 0


def test_checkpoint_is_signed_and_verifies(tmp_path, clock, device_key, trust_store):
    journal = make_journal(tmp_path, clock, device_key=device_key)
    entry = journal.checkpoint()
    assert entry.body["entry_count"] == 5
    assert entry.body["signature"]["key_id"] == "device-uno-q-01"
    report = verify_journal(journal.path, trust_store)
    assert report.ok, report.summary()
    assert report.checkpoints == 1


def test_unsigned_checkpoint_is_refused_when_a_trust_store_is_supplied(
    tmp_path, clock, trust_store
):
    journal = make_journal(tmp_path, clock)  # no device key
    journal.checkpoint()
    assert verify_journal(journal.path).ok            # structurally fine
    report = verify_journal(journal.path, trust_store)  # but unattributable
    assert not report.ok
    assert "unsigned" in report.reasons[0]


# --------------------------------------------------------------------- tampering
def test_edited_entry_is_detected(tmp_path, clock):
    journal = make_journal(tmp_path, clock)

    def mutate(lines):
        lines[2]["body"]["verdict"] = "fail"   # the record everyone would change
        return lines

    rewrite(journal.path, mutate)
    report = verify_journal(journal.path)
    assert not report.ok
    assert report.broken_at == 2
    assert "altered" in report.reasons[0]


def test_edited_entry_with_recomputed_hash_still_breaks_the_chain(tmp_path, clock):
    """The half-competent tamper: fix the record's own hash, forget its successor."""
    from governed_edge_ai.journal.chain import Entry

    journal = make_journal(tmp_path, clock)

    def mutate(lines):
        lines[2]["body"]["verdict"] = "fail"
        lines[2]["hash"] = Entry.compute_hash(
            lines[2]["seq"],
            lines[2]["timestamp"],
            lines[2]["kind"],
            lines[2]["prev_hash"],
            lines[2]["body"],
        )
        return lines

    rewrite(journal.path, mutate)
    report = verify_journal(journal.path)
    assert not report.ok
    assert report.broken_at == 3
    assert "chain break" in report.reasons[0]


def test_deleted_entry_is_detected(tmp_path, clock):
    journal = make_journal(tmp_path, clock)
    rewrite(journal.path, lambda lines: lines[:2] + lines[3:])
    report = verify_journal(journal.path)
    assert not report.ok
    assert "sequence gap" in report.reasons[0]


def test_reordered_entries_are_detected(tmp_path, clock):
    journal = make_journal(tmp_path, clock)

    def mutate(lines):
        lines[1], lines[2] = lines[2], lines[1]
        return lines

    rewrite(journal.path, mutate)
    report = verify_journal(journal.path)
    assert not report.ok


def test_truncation_is_detected_only_against_a_checkpoint(tmp_path, clock, device_key, trust_store):
    """Truncating the tail of a chain leaves a *valid* shorter chain.

    This is the honest limitation of hash chaining, and the reason checkpoints
    exist: once a signed checkpoint has been published, the entries it covers
    can no longer be silently dropped.
    """
    journal = make_journal(tmp_path, clock, device_key=device_key)
    journal.checkpoint()
    clock.advance(seconds=1)
    journal.append("inference", {"index": 99, "verdict": "fail"})

    # Dropping the post-checkpoint entry is undetectable from the file alone…
    rewrite(journal.path, lambda lines: lines[:-1])
    assert verify_journal(journal.path, trust_store).ok

    # …whereas dropping entries the checkpoint commits to is not.
    rewrite(journal.path, lambda lines: lines[:3] + lines[5:])
    assert not verify_journal(journal.path, trust_store).ok


def test_forged_checkpoint_root_is_detected(tmp_path, clock, device_key, trust_store):
    journal = make_journal(tmp_path, clock, device_key=device_key)
    journal.checkpoint()

    def mutate(lines):
        from governed_edge_ai.journal.chain import Entry

        lines[-1]["body"]["merkle_root"] = "sha256:" + "ab" * 32
        lines[-1]["hash"] = Entry.compute_hash(
            lines[-1]["seq"], lines[-1]["timestamp"], lines[-1]["kind"],
            lines[-1]["prev_hash"], lines[-1]["body"],
        )
        return lines

    rewrite(journal.path, mutate)
    report = verify_journal(journal.path, trust_store)
    assert not report.ok
    assert "merkle_root" in report.reasons[0] or "signature" in report.reasons[0]


def test_checkpoint_signed_by_an_unknown_key_is_refused(tmp_path, clock, owner_key, risk_key):
    from governed_edge_ai.registry.signing import SigningKey

    rogue = SigningKey.generate("rogue-device", "operator")
    journal = make_journal(tmp_path, clock, device_key=rogue)
    journal.checkpoint()
    store = TrustStore.from_keys([owner_key, risk_key], KEY_FROM, KEY_UNTIL)
    report = verify_journal(journal.path, store)
    assert not report.ok
    assert "unknown key" in report.reasons[0]


# --------------------------------------------------------------------- behaviour
def test_reopening_a_broken_journal_refuses_to_append(tmp_path, clock):
    journal = make_journal(tmp_path, clock)
    rewrite(journal.path, lambda lines: lines[:2] + lines[3:])
    with pytest.raises(JournalIntegrityError):
        Journal(journal.path, device_id="uno-q-lab-01", clock=clock, fsync=False)


def test_reopening_a_sound_journal_continues_the_chain(tmp_path, clock, device_key):
    journal = make_journal(tmp_path, clock, device_key=device_key)
    head, length = journal.head, journal.length
    reopened = Journal(
        journal.path, device_id="uno-q-lab-01", clock=clock,
        device_key=device_key, fsync=False,
    )
    assert reopened.head == head
    assert reopened.length == length
    reopened.append("inference", {"index": 5, "verdict": "pass"})
    reopened.checkpoint()
    assert verify_journal(journal.path).ok


def test_unknown_record_kind_is_rejected_at_write_time(tmp_path, clock):
    journal = make_journal(tmp_path, clock, entries=0)
    with pytest.raises(JournalIntegrityError):
        journal.append("whatever_we_felt_like_logging", {})


def test_missing_journal_file_reports_cleanly(tmp_path):
    report = verify_journal(str(tmp_path / "absent.jsonl"))
    assert not report.ok
    assert "not found" in report.reasons[0]


def test_corrupt_line_reports_cleanly(tmp_path, clock):
    journal = make_journal(tmp_path, clock)
    with open(journal.path, "a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")
    report = verify_journal(journal.path)
    assert not report.ok
    assert "not valid JSON" in report.reasons[0]


# ------------------------------------------------------------------------ merkle
def test_inclusion_proof_round_trips():
    hashes = [f"sha256:{i:064x}" for i in range(7)]
    root = merkle_root(hashes)
    for index, entry_hash in enumerate(hashes):
        proof = inclusion_proof(hashes, index)
        assert verify_inclusion(entry_hash, proof, root)


def test_inclusion_proof_fails_for_an_absent_entry():
    hashes = [f"sha256:{i:064x}" for i in range(7)]
    root = merkle_root(hashes)
    proof = inclusion_proof(hashes, 3)
    assert not verify_inclusion(f"sha256:{99:064x}", proof, root)


def test_merkle_root_is_order_sensitive():
    a = [f"sha256:{i:064x}" for i in range(4)]
    b = [a[1], a[0], a[2], a[3]]
    assert merkle_root(a) != merkle_root(b)


def test_single_entry_root_is_not_the_bare_leaf():
    """Domain separation: a one-entry tree must not collide with its leaf."""
    from governed_edge_ai.journal.merkle import leaf_hash

    only = "sha256:" + "11" * 32
    assert merkle_root([only]) == leaf_hash(only)
    assert merkle_root([only]) != only
