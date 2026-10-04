"""Append-only, hash-chained inference journal.

AI Act Article 12 requires high-risk systems to record events automatically
over their lifetime; ISO/IEC 27001 A.8.15 requires logs to be protected against
alteration. The usual implementation of both is a log file that anyone with
root can edit. This one makes alteration *detectable*: each entry commits to
the hash of its predecessor, and periodic checkpoints commit a Merkle root
signed by the device key.

What this buys and what it does not:

* It buys **tamper evidence**. An edited, deleted, or reordered record breaks
  the chain at a determinate sequence number, and :func:`verify_journal` names
  it.
* It does **not** buy tamper *resistance*. An attacker with the device key and
  write access can rewrite the whole file consistently. Countering that needs
  an external anchor (shipping checkpoint roots off-device to a witness) which
  :meth:`Journal.checkpoint` produces but this module deliberately does not
  transmit. See ADR 0007.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Iterator

from ..canonical import canonical_bytes, digest
from ..clock import Clock, SystemClock, iso
from ..errors import JournalIntegrityError
from ..registry.signing import SigningKey, TrustStore, b64decode, b64encode
from .merkle import merkle_root

GENESIS_HASH = "sha256:" + "00" * 32
RECORD_SCHEMA = "governed-edge-ai/journal-record/v1"

#: Record kinds. Closed set: an unknown kind is an integrity failure, because
#: a log you cannot enumerate is a log you cannot report against.
KINDS = (
    "session_open",
    "admission",
    "inference",
    "policy_decision",
    "actuation",
    "oversight",
    "stop",
    "checkpoint",
    "session_close",
)


@dataclass(frozen=True)
class Entry:
    seq: int
    timestamp: str
    kind: str
    prev_hash: str
    body: dict[str, Any]
    hash: str

    @staticmethod
    def compute_hash(
        seq: int, timestamp: str, kind: str, prev_hash: str, body: dict[str, Any]
    ) -> str:
        return digest(
            {
                "schema": RECORD_SCHEMA,
                "seq": seq,
                "timestamp": timestamp,
                "kind": kind,
                "prev_hash": prev_hash,
                "body": body,
            }
        )

    def to_line(self) -> str:
        return canonical_bytes(
            {
                "schema": RECORD_SCHEMA,
                "seq": self.seq,
                "timestamp": self.timestamp,
                "kind": self.kind,
                "prev_hash": self.prev_hash,
                "body": self.body,
                "hash": self.hash,
            }
        ).decode("utf-8")

    @classmethod
    def from_obj(cls, obj: Any) -> "Entry":
        if not isinstance(obj, dict):
            raise JournalIntegrityError("journal line is not an object")
        for field in ("schema", "seq", "timestamp", "kind", "prev_hash", "body", "hash"):
            if field not in obj:
                raise JournalIntegrityError(f"journal line missing {field!r}")
        if obj["schema"] != RECORD_SCHEMA:
            raise JournalIntegrityError(f"unknown record schema: {obj['schema']!r}")
        return cls(
            seq=obj["seq"],
            timestamp=obj["timestamp"],
            kind=obj["kind"],
            prev_hash=obj["prev_hash"],
            body=obj["body"],
            hash=obj["hash"],
        )


class Journal:
    """Append-only journal backed by a JSON Lines file.

    Durability is deliberate: each append is flushed and ``fsync``-ed before the
    call returns. An inference whose journal entry is still in a page cache when
    the device loses power did not happen, as far as the evidence is concerned,
    and a governance system that loses its own evidence under exactly the
    conditions that produce incidents is worse than none.
    """

    def __init__(
        self,
        path: str,
        *,
        device_id: str,
        clock: Clock | None = None,
        device_key: SigningKey | None = None,
        fsync: bool = True,
    ) -> None:
        self.path = path
        self.device_id = device_id
        self.clock = clock or SystemClock()
        self.device_key = device_key
        self._fsync = fsync
        self._lock = threading.Lock()
        self._seq = -1
        self._last_hash = GENESIS_HASH
        self._pending: list[str] = []          # entry hashes since last checkpoint
        self._checkpoint_from = 0

        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        if os.path.exists(path):
            self._resume()

    # ------------------------------------------------------------------ resume
    def _resume(self) -> None:
        """Reload chain state, refusing to append to a journal that is broken."""
        report = verify_journal(self.path)
        if not report.ok:
            raise JournalIntegrityError(
                f"refusing to append to a journal that fails verification: "
                f"{'; '.join(report.reasons)}"
            )
        if report.entries == 0:
            return
        entries = list(read_journal(self.path))
        self._seq = entries[-1].seq
        self._last_hash = entries[-1].hash
        last_checkpoint = max(
            (e.seq for e in entries if e.kind == "checkpoint"), default=None
        )
        start = 0 if last_checkpoint is None else last_checkpoint + 1
        self._checkpoint_from = start
        self._pending = [e.hash for e in entries if e.seq >= start]

    # ------------------------------------------------------------------ append
    def append(self, kind: str, body: dict[str, Any]) -> Entry:
        """Append one record and return it."""
        if kind not in KINDS:
            raise JournalIntegrityError(f"unknown record kind: {kind!r}")
        with self._lock:
            return self._append_locked(kind, body)

    def _append_locked(self, kind: str, body: dict[str, Any]) -> Entry:
        seq = self._seq + 1
        timestamp = iso(self.clock.now())
        entry_hash = Entry.compute_hash(seq, timestamp, kind, self._last_hash, body)
        entry = Entry(
            seq=seq,
            timestamp=timestamp,
            kind=kind,
            prev_hash=self._last_hash,
            body=body,
            hash=entry_hash,
        )
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(entry.to_line() + "\n")
            handle.flush()
            if self._fsync:
                os.fsync(handle.fileno())
        self._seq = seq
        self._last_hash = entry_hash
        self._pending.append(entry_hash)
        return entry

    # -------------------------------------------------------------- checkpoint
    def checkpoint(self) -> Entry:
        """Seal every record since the last checkpoint under a signed root.

        The returned record is the artefact you would ship to an external
        witness. It contains no payload, only a range, a root, and a signature
, so it can be published without disclosing what the device inferred.
        """
        with self._lock:
            covers_from = self._checkpoint_from
            covers_to = self._seq
            root = merkle_root(self._pending)
            body: dict[str, Any] = {
                "device_id": self.device_id,
                "covers": {"from": covers_from, "to": covers_to},
                "entry_count": len(self._pending),
                "merkle_root": root,
                "chain_head": self._last_hash,
            }
            if self.device_key is not None:
                signature = self.device_key.private_key.sign(canonical_bytes(body))
                body = {
                    **body,
                    "signature": {
                        "key_id": self.device_key.key_id,
                        "alg": "ed25519",
                        "value": b64encode(signature),
                    },
                }
            entry = self._append_locked("checkpoint", body)
            self._pending = []
            self._checkpoint_from = entry.seq + 1
            return entry

    # ------------------------------------------------------------------ status
    @property
    def head(self) -> str:
        return self._last_hash

    @property
    def length(self) -> int:
        return self._seq + 1


def read_journal(path: str) -> Iterator[Entry]:
    """Yield entries from a journal file, in file order."""
    try:
        # noqa justified: the open must be guarded on its own so an OSError
        # becomes a stated refusal before the with-block; the handle is closed
        # by the `with` immediately below.
        handle = open(path, "r", encoding="utf-8")  # noqa: SIM115
    except OSError as exc:
        # A directory, a broken symlink, a permission problem. An auditor who
        # points the verifier at the wrong path gets a refusal with the reason,
        # not a stack trace: a tool that crashes has not verified anything, and
        # should not look like it fell over rather than found something.
        raise JournalIntegrityError(f"cannot read journal: {exc}") from exc
    with handle:
        line_number = 0
        while True:
            try:
                line = handle.readline()
            except UnicodeDecodeError as exc:
                # Not a text file at all. Same argument as above.
                raise JournalIntegrityError(
                    f"journal is not UTF-8 text at line {line_number + 1}: {exc}"
                ) from exc
            if not line:
                break
            line_number += 1
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JournalIntegrityError(
                    f"line {line_number} is not valid JSON: {exc}"
                ) from exc
            yield Entry.from_obj(obj)


@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    entries: int
    checkpoints: int
    head: str
    broken_at: int | None = None
    reasons: tuple[str, ...] = ()

    def summary(self) -> str:
        if self.ok:
            return (
                f"journal verified: {self.entries} entries, "
                f"{self.checkpoints} checkpoint(s), head {self.head[:19]}…"
            )
        return f"journal FAILED at seq {self.broken_at}: {'; '.join(self.reasons)}"


def verify_journal(path: str, trust_store: TrustStore | None = None) -> VerificationReport:
    """Independently re-derive the chain and, optionally, checkpoint signatures.

    This function shares no state with :class:`Journal`. That is the point: an
    auditor runs it against a file, on their own machine, with their own copy of
    the trust store.
    """
    if not os.path.exists(path):
        return VerificationReport(
            ok=False, entries=0, checkpoints=0, head=GENESIS_HASH,
            broken_at=None, reasons=(f"journal not found: {path}",),
        )
    if not os.path.isfile(path):
        return VerificationReport(
            ok=False, entries=0, checkpoints=0, head=GENESIS_HASH,
            broken_at=None, reasons=(f"journal path is not a file: {path}",),
        )

    expected_prev = GENESIS_HASH
    expected_seq = 0
    checkpoints = 0
    pending: list[str] = []
    head = GENESIS_HASH
    count = 0

    try:
        for entry in read_journal(path):
            if entry.seq != expected_seq:
                return VerificationReport(
                    False, count, checkpoints, head, entry.seq,
                    (f"sequence gap: expected {expected_seq}, found {entry.seq}",),
                )
            if entry.kind not in KINDS:
                return VerificationReport(
                    False, count, checkpoints, head, entry.seq,
                    (f"unknown record kind {entry.kind!r}",),
                )
            if entry.prev_hash != expected_prev:
                return VerificationReport(
                    False, count, checkpoints, head, entry.seq,
                    ("chain break: prev_hash does not match the preceding entry",),
                )
            recomputed = Entry.compute_hash(
                entry.seq, entry.timestamp, entry.kind, entry.prev_hash, entry.body
            )
            if recomputed != entry.hash:
                return VerificationReport(
                    False, count, checkpoints, head, entry.seq,
                    ("record hash does not match its content: the entry was altered",),
                )

            if entry.kind == "checkpoint":
                problem = _verify_checkpoint(entry, pending, trust_store)
                if problem:
                    return VerificationReport(
                        False, count, checkpoints, head, entry.seq, (problem,)
                    )
                checkpoints += 1
                pending = []
            else:
                pending.append(entry.hash)

            expected_prev = entry.hash
            head = entry.hash
            expected_seq += 1
            count += 1
    except JournalIntegrityError as exc:
        return VerificationReport(
            False, count, checkpoints, head, expected_seq, (str(exc),)
        )

    if count == 0:
        # An empty file and a completely erased one are the same bytes. The
        # verifier cannot tell them apart and must not affirm either: saying
        # "verified" about nothing is the manufactured assurance this project
        # exists to refuse. Detecting *which* of the two it is needs an external
        # record of the expected head, see ADR 0007.
        return VerificationReport(
            ok=False, entries=0, checkpoints=checkpoints, head=GENESIS_HASH,
            broken_at=None,
            reasons=(
                "journal is empty: nothing to verify, and an empty file is "
                "indistinguishable from an erased one",
            ),
        )
    return VerificationReport(True, count, checkpoints, head)


def _verify_checkpoint(
    entry: Entry, pending: list[str], trust_store: TrustStore | None
) -> str | None:
    body = entry.body
    covers = body.get("covers", {})
    if covers.get("to") != entry.seq - 1 and entry.seq != 0:
        return (
            f"checkpoint claims to cover up to {covers.get('to')} "
            f"but sits at seq {entry.seq}"
        )
    if body.get("entry_count") != len(pending):
        return (
            f"checkpoint claims {body.get('entry_count')} entries, "
            f"chain shows {len(pending)} since the previous checkpoint"
        )
    if body.get("merkle_root") != merkle_root(pending):
        return "checkpoint merkle_root does not match the entries it covers"

    signature = body.get("signature")
    if signature is None:
        return None if trust_store is None else "checkpoint is unsigned"
    if trust_store is None:
        return None

    key = trust_store.get(signature.get("key_id", ""))
    if key is None:
        return f"checkpoint signed by unknown key {signature.get('key_id')!r}"
    unsigned_body = {k: v for k, v in body.items() if k != "signature"}
    try:
        key.public_key.verify(b64decode(signature["value"]), canonical_bytes(unsigned_body))
    except Exception:  # noqa: BLE001 - any verification failure is the same verdict
        return f"checkpoint signature from {signature['key_id']!r} does not verify"
    return None
