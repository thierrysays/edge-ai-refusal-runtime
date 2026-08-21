# ADR 0002 — The model card is the admission gate, not documentation

**Status:** accepted · 2026-08-21

## Context

AI Act Annex IV technical documentation and the ISO/IEC 42001 AI system record
are, in practice, produced after deployment and filed. Nothing in the running
system consults them, so nothing in the running system contradicts them when
they drift.

## Decision

The model card is a signed object the runtime consults *before* loading
anything. It carries the artefact digest, the risk tier, the authorised
deployment targets, a validity window, and the controls that must be active. A
card that does not verify, does not match the artefact, is out of date, names
another device, or demands a control this device cannot enforce is refused.

High-risk cards require signatures from two distinct roles, one of which must be
`risk_officer`. Roles are resolved from the trust store at verification time,
never read from the envelope.

## Alternatives rejected

- *Warn and continue.* Produces a system that logs its own non-compliance and
  keeps running, which is worse than no gate because it manufactures assurance.
- *Allow an operator override flag.* A control that can be waived under
  operational pressure will be waived under operational pressure.

## Cost

A model cannot be hot-fixed onto a device at 3 a.m. without a countersignature.
This is the intended cost. Organisations that cannot pay it should know that
before an incident, not during one.
