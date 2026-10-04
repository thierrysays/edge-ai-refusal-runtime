# Threat model

Who this defends against, who it does not, and where the line is. Written after
an adversarial review on 21 August 2026 whose tests live in
`tests/test_adversarial.py`: every claim below is either pinned by one of them
or listed as residual.

---

## Assets

| Asset | Why it is worth attacking |
|---|---|
| The **signing keys** | Whoever holds them admits models and forges journals |
| The **trust store** | Adding a key admits anything signed by it |
| The **journal** | It is the evidence; altering it changes what is known to have happened |
| The **policy file** | It decides what is permitted |
| The **stop channel state** | Releasing it removes every other control's last resort |
| The **model artefact** | Substituting it runs different code under an admitted card |

## Adversaries

| # | Adversary | Capability assumed |
|---|---|---|
| **A1** | A misbehaving model or agent | Can request any actuation, with any parameters and rationale |
| **A2** | A rushed insider | Can edit files the process can write; wants the line running tonight |
| **A3** | A remote attacker with file write | Can alter the journal, policy or trust store on disk |
| **A4** | A supplier | Writes the model card and controls the artefact |
| **A5** | A key holder | Holds the device key or a signing key |

---

## What is defended, and by what

### A1, the model asks for something it should not

| Attack | Control | Pinned by |
|---|---|---|
| Act before the stop is released | Stop channel evaluated **first**, before the request is examined at all | demo refusal 1 |
| Act outside the declared envelope | Policy deny rule on the parameter | demo refusal 2 |
| Act on a target it was not authorised for | Policy deny on target | demo refusal 3 |
| Act with no stated rationale | Policy deny, an action nobody can review after the fact may not be taken | demo refusal 4 |
| Approve its own escalation | Confirmation comes from a `Confirmer`, never from the request | `test_oversight_and_marking.py` |
| Release its own stop | The runtime has no path to energise the relay | `test_registry_admission.py -k stop_channel` |
| Grind through many individually-legal actions | Budgets, and exhaustion engages the stop | `test_policy.py` |
| Exploit `True < 1.0` in a numeric rule | `bool` excluded on both sides of numeric comparisons | `test_policy.py` |

### A4, the supplier writes its own paperwork

| Attack | Control | Pinned by |
|---|---|---|
| Ask for fewer controls than the tier requires | `effective_controls()` returns the **union**; omission grants nothing | `test_registry_admission.py` |
| Self-sign a high-risk card | Quorum of two **distinct roles**, one of them `risk_officer`, resolved from the trust store | `test_A3` |
| Sign twice with one key to make quorum | Duplicate `key_id` refused | `test_A3` |
| Ship an artefact that is not the one described | `artifact_binding` check against `artifact_digest` | `test_registry_admission.py` |
| Declare a control the device cannot enforce | `controls_enforceable` fails closed | device profile tests |
| Deploy to a device the card does not name | `deployment_target` check | `test_registry_admission.py` |

### A3, file-level tampering

| Attack | Control | Pinned by |
|---|---|---|
| Alter a record body | Recomputed record hash mismatches | `test_B3` |
| Reorder two records | `prev_hash` no longer chains | `test_B1` |
| Delete a record | Sequence gap | `test_B2` |
| Append a forged record | No valid `prev_hash` without the preceding hash | `test_journal.py` |
| Erase the journal entirely | Empty file is **refused**, not reported verified | `test_B5`, audit finding F-4 |
| Feed the verifier a non-journal | Refusal with a reason, not a stack trace | `test_B5`, `test_B6` |
| Add a key to the trust store | *Not defended.* See residual R-2 |

### Signature-layer attacks

All refused, all pinned in `tests/test_adversarial.py`:

- **Transplant**: signatures lifted onto a modified card (`test_A1`); `card_digest` is inside the signed payload.
- **Untrusted key / TOFU**: an unknown `key_id` is a refusal, not a prompt (`test_A2`).
- **Algorithm confusion**: `alg: "none"` and anything but `ed25519` refused (`test_A6`).
- **Empty signature list**: refused, never treated as "nothing objected" (`test_A7`).
- **Backdating**: a signature outside the key's validity window refused (`test_A4`).
- **Future-dating**: refused (`test_A5`).
- **`signed_at` tampering**: it is inside the signed payload (`test_A8`).
- **`key_id` swap between two valid signatures**: refused (`test_A9`).

### Canonicalisation

- Key order does not change a digest (`test_C3`).
- NaN and ±Infinity are refused rather than serialised (`test_C2`).
- Unicode is **not** normalised, so visually identical strings with different
  code points do not collide (`test_C4`).

---

## Residual risk, accepted, not overlooked

| # | Risk | Why it is accepted | Reference |
|---|---|---|---|
| **R-1** | A holder of the device key can rewrite the journal consistently and it verifies | Hash chaining gives tamper *evidence*, not resistance. The fix is an external witness holding checkpoint roots; the checkpoints are produced, the transmission belongs to whoever operates the fleet | ADR 0007, `test_B4` (passes deliberately) |
| **R-2** | Anyone who can write the trust store can admit anything | The trust store is the root. Protecting it is a filesystem and provisioning problem, not one this package can solve from inside | ADR 0006 |
| **R-3** | Signing keys sit in the clear on disk | Attestation without a secure element is theatre. Encrypting the file with a passphrase stored beside it would be worse, it would look solved | ADR 0006 |
| **R-4** | Truncation after the last checkpoint is undetectable from the file alone | Same root cause as R-1: no external anchor | `test_truncation_is_detected_only_against_a_checkpoint` |
| **R-5** | The policy file can be edited by anyone who can write it | Rules are data on purpose, so they can be diffed and reviewed. Integrity is a deployment control | ADR 0004 |
| **R-6** | Nothing has run on hardware | Every backend but the simulator raises `NotPortedError`. The stop channel has never held a relay, and a simulated relay cannot lose power | README, `hal/devices.py` |
| **R-7** | `SimulatedModel` is not a detector | Its two knobs are miss rate and false-alarm rate, which are the governance events that matter | README |

**R-1 and R-4 have one fix between them**: publish checkpoint roots somewhere
the device cannot reach. Until that exists, the honest claim is that this
detects tampering by everyone *except* the party holding the device key.

---

## Out of scope

- Availability. Nothing here resists denial of service; a stopped machine is the
  intended failure mode.
- Confidentiality of the model artefact. The card binds its digest; it does not
  protect it.
- Side channels, fault injection, physical attack on the relay.
- The supply chain of `cryptography`, the single runtime dependency.

## Reporting

Private vulnerability reporting, and what is out of scope by design:
[SECURITY.md](../SECURITY.md).
