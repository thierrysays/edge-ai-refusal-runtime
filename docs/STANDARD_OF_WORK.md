# The standard of work

What "done" means in this repository and its siblings, `edge-ai-workbench` and
`governed-edge-ai`. It applies by default to every piece of work. Departures are
stated in the pull request rather than discovered later by whoever inherits the
code, and the gaps this repository currently has are listed at the bottom rather
than left to be found.

## Every deliverable carries seven things

**1. Functional documentation.** What the thing is for, who uses it, what it
must do, and what counts as it working. Written so that someone deciding whether
to adopt it can decide without reading the source. → `FUNCTIONAL_SPEC.md`

**2. Technical documentation.** Module by module, with the shape of every
artefact it produces or consumes. Written so that someone extending it does not
have to reverse-engineer a format from an example. → `TECHNICAL_REFERENCE.md`

**3. A neophyte path.** A route from a machine with nothing installed to a
working result, assuming no Python, no terminal experience, and no prior
context. Not a quickstart for colleagues, a guide for someone who has never
done this. → `GETTING_STARTED.md`

**4. A bare-metal path.** The same result on the actual hardware, from an
unboxed board: image, wiring, dependencies without a working network, and how to
tell the difference between a software fault and a power fault.

**5. A layered test harness.** Not one suite. Seven questions, each answered by
tests that can be run alone:

| Layer | The question it answers |
|---|---|
| Smoke | Does it start, and does every entry point answer at all? |
| Unit | Does each control refuse exactly what it is supposed to refuse? |
| Functional | Do the journeys leave the system in the state the operator expected? |
| Security | What happens when someone actively tries to get a refusal reversed? |
| QA | Do the documents, links and shipped artefacts still agree with the code? |
| Quality gate | Lint, strict types, SAST, dependency advisories, coverage floor. |
| Pen-test | Fuzzing and adversarial probing, run as a job of its own. |

**6. A threat model.** What is being defended, against whom, and what is
accepted as residual risk with the reason. A threat model that lists only
defended threats is a brochure. → `THREAT_MODEL.md`

**7. A build log entry.** What was built, what was wrong on the way, and what
the defects were. Bilingual here, and both halves are part of the deliverable.
→ `BUILD_LOG.en.md` / `BUILD_LOG.fr.md`

## Why the security and pen-test layers are separate

They find different things. A security suite encodes attacks someone thought of;
a fuzzer finds the ones nobody thought of. In `edge-ai-workbench`, the security
suite found that a project name was being used as a path and wrote files outside
the repository, and the fuzzer found a parser raising a bare `ValueError` where
the caller had been promised a refusal. Neither was reachable by a functional
test, because neither is a thing a user does on purpose.

The same distinction applies here with higher stakes. `tests/test_adversarial.py`
is the security layer: it attacks the controls rather than exercising them. What
is missing is the layer beneath it, nothing fuzzes the journal parser, the
canonical serialiser, or the model-card schema, and all three read attacker-
influenced input.

## Where this repository stands against it

The four gaps this document listed when it was written are closed:

**A bare-metal path.** `docs/BARE_METAL.md` takes an unboxed UNO Q to a relay
that drops out when the process is killed, including the wiring polarity that
makes the de-energised state the stopped state. Every step of it is untested,
which the guide states at the top rather than leaving the reader to discover at
step six, and each step names what would prove it wrong.

**Separable layers.** `make smoke`, `make unit`, `make functional`,
`make security` and `make docs` each answer one question and run alone. CI runs
the security layer and the fuzzer as their own job, so a security regression is
legible in the checks list rather than buried in a test count.

**A fuzzer.** `tools/fuzz_evidence.py` mutates journals and model cards and
asserts one property: `verify_journal()` and `validate_card()` answer with a
result or a named governance error, for any input at all. It found a real
defect on its first run, in which a card carrying `"valid_from": null` raised
`AttributeError` out of `parse_iso()`. In the gate that meant a stack trace
where an operator needed a reason, and an operator who cannot tell why a model
was refused eventually disables the gate.

**A repository-consistency layer.** `tests/test_repository.py` fails the build
when the control map names a test that does not exist, when a markdown link or
an ADR citation points at nothing, when an `energy_model` loses its `estimate`
label, or when a documented test count stops matching the suite. Writing it
surfaced two pieces of drift immediately: the documented count said 113 when the
suite held 119 test functions, and the entire adversarial suite, nineteen
attacks, was named nowhere in the control map that CONTRIBUTING.md calls a
contract. Both are fixed.

## What is still open

**Nothing has run on hardware.** That is the only gap that matters now, and no
amount of documentation closes it. The stop channel is an argument until a
killed process is observed leaving a relay de-energised.

**No bench acceptance layer.** There is no test that compares a control's
behaviour against an instrument reading the physical world, because there is no
instrument in the loop yet. The sibling repository `edge-ai-workbench` is where
that measurement will be recorded.

**The CLI argument surface is not fuzzed.** The evidence parsers are. Argument
fuzzing would be cheap to add and has not been.

## What this standard does not require

- **Not 100 % coverage.** A floor that fails when coverage *drops* is what a
  gate is for; a number chosen to look impressive gets met with tests that
  assert nothing. This repository's floor is 90, which is where the code is.
- **Not a benchmark for every function.** Performance work needs a measurement
  and a reason.
- **Not documentation of the obvious.** A docstring restating the signature is
  noise. The docstrings here carry the argument for why a control exists and
  what it costs.
