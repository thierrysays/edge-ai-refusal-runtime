"""Binary Merkle tree over journal entry hashes.

Why a Merkle root on top of an already-chained log: the chain proves *order and
completeness* to whoever holds the whole file, but an auditor rarely wants the
whole file — they want to prove that one specific inference happened, without
being handed every other inference the device ever made. The root lets a single
record be proven against a signed checkpoint with a logarithmic proof, which is
the difference between disclosing an event and disclosing a database.

Second-preimage resistance: leaves and internal nodes are domain-separated
with distinct prefixes, so a proof cannot be reinterpreted at the wrong level.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"

EMPTY_ROOT = "sha256:" + "00" * 32


def _h(prefix: bytes, *parts: bytes) -> str:
    hasher = hashlib.sha256()
    hasher.update(prefix)
    for part in parts:
        hasher.update(part)
    return f"sha256:{hasher.hexdigest()}"


def leaf_hash(entry_hash: str) -> str:
    return _h(LEAF_PREFIX, entry_hash.encode("utf-8"))


def node_hash(left: str, right: str) -> str:
    return _h(NODE_PREFIX, left.encode("utf-8"), right.encode("utf-8"))


def merkle_root(entry_hashes: Sequence[str]) -> str:
    """Root over a sequence of entry hashes. Empty input yields ``EMPTY_ROOT``."""
    if not entry_hashes:
        return EMPTY_ROOT
    level = [leaf_hash(h) for h in entry_hashes]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])  # duplicate the last node for odd levels
        level = [node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def inclusion_proof(entry_hashes: Sequence[str], index: int) -> list[tuple[str, str]]:
    """Sibling path proving ``entry_hashes[index]`` is under :func:`merkle_root`.

    Returns a list of ``(side, hash)`` where ``side`` is ``"left"`` or
    ``"right"`` describing where the sibling sits.
    """
    if not 0 <= index < len(entry_hashes):
        raise IndexError(f"index {index} out of range for {len(entry_hashes)} entries")
    level = [leaf_hash(h) for h in entry_hashes]
    proof: list[tuple[str, str]] = []
    position = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        sibling = position ^ 1
        side = "left" if sibling < position else "right"
        proof.append((side, level[sibling]))
        level = [node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        position //= 2
    return proof


def verify_inclusion(entry_hash: str, proof: Sequence[tuple[str, str]], root: str) -> bool:
    """Recompute a root from a leaf and its sibling path."""
    current = leaf_hash(entry_hash)
    for side, sibling in proof:
        if side == "left":
            current = node_hash(sibling, current)
        elif side == "right":
            current = node_hash(current, sibling)
        else:
            return False
    return current == root
