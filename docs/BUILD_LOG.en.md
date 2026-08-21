# Build log

A record of what was built, in what order, and what was wrong on the way. Kept
because the interesting content of a governance project is the choices, and
choices are only legible while the reasons are still fresh.

---

## 2026-08-21, Day 1

### Starting position

Five boards, ordered across June and August 2026: an UNO Q 4 GB, a VENTUNO Q,
an UNO R4 WiFi with the Plug and Make Kit Modulino nodes, an Alvik, and a Nesso
N1. Only some of them are on the bench. The VENTUNO Q shipped on 20 August.

That constraint set the first decision: **simulation first**. Waiting for
hardware would have produced controls shaped by whatever the first board made
easy, which is the wrong direction of dependency for something meant to run on a
fleet. → ADR 0005.

### Order of construction

1. `canonical.py`: before anything that would be hashed. Sorted keys, no
   insignificant whitespace, non-finite floats rejected. A digest is only as
   good as the determinism of the bytes beneath it.
2. `clock.py`: injectable time. Evidence that cannot be replayed is anecdote.
3. `registry/`: model card schema, Ed25519 signing, admission gate.
4. `journal/`: Merkle helpers, then the chain, then the independent verifier.
5. `policy/`: decisions, engine, budgets.
6. `oversight/`: stop channels, supervisor.
7. `marking/`: Article 50 provenance.
8. `hal/`: simulated cell, then device profiles.
9. `agent/`: the runtime that wires the five controls in order, then the
   scenario.
10. `cli.py`: produce evidence, check evidence, as separate commands.

Tests were written alongside each module rather than after. The suite reached
113 tests, of which the great majority are negative: a gate that admits a good
model proves nothing.

### Signature transplant

First version of the signing envelope signed the model card directly. That is
transplantable: a valid signature lifted from card A verifies against card A
even when it is presented inside an envelope carrying card B, if the verifier is
careless, and worse, it says nothing about *who* signed or *when*.

Replaced with a to-be-signed structure binding the card digest, the signer key
id, and the signing timestamp. Roles are then resolved from the trust store at
verification time, never read from the envelope, which closes role confusion at
the same time. `test_signature_cannot_be_transplanted_between_cards` and
`test_two_signatures_from_the_same_role_do_not_form_a_quorum` pin both.

### The circular manifest

The provenance manifest initially carried the hash of the journal entry that
recorded the inference. The journal entry carries the digest of the manifest.
That is not merely awkward: it is uncomputable, and I only noticed after
writing a `object.__setattr__` on a frozen dataclass to patch the manifest after
the fact, which is the kind of code that should be read as an alarm rather than
a workaround.

Resolved by making the link one-directional: journal → manifest. An auditor who
found a manifest embedding the hash of the entry that records the manifest's own
digest would be right to distrust the whole file.

### The profile that refused

Writing `hal/devices.py` honestly produced the most useful result of the day.
The UNO R4 WiFi is a microcontroller, not a computer: no durable append-only
storage, therefore it cannot hold the inference journal, therefore its profile
does not list `inference_journal`, therefore a high-risk model card is **refused
on it**.

That conclusion was not designed. It fell out of describing the hardware
accurately, and it is exactly the kind of finding that gets papered over when the
code is written against the board first and the documentation afterwards. It is
now `test_runtime_without_stop_channel_cannot_run_a_high_risk_model` and the
`uno-r4-wifi` row of `gea admit`.

### Choosing a seed, and saying so

The first demonstration run was boring: fourteen parts, two defects, no
low-confidence escalation, no run of three. The controls were all correct and
none of the interesting ones fired.

I searched the seed space for a run that exercises both the escalation path and
the consecutive-defect stop, and settled on seed 12 with a 0.35 defect rate.
Cherry-picking a seed to make a demonstration work is only dishonest when you do
not say so, so `DEMO_SEED` carries a comment saying exactly that, and the tests
pin other seeds including ones where nothing interesting happens.

### Two gaps left open

Both are recorded as accepted, not deferred:

- **No hardware root of trust.** Signing keys sit in the clear in a JSON file.
  Encrypting them with a passphrase stored beside them would change the threat
  model not at all while creating the appearance that it had. → ADR 0006.
- **No external anchoring.** Checkpoints are produced in exactly the form that
  would close the truncation gap (a range, a root, a signature, no payload)
  and deliberately not transmitted, because the choice of witness belongs to
  whoever runs the fleet. → ADR 0007.

Both appear in the control map's "claims deliberately not made" table. A
governance repository that only advertises what it does well is a brochure.

### State at end of day

- 113 tests, all passing, 0.5 s
- `gea demo` produces a 34-entry journal with one signed checkpoint
- `gea verify` re-derives the chain independently and names the sequence number
  when it breaks
- Scenario counters: 10 inferences, 11 requests, 7 allowed, **4 refused**, 1
  escalated and approved
- Nothing demonstrated on hardware yet

### Next

1. Port the stop channel to the UNO Q with the Modulino latch relay over Qwiic,
   and measure whether a killed Python process actually leaves the relay
   de-energised. Everything else is theory until that is observed.
2. Replace one `energy_model` estimate with a measured figure and see how far
   the estimate was out. ADR 0008 depends on budgets being sized from
   measurement.
3. Move the actuation loop to the STM32H5 on the VENTUNO Q under Zephyr, so a
   Linux stall cannot keep the machine running.
