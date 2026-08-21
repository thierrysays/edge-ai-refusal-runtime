# edge-ai-refusal-runtime — project instructions

A runtime that refuses to execute an AI model unless its paperwork holds, and
refuses every actuation that no rule authorises. The product of this repository
is **refusals with evidence**, not features.

## Commands

```bash
pip install -e ".[dev]"
make test          # 113 tests, ~0.5s
make demo          # deterministic scenario -> ./run
make verify        # independent journal verification
make qa            # lint, strict types, SAST, dependency advisories, coverage gate
make tamper        # edits the journal, shows verification naming the break
python -m pytest tests/test_registry_admission.py -k stop_channel   # single test
```

`make demo` must always print **4 refused** and **1 escalated**. If it does not,
something regressed — do not adjust the scenario to match the new output.

## Where things are

| Path | Role |
|---|---|
| `canonical.py` | The only place anything is serialised for hashing. Sorted keys, no NaN. |
| `clock.py` | Injectable time. Nothing calls `datetime.now()` directly. |
| `errors.py` | One exception per governance failure mode, each with a stable `code`. |
| `registry/` | Model card schema, Ed25519 signing, the admission gate |
| `journal/` | Hash chain, Merkle checkpoints, the independent verifier |
| `policy/` | Default-deny rule engine (rules are JSON data), budgets |
| `oversight/` | Stop channels, human confirmation |
| `marking/` | AI Act Article 50 provenance |
| `hal/` | Simulated cell + device profiles for the five boards |
| `agent/runtime.py` | Wires the five controls **in order** |
| `policies/` | Rule sets as data — diffable, versionable |
| `docs/CONTROL_MAP.md` | Claim → implementation → the test that proves it |
| `docs/TECHNICAL_REFERENCE.md` | Module by module, and the shape of every artefact |
| `docs/FUNCTIONAL_SPEC.md` | Actors, requirements, acceptance criteria |
| `docs/THREAT_MODEL.md` | What is defended; residual risk R-1 to R-7 |
| `tests/test_adversarial.py` | Attacks on the controls, not exercises of them |

## Invariants — do not break these without an ADR

1. **The control order in `GovernedRuntime.act()` is load-bearing.** Stop channel
   → policy → human oversight → budgets → actuation. Never evaluate a request
   before checking the stop channel.
2. **Fail closed. There is no `--force` and there will not be one.** Any new
   code path that could let a refused thing proceed is a defect.
3. **The stop channel starts engaged.** `SimulatedRelay` boots de-energised.
   Releasing requires a named operator; `"unattended"` and `""` are rejected.
4. **The default `Confirmer` is `AbsentOperator`, which refuses.** An escalation
   nobody answers is a refusal, never a permission.
5. **`effective_controls()` returns the union** of the tier baseline and the
   card's request — never the intersection. A provider cannot opt out by omission.
6. **A missing artefact is a failed check, not a skipped one.**
7. **Journal records carry digests, never payloads.** A CRA-retained technical
   file cannot contain the images.
8. **`verify_journal()` shares no state with `Journal`.** Keep it that way — an
   auditor runs it against a file on their own machine.
9. **Device profiles are conservative.** `uno-r4-wifi` deliberately lacks
   `inference_journal`. Change a profile only after the capability is
   demonstrated on the bench, and say so in the build log.
10. **Every `energy_model` is labelled `estimate`** until a real measurement
    replaces it. Do not quietly drop the label.
11. **The schema identifiers are frozen and do not track the repository name.**
    The repository is `edge-ai-refusal-runtime`; the import package is
    `governed_edge_ai`, the console script is `gea`, and every artefact is
    stamped `governed-edge-ai/journal-record/v1` or a sibling identifier. This
    is not drift left over from the rename. `journal-record/v1` is inside every
    hashed record and `tbs/v1` is inside every signed payload, so changing
    either string invalidates every signature and every chain made before the
    change. Do not "tidy" them into agreement with the slug. → ADR 0010.

## The delivery standard

Every deliverable ships with all seven of the following. This is the standing
default across this repository and its siblings — `measurement-harness` and
`fleet-ops-lab` carry the same list — not a per-task decision. Work that adds
behaviour without its documentation and its tiers is unfinished, not fast.

1. **Technical documentation** — module by module, every artefact field, every
   error code. → `docs/TECHNICAL_REFERENCE.md`
2. **Functional documentation** — actors, numbered requirements, acceptance
   criteria, written so someone who never reads the source can check a claim.
   → `docs/FUNCTIONAL_SPEC.md`
3. **A neophyte path** — a guide assuming no terminal, no Python, no git, that
   ends with the reader breaking something on purpose and watching a control
   fire. → `docs/GETTING_STARTED.md`
4. **A bare-metal run** — how it works on real hardware, no container, with the
   wiring, permissions and the one test that must pass before the model is worth
   anything on that board.
5. **A full test harness** — smoke, unit, functional, security and pen-test
   tiers, each selectable by marker, each with a stated purpose.
   → `docs/TEST_STRATEGY.md`
6. **A QA gate** — lint, strict types, SAST, dependency advisories, coverage.
   Everything in it fails the build. → `make qa`
7. **A threat model with residual risks**, each pinned by a test that
   demonstrates the gap rather than hiding it. → `docs/THREAT_MODEL.md`

**Where this repository does not yet meet it.** Points 1, 2, 3, 6 and 7 are
covered. Two are not, and saying so is cheaper than discovering it:

- **Point 4** — there is no `docs/BARE_METAL.md` here. Bare-metal work is
  deferred to the sibling `governed-edge-ai` deployment guide, and nothing in
  this repository has run on a board. Writing it is part of milestone 1 below.
- **Point 5** — the suite is one flat tier plus `tests/test_adversarial.py`,
  which is the pen-test tier under an older name. There is no smoke tier, and
  the security concerns are spread through the adversarial file rather than
  separated. Restructuring into `tests/{smoke,unit,functional,security,pentest}/`
  with markers applied from the path is tracked, not done.

## Repository metadata

**Every repository carries `glossolalie-advisory` as a topic.** It is the common
tag across the whole portfolio — the one that makes the family findable from a
single search — and it sits alongside the repository's own descriptive topics
rather than replacing them. A new repository is not finished until it has it.

The rest of the topic list describes *this* repository: what it does, what it
runs on, what standard it answers to. Aim for ten to twenty, lower-case and
hyphenated, and prefer terms somebody would actually search for over terms that
merely sound thorough.

The description is one sentence saying what the thing refuses or measures, not
what category it belongs to.

## Conventions

**Tests assert on the world, not the log.** `assert bench.cell.speed == 0.3`,
not `assert "denied" in caplog.text`. A governance test that only checks that
something was logged is testing the logger.

**Write the negative test first.** Roughly three quarters of the suite asserts
that something was refused. A gate that admits a good model proves nothing.

**Docstrings carry the argument, not the mechanics.** Module docstrings here
explain *why* a control exists and what it costs. That is the repository's main
intellectual content; keep the register and do not strip it to one-liners.

**One runtime dependency (`cryptography`).** Adding another needs a justification
in the pull request — dependency weight is a governance property here.

**ADRs are immutable.** A change a competent engineer could have made
differently gets a new file in `docs/adr/` with its **cost** stated. Reversals
supersede, never edit.

**Control map is a contract.** Adding a control adds a row plus its test.
Deleting a test deletes the row.

## Traps

- The demo **seed is cherry-picked** (`DEMO_SEED = 12`) so the run exercises both
  the escalation path and the defect-run stop. This is stated openly in a
  comment. Do not "clean it up" by removing the comment.
- The provenance manifest must **not** carry the hash of the journal entry that
  records the manifest's digest — that is uncomputable. The link runs
  journal → manifest, one way only.
- Booleans are excluded from numeric policy comparisons on purpose (`True < 1.0`
  is true in Python and must not be true in a policy).
- `test_truncation_is_detected_only_against_a_checkpoint` pins a **limitation**,
  not a feature. It is supposed to show that post-checkpoint truncation is
  undetectable from the file alone.
- Rules are data. Do not "simplify" a rule into a Python callable — a risk
  officer must be able to diff what was in force on a given date.

## Out of scope by design — do not "fix" these

- **No hardware root of trust.** Keys sit in the clear. → ADR 0006. Do not add
  passphrase encryption with the passphrase stored beside it.
- **No external anchoring of checkpoints.** The artefact is produced; the
  transmission belongs to whoever operates the fleet. → ADR 0007.
- **`SimulatedModel` is a stand-in**, not a detector. Its two knobs — miss rate
  and false-alarm rate — are the governance events that matter.
- **Fleet operations and measurement are somebody else's repository.** OTA,
  rollback, SBOM, reproducible builds and container orchestration live in
  `fleet-ops-lab`; power, latency and thermal measurement live in
  `measurement-harness`. Both are hardware-agnostic, neither depends on this
  package, and this package depends on neither. → ADR 0011. The only interface
  is a file: a `measurement-harness/energy-model/v1` export replaces a
  `DeviceProfile.energy_model`, and its `source` string is copied **verbatim**
  into `energy_model_source`. Do not add either as a dependency.

- **The device profiles are capability, not job assignment.** `available_controls`
  records what a board *can* enforce, which is what the admission gate needs to
  know. It does not say which job that board holds in a rig. The sibling
  `governed-edge-ai` repository assigns the UNO Q the witness role and lets no
  board both decide and enforce; nothing here contradicts that, because nothing
  here assigns roles at all. Do not "align" the two by narrowing a profile — a
  profile that understates a device is as wrong as one that overstates it.

## The next milestone

Nothing has run on hardware. In priority order:

1. Port the stop channel to the **UNO Q** with the Modulino Latch Relay over
   Qwiic, and verify that a killed Python process leaves the relay
   **de-energised**. Everything else is theory until that is observed.
   Start at `hal/devices.py::UnoQDevice.porting_note`.
2. Replace one `energy_model` estimate with a measured figure (INA219 over
   Qwiic) and record the gap in `docs/BUILD_LOG.*`. The producer is the sibling
   `measurement-harness`; its `ina219.py` porting note is the specification, and
   its export refuses to hand over a figure that was not measured.
3. Move the actuation loop to the **STM32H5 on the VENTUNO Q** under Zephyr, so
   a Linux stall cannot keep the machine running.

When a porting step lands, update `docs/BUILD_LOG.en.md` **and**
`docs/BUILD_LOG.fr.md` — the build log is bilingual and both are part of the
deliverable.
