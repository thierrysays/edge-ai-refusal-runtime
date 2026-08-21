# ADR 0008 — Budget exhaustion engages the stop channel

**Status:** accepted · 2026-08-21

## Context

The obvious behaviour on budget exhaustion is to refuse the request and carry
on. The agent then keeps proposing actions, keeps being refused, and the system
spends the rest of the shift in a loop nobody is watching.

## Decision

Exhausting any budget engages the stop channel and writes a `stop` record.

## Rationale

An agent that has spent its allocation has demonstrated that its plan and its
allowance disagree. The correct response to that disagreement is to stop and
involve a human — not to keep refusing individual requests while the agent keeps
trying, which converts a governance signal into background noise.

## Cost

A single mis-sized budget stops a line. Budgets therefore need to be sized from
measurement rather than intuition, which is precisely why `DeviceProfile`
carries `energy_model_source` and why every current value reads `estimate`.
