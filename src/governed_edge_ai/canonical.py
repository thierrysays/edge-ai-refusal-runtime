"""Canonical serialisation and digests.

Every governance artefact in this project: model cards, journal records,
policy decisions, provenance manifests, is hashed. A hash is only as good as
the determinism of the bytes that go into it, so all serialisation goes
through this module and nowhere else.

Rules:
  * UTF-8, sorted keys, no insignificant whitespace.
  * ``NaN`` / ``Infinity`` are rejected: they are not representable in
    interoperable JSON and would make a digest unverifiable by a third party.
  * Digests are namespaced strings (``sha256:<hex>``) so the algorithm can be
    rotated without ambiguity in stored evidence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

DIGEST_ALGORITHM = "sha256"


def canonical_bytes(payload: Any) -> bytes:
    """Serialise ``payload`` to canonical JSON bytes.

    Raises:
        ValueError: if the payload contains non-finite floats.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(payload: Any) -> str:
    """Return the namespaced digest of an arbitrary JSON-serialisable payload."""
    return digest_bytes(canonical_bytes(payload))


def digest_bytes(raw: bytes) -> str:
    """Return the namespaced digest of raw bytes (e.g. a model weights file)."""
    return f"{DIGEST_ALGORITHM}:{hashlib.sha256(raw).hexdigest()}"


def digest_file(path: str, chunk_size: int = 1 << 20) -> str:
    """Digest a file without loading it into memory.

    Model artefacts on a VENTUNO Q can be hundreds of megabytes; the admission
    gate must be able to verify them on the device itself.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            hasher.update(chunk)
    return f"{DIGEST_ALGORITHM}:{hasher.hexdigest()}"


def is_digest(value: object) -> bool:
    """True if ``value`` looks like a well-formed namespaced sha256 digest."""
    if not isinstance(value, str):
        return False
    prefix, _, hexpart = value.partition(":")
    if prefix != DIGEST_ALGORITHM or len(hexpart) != 64:
        return False
    return all(c in "0123456789abcdef" for c in hexpart)
