# Technical reference

What each module is, what it refuses, and the exact shape of every artefact it
writes. [ARCHITECTURE.md](ARCHITECTURE.md) argues *why* the controls are ordered
as they are; this file is the part you need open while writing code against
them.

Package `governed_edge_ai`, distribution `edge-ai-refusal-runtime`. The two
names differ on purpose, [ADR 0010](adr/0010-repository-name-and-frozen-schema-ids.md).

---

## Foundations

### `canonical.py`

Every digest in this repository is produced here or nowhere. Serialisation is
JSON with sorted keys, `(",", ":")` separators, `ensure_ascii=False`, and
`allow_nan=False`.

| Function | Returns | Refuses |
|---|---|---|
| `canonical_bytes(payload)` | `bytes` | NaN, ±Infinity, a digest over a value that does not round-trip is not a digest |
| `digest(payload)` | `"sha256:<64 hex>"` | as above |
| `digest_bytes(raw)` | `"sha256:<64 hex>"` |, |
| `digest_file(path, chunk_size=1MiB)` | `"sha256:<64 hex>"` |, streams, so a model artefact never has to fit in memory |
| `is_digest(value)` | `bool` |, |

Key order does not affect the digest; Unicode is **not** normalised, so two
distinct code-point sequences that render identically produce different digests.
That is deliberate: silently folding them would let two different cards share
one signature.

### `clock.py`

`Clock` protocol with `SystemClock` and `FrozenClock`. Nothing in the package
calls `datetime.now()` directly. Evidence has to be reproducible, and a control
whose behaviour depends on wall-clock time cannot be tested at its boundary.

### `errors.py`

One exception per governance failure mode, each with a stable `code`, the code
is what a fleet operator greps for, so it is API.

`ConfigurationError` · `SignatureInvalid` · `AdmissionRefused` ·
`PolicyViolation` · `BudgetExhausted` · `StopEngaged` · `JournalIntegrityError` ·
`NotPortedError`

---

## `registry/`: the admission gate

### Model card (`schema.py`)

Schema id `governed-edge-ai/model-card/v1`. Required top-level fields include
`model_id`, `version`, `artifact_digest`, `risk_tier`, `intended_purpose`,
`provider`, `deployment`, `evaluation`, `oversight`, `transparency`,
`valid_from`, `valid_until`.

Risk tiers: `minimal`, `limited`, `high`.

| Tier | Baseline controls | Signer quorum |
|---|---|---|
| `minimal` | none | 1 |
| `limited` | `output_marking` | 1 |
| `high` | `inference_journal`, `policy_mediation`, `stop_channel`, `output_marking` | 2 distinct roles, one of them `risk_officer` |

`effective_controls(card)` returns **baseline ∪ requested**, plus
`output_marking` if the card marks synthetic output and `human_confirmation` if
it declares a human in the loop. The union, never the intersection: a provider
cannot obtain fewer controls by asking for fewer.

Known controls: `inference_journal`, `policy_mediation`, `stop_channel`,
`output_marking`, `human_confirmation`. A card demanding anything else fails
closed.

### Signing (`signing.py`)

Ed25519 only. There is no algorithm negotiation, and `alg` values other than
`"ed25519"` are refused rather than defaulted.

The signed payload is **not** the card. It is
```json
{"schema": "governed-edge-ai/tbs/v1",
 "card_digest": "sha256:…", "key_id": "…", "signed_at": "…Z"}
```
Binding `card_digest`, `key_id` and `signed_at` together is what makes a
signature non-transplantable between cards and non-replayable under another
identity.

`TrustStore` is a closed set loaded from a file. No discovery, no
key-from-the-envelope fallback, no trust-on-first-use. Roles are resolved from
the store at verification time and never read from the envelope, so an envelope
cannot promote its own signer.

`verify_envelope(envelope, trust_store, now)` refuses: an unknown `key_id`; a
duplicate `key_id` across signatures (otherwise one compromised key satisfies a
quorum alone); a signature dated in the future; a signature outside the key's
validity window; a key revoked as of `now`; and any signature that does not
verify. It raises on a malformed envelope rather than returning an empty list,
so a caller cannot confuse *nothing signed this* with *this is not an envelope*.

### `admit()` (`admission.py`)

Eight named checks, each recorded pass/fail in the returned
`AdmissionDecision` and written to the journal:

`signatures_verify` · `card_structure` · `signer_quorum` ·
`risk_officer_signature` · `card_in_validity_window` · `deployment_target` ·
`artifact_binding` · `controls_enforceable`

A missing artefact is a **failed** check, never a skipped one.

---

## `journal/`: tamper-evident record

### Record format (`chain.py`)

One JSON object per line, schema `governed-edge-ai/journal-record/v1`:

```json
{"seq": 0, "timestamp": "…Z", "kind": "session_open",
 "prev_hash": "sha256:000…0", "hash": "sha256:…", "body": {…},
 "schema": "governed-edge-ai/journal-record/v1"}
```

`hash = sha256(canonical_bytes({seq, timestamp, kind, prev_hash, body}))`.
Genesis `prev_hash` is 64 zeros.

Kinds: `session_open`, `admission`, `inference`, `policy_decision`,
`actuation`, `oversight`, `stop`, `checkpoint`, `session_close`.

**Bodies carry digests, never payloads.** A technical file retained for five
years under the CRA must not contain the images.

Every append is flushed and `fsync`-ed before the call returns. An inference
whose record is still in a page cache when the device loses power did not
happen, as far as the evidence is concerned.

### `verify_journal(path, trust_store=None)`

Shares no state with `Journal`. An auditor runs it against a file on their own
machine. Returns a `VerificationReport`; the CLI exits `0` on `ok`, `1`
otherwise.

Detects: sequence gaps, unknown record kinds, chain breaks, altered record
bodies, bad checkpoint roots, invalid checkpoint signatures, malformed JSON,
non-UTF-8 content, a path that is not a file, and an **empty file**.

An empty journal is reported as a failure, not as `verified: 0 entries`. An
erased journal and a never-written one are the same bytes, and affirming either
would be the manufactured assurance this project exists to refuse. Telling them
apart needs an external record of the expected head, [ADR 0007](adr/0007-external-anchoring-out-of-scope.md).

Does **not** detect: a consistent rewrite by a holder of the device key, or
truncation after the last checkpoint. Both are accepted limitations with tests
that pin them.

### Checkpoints (`merkle.py`)

A `checkpoint` record carries a Merkle root over the hashes appended since the
previous checkpoint, signed with the device key when one is configured.

---

## `policy/`: default deny

Rules are JSON data (`policies/*.json`, schema `governed-edge-ai/policy/v1`), so
a risk officer can diff what was in force on a given date. **Do not replace a
rule with a Python callable.**

`decide(request)` returns a `Decision` with `effect` ∈ `allow` · `deny` ·
`require_human`, the rules matched, and human-readable reasons. **No matching
allow rule means deny.**

Numeric comparisons (`gt`, `gte`, `lt`, `lte`) exclude `bool` on both sides.
`True < 1.0` is true in Python and must not be true in a policy.

`budget.py` tracks allocations over an optional window. Exhaustion raises
`BudgetExhausted` **and engages the stop channel**, [ADR 0008](adr/0008-budget-exhaustion-engages-the-stop.md).

---

## `oversight/`: stop and confirmation

`SimulatedRelay` boots **de-energised**, so the stop channel starts engaged.
Releasing requires a named operator; `""` and `"unattended"` are rejected.

`CompositeStopChannel` is engaged if **any** member is engaged.

Confirmers implement `confirm(request_summary, reasons) -> (approved, operator_id)`.
The default is `AbsentOperator`, which refuses. An escalation nobody answers is
a refusal, never a permission, [ADR 0009](adr/0009-silence-is-refusal.md).

---

## `marking/`: AI Act Article 50

Produces a **detached** provenance manifest (`governed-edge-ai/provenance/v1`)
carrying `input_digest`, `output_digest`, `model_id`, `model_version`,
`card_digest`, and disclosure text, digests, so provenance can be published
without disclosing the input.

The manifest must **not** carry the hash of the journal entry that records the
manifest's digest; that is uncomputable. The link runs journal → manifest, one
way only.

---

## `hal/`: devices

`DeviceProfile` declares `available_controls`, what a device class **can**
enforce, which is what the admission gate needs. It is **not** a job assignment;
see the module docstring.

| Class | Controls | Note |
|---|---|---|
| `uno-q` | all five | Debian, durable filesystem |
| `ventuno-q` | all five | STM32H5 on Zephyr for actuation |
| `uno-r4-wifi` | four, **not** `inference_journal` | no durable append-only storage, so a high-risk card is refused |
| `alvik` | `policy_mediation`, `stop_channel` | the actuated system |
| `nesso-n1` | `human_confirmation`, `stop_channel` | LoRa oversight console |

Unported backends raise `NotPortedError` with a specific porting note. Every
`energy_model` is labelled `estimate` until a bench measurement replaces it.

---

## `agent/runtime.py`: the order

`GovernedRuntime.act(request)` runs, and the order is load-bearing:

1. **stop channel**: before the request is evaluated at all
2. **policy**: default deny
3. **human oversight**: only if policy said `require_human`
4. **budgets**: last, so a concurrent spend cannot overtake the check
5. **actuation**: via the HAL

Every branch writes to the journal, including every refusal.

---

## CLI

```
gea demo        run the deterministic inspection scenario
gea verify      verify a journal independently
gea keygen      generate an Ed25519 signing key
gea truststore  build a trust store from key files
gea sign        sign a model card
gea admit       run the admission gate
gea devices     list device profiles and their controls
gea policy      load a policy and print its rules
```

Exit codes: `0` success, `1` a refusal or a failed verification.

---

## Extending it

- **A new control**: add to `KNOWN_CONTROLS`, to the device profiles that can
  enforce it, to `TIER_BASELINE` if a tier implies it, and add a row to
  [CONTROL_MAP.md](CONTROL_MAP.md) with the test that proves it refuses.
- **A new rule**: JSON in `policies/`. Never a callable.
- **A new board**: a `DeviceProfile` plus an unported backend with a porting
  note. Conservative by default, claim a control only once it is demonstrated
  on the bench, and say so in the build log.
- **A new record kind**: add to `KINDS`, or `verify_journal` rejects it.
- **A schema identifier**: never change an existing one. → ADR 0010.
