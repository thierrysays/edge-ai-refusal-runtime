# edge-ai-refusal-runtime, project instructions

A runtime that refuses to execute an AI model unless its paperwork holds, and
refuses every actuation that no rule authorises. The product of this repository
is **refusals with evidence**, not features.

## Commands

```bash
pip install -e ".[dev]"
make test          # 136 test functions across five layers, in order
make smoke         # 8 test functions, under a second: run this first
make security      # attacks on the controls, rather than exercises of them
make pentest       # adversarial suite + evidence fuzzer + SAST
make demo          # deterministic scenario -> ./run
make verify        # independent journal verification
make qa            # lint, strict types, SAST, dependency advisories, coverage gate
make tamper        # edits the journal, shows verification naming the break
python -m pytest tests/test_registry_admission.py -k stop_channel   # single test
```

`make demo` must always print **4 refused** and **1 escalated**. If it does not,
something regressed, do not adjust the scenario to match the new output.

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
| `policies/` | Rule sets as data, diffable, versionable |
| `docs/CONTROL_MAP.md` | Claim → implementation → the test that proves it |
| `docs/TECHNICAL_REFERENCE.md` | Module by module, and the shape of every artefact |
| `docs/FUNCTIONAL_SPEC.md` | Actors, requirements, acceptance criteria |
| `docs/THREAT_MODEL.md` | What is defended; residual risk R-1 to R-7 |
| `tests/test_adversarial.py` | Attacks on the controls, not exercises of them |
| `tests/test_smoke.py` | Does it start, and does every entry point answer |
| `tests/test_repository.py` | The control map is a contract, enforced. 136 test functions |
| `tools/fuzz_evidence.py` | Mutation fuzzer over `verify_journal()` and `validate_card()` |
| `docs/BARE_METAL.md` | Unboxed UNO Q to a relay that drops out. Untested until the bench says otherwise |

## Invariants, do not break these without an ADR

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
   card's request, never the intersection. A provider cannot opt out by omission.
6. **A missing artefact is a failed check, not a skipped one.**
7. **Journal records carry digests, never payloads.** A CRA-retained technical
   file cannot contain the images.
8. **`verify_journal()` shares no state with `Journal`.** Keep it that way, an
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

## The standard of work

Every deliverable meets `docs/STANDARD_OF_WORK.md` by default: functional
documentation, technical documentation, a neophyte path, a bare-metal path, the
seven test layers (smoke, unit, functional, security, QA, quality gate,
pen-test), a threat model, and a bilingual build log entry. Departures are
stated in the pull request.

All four gaps that document listed are now closed: `docs/BARE_METAL.md` is the
bare-metal path, `make smoke|unit|functional|security|docs` are the separable
layers, `tools/fuzz_evidence.py` fuzzes the journal and card parsers, and
`tests/test_repository.py` fails the build when the control map cites a test
that does not exist. What remains open is stated in that document, and the list
is short: nothing has run on hardware.

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
in the pull request, dependency weight is a governance property here.

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
  records the manifest's digest, that is uncomputable. The link runs
  journal → manifest, one way only.
- Booleans are excluded from numeric policy comparisons on purpose (`True < 1.0`
  is true in Python and must not be true in a policy).
- `test_truncation_is_detected_only_against_a_checkpoint` pins a **limitation**,
  not a feature. It is supposed to show that post-checkpoint truncation is
  undetectable from the file alone.
- Rules are data. Do not "simplify" a rule into a Python callable, a risk
  officer must be able to diff what was in force on a given date.

## Out of scope by design, do not "fix" these

- **No hardware root of trust.** Keys sit in the clear. → ADR 0006. Do not add
  passphrase encryption with the passphrase stored beside it.
- **No external anchoring of checkpoints.** The artefact is produced; the
  transmission belongs to whoever operates the fleet. → ADR 0007.
- **`SimulatedModel` is a stand-in**, not a detector. Its two knobs (miss rate
  and false-alarm rate) are the governance events that matter.
- **The device profiles are capability, not job assignment.** `available_controls`
  records what a board *can* enforce, which is what the admission gate needs to
  know. It does not say which job that board holds in a rig. The sibling
  `governed-edge-ai` repository assigns the UNO Q the witness role and lets no
  board both decide and enforce; nothing here contradicts that, because nothing
  here assigns roles at all. Do not "align" the two by narrowing a profile, a
  profile that understates a device is as wrong as one that overstates it.

## The next milestone

Nothing has run on hardware. In priority order:

1. Port the stop channel to the **UNO Q** with the Modulino Latch Relay over
   Qwiic, and verify that a killed Python process leaves the relay
   **de-energised**. Everything else is theory until that is observed.
   Start at `hal/devices.py::UnoQDevice.porting_note`.
2. Replace one `energy_model` estimate with a measured figure (INA219 over
   Qwiic) and record the gap in `docs/BUILD_LOG.*`.
3. Move the actuation loop to the **STM32H5 on the VENTUNO Q** under Zephyr, so
   a Linux stall cannot keep the machine running.

When a porting step lands, update `docs/BUILD_LOG.en.md` **and**
`docs/BUILD_LOG.fr.md`: the build log is bilingual and both are part of the
deliverable.
