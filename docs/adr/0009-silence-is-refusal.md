# ADR 0009, An unanswered escalation is a refusal

**Status:** accepted · 2026-08-21

## Context

Article 14 oversight is usually implemented as a notification. If nobody
responds, the action proceeds. The record then shows that oversight occurred.

## Decision

The default `Confirmer` is `AbsentOperator`, which returns "not approved" with
operator id `unattended`. A `ScriptedConfirmer` that runs out of answers does
the same. Releasing a stop channel rejects the operator id `unattended`
outright.

## Rationale

An escalation that nobody answers produces a record, not a decision. Treating it
as approval is oversight theatre, and it is the specific mechanism by which a
control that passed its acceptance test degrades into a rubber stamp over the
following year.

## Cost

Real: a line whose operator has stepped away stops. That cost is the honest
price of the Article 14 claim, and pricing it is part of what this project is
for. Organisations unwilling to pay it are not implementing Article 14; they are
describing it.
