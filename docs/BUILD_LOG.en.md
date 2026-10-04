# Build log

A record of what was built, in what order, and what was wrong on the way. Kept
because the interesting content of a governance project is the choices, and
choices are only legible while the reasons are still fresh.

---

## 2026-08-21, later the same day

### The standard, and four gaps closed

`docs/STANDARD_OF_WORK.md` states what "done" means across these repositories:
functional and technical documentation, a neophyte path, a bare-metal path, a
seven-layer test harness, a threat model, and a bilingual build log entry. It
also named four places where this repository fell short of it. All four are now
closed, and closing them produced two findings that were not in anyone's plan.

### The fuzzer found a card that crashed the gate

`tools/fuzz_evidence.py` mutates journal records and model cards, and asserts
one property: `verify_journal()` and `validate_card()` answer with a result or
a named governance error, whatever they are handed.

On the first run, at seed 12, a card carrying `"valid_from": null` raised
`AttributeError: 'NoneType' object has no attribute 'replace'` from inside
`parse_iso()`. The admission gate's whole argument is that a refusal arrives
with a reason an operator can act on. A stack trace is not that. An operator who
cannot tell why a model was refused will disable the gate, which makes this a
governance defect wearing the clothes of a type error.

Fixed at the shared helper rather than at the call site: `parse_iso()` now takes
`object`, states in its docstring that it sits on a trust boundary, and refuses
a non-string with a reason naming the type it got. The gate catches `TypeError`
alongside `ValueError` on the way past. Six parametrised negative tests pin it,
and the fuzzer runs clean across five seeds at 3 000 iterations each.

One earlier failure was the fuzzer's own fault and worth recording: it handed
the same nested dictionary out twice, which produced a self-referential card and
a "circular reference" error that said nothing about this codebase. Fuzz values
are deep-copied now. A finding that turns out to be about the harness is still
worth the hour, because the alternative is trusting a harness that lies.

### The control map was not a contract yet

`tests/test_repository.py` enforces what CONTRIBUTING.md has claimed since day
one: adding a control adds a row plus its test, and deleting a test deletes the
row. It fails the build when the map names a test that does not exist, when a
link or an ADR citation points at nothing, when an `energy_model` loses its
`estimate` label, or when the documented test count stops matching the suite.

It found drift on its first run, in both directions. The documented count said
113 when the suite held 119 test functions. And the entire adversarial suite,
nineteen attacks including the one that records a limitation rather than a
defence, was named nowhere in the map. The map now has an Adversarial section
with those nineteen rows plus the twentieth for the fuzzer's finding.

A contract nothing checks is a preference. That was true here for a day.

### Layers, and a guide written ahead of the bench

The suite now runs as `smoke`, `unit`, `functional`, `security` and `docs`,
each alone, fast first. CI runs the security layer and the fuzzer as their own
job so a regression there is legible in the checks list.

`docs/BARE_METAL.md` takes an unboxed UNO Q to a killed process and a relay that
should drop out. It is written ahead of the bench, says so at the top, and names
what would falsify each step. The step that matters is step 6: kill the process
with `SIGKILL` and watch whether the lamp goes out. If it stays lit, the fix is
not in Python, and the guide says where it is instead.

### State

- 136 test functions across five layers, all passing
- Evidence fuzzer clean across five seeds
- One real defect found and fixed, one piece of documentation drift corrected
- Still nothing run on hardware

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

---

## 2026-08-21, Day 1, later: two things that are not this repository

### What prompted it

Two pieces of work kept being described as "part of the programme" while
plainly not being part of *this*: fleet operations (OTA, rollback, SBOM,
reproducible builds, orchestration on constrained nodes) and a measurement
harness for power, latency and thermal throttling under sustained inference.

Both use the whole rig rather than any one board. Both are hardware-agnostic in
a way this repository is deliberately not: `hal/devices.py` names five specific
boards, because the admission gate has to know what each can enforce. A
measurement harness that names five boards is a benchmark script for one lab.

So: two separate repositories, and → ADR 0011 recording why, at what cost.

### `measurement-harness`

Instrument-agnostic by construction. The core knows `open` / `read` / `close`
returning volts and amps, and nothing else: a shunt monitor, a bench supply
over SCPI, a USB-C analyser and a synthetic generator are the same shape.

The rule the whole thing is built around: **a figure that was not measured never
leaves labelled as one.** `provenance.kind` is derived from the instrument, not
asserted by the caller, and the export refuses a synthetic report unless asked
in as many words, at which point `source` reads `synthetic — not measured`
permanently. That rule exists because of invariant 10 in this repository: every
`energy_model` here is an estimate, and the only thing worse than an estimate is
an estimate that has lost its label somewhere between two systems.

Three findings while building it, none of them anticipated:

- **Integration, not averaging.** Mean watts times wall-clock is right only when
  sampling is uniform, and sampling is least uniform under exactly the sustained
  load being characterised. `max_gap_s` is reported so a reader can see when the
  sampler was starved.
- **An inline sampler cannot see an inference.** Reading between units of work
  is exactly reproducible and structurally blind to the peak draw of the work
  itself. That is not a bug to fix; it is why there are two samplers and why the
  report records which one ran. → its ADR 0003.
- **The throttle detector needed an anti-noise rule before it needed anything
  else.** A single slow window in a long run is a log rotation, not a thermal
  limit. Without the consecutive-window rule the detector reports throttling
  every time something else happens on the machine.

The verdict says *throughput regressed*, never *the device throttled*, unless a
temperature series is present. Sustained slowdown has several causes and the
harness observes one symptom.

61 tests, `mypy --strict` clean, 96 % coverage, no runtime dependencies.
`ina219.py` is written from the datasheet, has driven nothing, and refuses to
return readings, the same `NotPortedError` pattern as `hal/devices.py` here.

### `fleet-ops-lab`

Two rules, and everything else follows.

**Silence is a rollback.** Activation is provisional: it starts a confirmation
window, and a node that does not check in reverts on its own timer, consulting
no server. The state that must survive a power cut is `PENDING`, and `PENDING`
reverts. This is the same argument as ADR 0009 in this repository (an
escalation nobody answers is a refusal), arriving at the same place from
operations rather than from oversight, which was not planned and is probably the
most interesting thing about the pair.

**The fleet halts itself.** A wave over its failure budget stops the rollout,
with no flag to continue, because the flag gets set at three in the morning.

The failure that took longest to model properly was the transfer that
*succeeds* and delivers the wrong bytes. A "did the download work" check misses
it entirely, which is why `digest-mismatch` is a separate code from
`transport-failure` and why `FlakyTransport` can truncate as well as drop.

No cryptography ships in it. Whoever runs a fleet already has a key story, and
the package will not choose one for them, but an *absent* verifier with a
required quorum raises rather than passing, on the same principle as invariant 6
here: a missing artefact is a failed check, not a skipped one.

67 tests, `mypy --strict` clean, 96 % coverage, no runtime dependencies. Every
node is a Python object; nothing has met a power switch. `docs/PORTING.md` in
that repository lists what the first bench port is expected to find wrong,
starting with the write ordering around `PENDING`.

### What this changes here

Nothing in `src/`. Invariant 10 stands unchanged (every `energy_model` is still
labelled `estimate`), but the replacement now has a named producer and a named
format, and `energy_model_source` will carry the harness's `source` string
verbatim, digest and all.

### Where they went

Both are their own repositories, pushed the same day:

* <https://github.com/thierrysays/measurement-harness>
* <https://github.com/thierrysays/fleet-ops-lab>

They were built in a working directory here and staged briefly under
`spinoff/`, because the GitHub App backing the session cannot create
repositories (`403 Resource not accessible by integration`). Once the two
remotes existed the trees were transplanted and the directory removed, so
nothing of either project remains in this one, which is the whole point of
ADR 0011, and would have been quietly undone by leaving them here.
