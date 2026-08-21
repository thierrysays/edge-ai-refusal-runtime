# ADR 0003 — A hash-chained file, not a database

**Status:** accepted · 2026-08-21

## Context

Article 12 requires automatic recording of events over the system's lifetime;
ISO 27001 A.8.15 requires log protection against alteration. The default
implementation of both is a table anyone with credentials can update.

## Decision

An append-only JSON Lines file where each entry commits to the hash of its
predecessor, with periodic Merkle checkpoints signed by the device key.
Verification is a separate function sharing no state with the writer.

## Alternatives rejected

- *A database with an audit trigger.* Requires trusting the same administrator
  who would be the subject of the audit, and does not travel: an auditor cannot
  be handed a Postgres instance.
- *Append-only cloud storage.* Correct for a fleet, unavailable on a device that
  may be offline, and it moves the trust anchor to a vendor rather than removing
  the need for one.

## Cost

Verification is O(n) in the file. Every append is `fsync`-ed, which caps write
throughput at roughly the device's sync rate — acceptable at inference cadence,
not at sensor cadence. High-rate telemetry belongs elsewhere; this journal is
for governance events.
