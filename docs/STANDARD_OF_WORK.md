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

## Where this repository currently falls short

Stated plainly, because a standard that is announced and not measured against is
a preference:

**No bare-metal path.** Nothing has run on hardware, so no guide takes an
unboxed UNO Q to a verified refusal. `hal/devices.py::UnoQDevice.porting_note`
carries the intent in three sentences; that is a note, not a guide. This closes
when the stop channel is ported.

**The test layers are not separable.** `make test` runs 113 tests as one suite.
The files are already organised by subject rather than by layer, so a security
regression and a typo in a policy fixture fail the same way. Splitting the
Makefile into `smoke`, `unit`, `functional`, `security` and `docs` targets is
mechanical and has not been done.

**No fuzzer.** `verify_journal()` parses a file an auditor may have received
from anywhere, and the schema validator parses model cards submitted by
providers. Both deserve a deterministic mutation fuzzer asserting that every
input produces either a valid structure or a named governance error, never a
traceback, and never a silently accepted malformed record.

**No repository-consistency layer.** Nothing fails the build when a link in the
control map points at a renamed document, or when an ADR is referenced that does
not exist. `edge-ai-workbench` has this as `tests/test_repository.py`; the same
tests would transfer with the paths changed.

## What this standard does not require

- **Not 100 % coverage.** A floor that fails when coverage *drops* is what a
  gate is for; a number chosen to look impressive gets met with tests that
  assert nothing. This repository's floor is 90, which is where the code is.
- **Not a benchmark for every function.** Performance work needs a measurement
  and a reason.
- **Not documentation of the obvious.** A docstring restating the signature is
  noise. The docstrings here carry the argument for why a control exists and
  what it costs.
