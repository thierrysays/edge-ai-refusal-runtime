# Functional specification

What the system does, for whom, and what counts as it working. Written so that
someone who will never read the source can tell whether a claim made about this
runtime is true.

The technical counterpart is [TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md).

---

## Purpose

Mediate every actuation an AI system requests, so that each one is either
performed and recorded, or refused and recorded. The system produces **evidence
of refusal**. That is the deliverable; the demonstration is a means of showing
it.

Explicitly **not** in scope: deciding whether a model is accurate, certifying
compliance, or replacing a safety case.

## Actors

| Actor | Does | Cannot |
|---|---|---|
| **Model provider** | Writes the model card, signs it as `model_owner` | Admit a high-risk model alone; opt out of a tier baseline by omission |
| **Risk officer** | Countersigns high-risk cards | Be substituted by a second `model_owner` signature |
| **Operator** | Releases the stop channel by name; answers escalations | Release the stop anonymously or as `"unattended"` |
| **The agent** | Requests actuations with a stated rationale | Perform anything the policy does not allow; release its own stop; approve its own escalation |
| **Auditor** | Runs `gea verify` against a journal file | Be required to trust the device that wrote it |

The separation that matters: **the party that asks for an action is never the
party that authorises it**, and neither is the party that records it.

## Preconditions

A device may run a model only if all of these hold. Each is a check with a name,
recorded in the journal.

1. The card verifies against the trust store, at the required quorum for its
   risk tier.
2. The card is inside its validity window.
3. The card names this device class among its deployment targets.
4. The artefact on disk digests to the value the card binds.
5. Every control the card's tier or text requires is one this device class can
   enforce.

Any failure is a refusal. **A missing artefact is a failed check, not a skipped
one.**

---

## Functional requirements

### FR-1 — Nothing runs before its paperwork

An unsigned, under-signed, expired, mis-targeted or unbindable card is refused,
and the refusal is journalled with the failing check named.

*Verified by* `tests/test_registry_admission.py`.

### FR-2 — The stop channel starts engaged

On boot the relay is de-energised. The first actuation request of a session is
refused unless a named operator has released the stop. `""` and `"unattended"`
are not names.

*Verified by* `test_registry_admission.py -k stop_channel`, and by the
demonstration, whose first refusal is `start_attempt_before_release`.

### FR-3 — Default deny

An actuation matching no allow rule is denied. Rules are JSON data, versioned
and diffable, so what was in force on a given date is a question with an answer.

*Verified by* `tests/test_policy.py`.

### FR-4 — Escalation is not permission

Where policy says `require_human`, the action proceeds only on an affirmative
answer from a named operator. The default confirmer refuses. Silence is a
refusal.

*Verified by* `tests/test_oversight_and_marking.py`.

### FR-5 — Budgets bound the legitimate

Individually-permitted actions repeated past an allocation are refused, and
exhaustion **engages the stop channel** rather than merely declining the next
request.

*Verified by* `tests/test_policy.py`.

### FR-6 — Every outcome is journalled

Allow, deny, escalate, stop and actuate all append a hash-chained record.
Refusals are recorded with the same weight as actions — a governance log that
records only what happened cannot answer what was prevented.

### FR-7 — Evidence verifies without the device

`gea verify` re-derives the chain from the file alone. It shares no state with
the writer. It names the sequence number at which a chain was altered, deleted
or reordered.

*Verified by* `tests/test_journal.py`, `make tamper`.

### FR-8 — Synthetic output is marked

Where a card declares it, each output gets a detached provenance manifest
carrying digests rather than payloads, so provenance can be published without
disclosing the input. (AI Act Article 50, applicable since 2 August 2026.)

### FR-9 — Refusal survives adversarial pressure

Signature transplant, key substitution, quorum-by-repetition, algorithm
confusion, backdating, chain reordering and canonicalisation collisions are all
refused.

*Verified by* `tests/test_adversarial.py`.

---

## Acceptance criteria

The build is good when all of these hold. CI enforces every one.

| # | Criterion | Check |
|---|---|---|
| A1 | The suite passes on Python 3.10, 3.11, 3.12 | `pytest` |
| A2 | The demonstration refuses **4** and escalates **1** | `gea demo` |
| A3 | The journal it produced verifies | `gea verify` |
| A4 | A tampered journal fails, naming the sequence number | `make tamper` |
| A5 | Lint, strict typing and SAST are clean | `make lint typecheck security` |
| A6 | Coverage does not fall below the gate | `make cover` |
| A7 | No dependency carries a known advisory | `pip-audit` |

**A2 is not a snapshot to be updated.** If the count changes, a control changed
behaviour. Fix the control or write the ADR; do not adjust the expected number.

---

## Regulatory mapping

Full detail, with the test that proves each row, in
[CONTROL_MAP.md](CONTROL_MAP.md).

| Obligation | Status as of August 2026 | Implemented as |
|---|---|---|
| AI Act Art. 50 — marking of synthetic output | **Applicable since 2 August 2026** | `marking/` |
| AI Act Art. 12 — automatic logging | Annex III duties deferred to 2 December 2027 | `journal/` |
| AI Act Art. 14 — human oversight | Same deferral | `oversight/` |
| AI Act Annex IV — technical documentation | Same deferral | signed model card |
| ISO/IEC 42001 — AI management system | In force | card as the system record |
| ISO/IEC 27001 A.8.15 — log protection | In force | hash chain + signed checkpoints |

A deferred date defers the obligation, not the design cost. Retrofitting a stop
channel into a deployed fleet is roughly the eighteen months that remain.

---

## Limits

These belong in any honest description of the system.

- **Tamper-evident, not tamper-resistant.** A holder of the device key can
  rewrite the journal consistently. → ADR 0007
- **No hardware root of trust.** Keys sit in the clear. → ADR 0006
- **`SimulatedModel` is a stand-in**, not a detector.
- **Nothing has run on hardware.** Every device backend but the simulator raises
  `NotPortedError`. The stop channel has never held a relay.
- **Not a compliance certificate.** Nothing here certifies anything.
