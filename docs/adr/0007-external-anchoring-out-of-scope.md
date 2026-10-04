# ADR 0007, External anchoring is out of scope (accepted gap)

**Status:** accepted · 2026-08-21

## Context

Hash chaining detects edits, deletions, and reordering by anyone who does not
re-derive the whole chain. It does not stop someone with the device key and
write access from rewriting the file consistently from genesis. It also does not
detect truncation of the tail: dropping the last k entries leaves a chain that
verifies.

## Decision

`Journal.checkpoint()` produces exactly the artefact that would close this gap,
a range, a Merkle root, a chain head, and a signature, carrying no payload, so
it can be published without disclosing anything. Transmitting it to a witness is
deliberately not implemented.

## Rationale

Anchoring is an infrastructure decision, not a device decision: the choice of
witness (a second device, a corporate log service, a transparency log, a
notarisation service) belongs to whoever operates the fleet, and baking one in
would make the wrong choice on their behalf.

## Consequence

Until checkpoints leave the device, the truncation window is "everything since
the last checkpoint". `test_truncation_is_detected_only_against_a_checkpoint`
pins that limitation explicitly rather than leaving it to be discovered.
