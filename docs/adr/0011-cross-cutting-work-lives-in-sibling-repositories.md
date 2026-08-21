# ADR 0011 — Fleet operations and measurement are separate repositories

**Status:** accepted · 2026-08-21

## Context

Two pieces of work use the whole rig rather than any one board, and both were
candidates for landing here.

**Fleet operations** — over-the-air update, rollback, SBOM, reproducible builds,
container orchestration on constrained nodes. It is what an industrial buyer
asks about before they ask anything about the model, and it is the least
glamorous work in the programme.

**A measurement harness** — power, latency and thermal throttling under
sustained inference, across the five boards. It turns the lab into an
instrument, and it is the only thing that can replace the `energy_model`
estimates this repository currently carries.

Both are useful to this repository. Neither belongs in it.

## Decision

Both become separate, hardware-agnostic repositories:

* `fleet-ops-lab` — A/B slots with automatic rollback, digest-bound manifests,
  SBOM diffing, reproducible-build checking, waved rollouts with a halt rule.
* `measurement-harness` — instrument-agnostic power, latency and thermal
  measurement, emitting verifiable reports.

Neither depends on this package, and this package does not depend on either. The
only interface is a file: a `measurement-harness/energy-model/v1` export can
replace a `DeviceProfile.energy_model`, carrying its `source` string verbatim
into `energy_model_source`.

## Rationale

Three reasons, in order of weight.

**They are not governance.** This repository's claim is that every control here
either fires or does not, and that the tests prove the refusals. A power meter
proves nothing of the kind, and neither does a rollout controller. Folding them
in would dilute a claim that is only worth making if it is narrow.

**They are hardware-agnostic and this is not.** `hal/devices.py` names five
boards. A measurement harness that names five boards is a benchmark script for
one lab; one that names none is an instrument anybody can point at anything.
The same argument holds for an update model that hard-codes a slot layout.

**Their dependency budgets differ.** This package carries one runtime dependency
because dependency weight is a governance property here. A measurement harness
that eventually speaks I²C, SCPI and USB-HID cannot live under that rule, and
should not have to argue with it.

## Cost

Three repositories to keep coherent instead of one, and a real risk that the
schema this repository consumes drifts from the schema the harness emits, since
nothing mechanically couples them. The energy figure will cross that boundary as
a file that somebody copies, which is exactly the kind of manual step that goes
stale.

Accepted, because the alternative — a governance repository that also owns a
benchmark suite and a deployment tool — makes the governance claim harder to
audit, and auditability is the whole product.

## Consequence

* Invariant 10 stands unchanged: every `energy_model` here is labelled
  `estimate` until a measured figure replaces it. What changes is that the
  replacement now has a named producer and a named format.
* When a measured figure arrives, `energy_model_source` carries the harness's
  `source` string **verbatim**, including the report digest and any note that
  throughput regressed under sustained load. A consumer that keeps the number
  and drops the sentence has kept the part that is easy to misuse.
* Neither sibling repository may be added as a dependency of this one. If that
  ever looks necessary, it supersedes this ADR rather than quietly amending it.
