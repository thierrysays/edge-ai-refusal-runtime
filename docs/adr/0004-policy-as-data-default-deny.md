# ADR 0004 — Policy as data, default deny

**Status:** accepted · 2026-08-21

## Context

A rule expressed as a Python callable cannot be diffed by a risk officer,
attached to a change record, or shown to an auditor as the thing that was in
force on a given date.

## Decision

Rules are JSON objects with an `id`, an `effect`, a `when` clause, and a
mandatory `because` string of at least eight characters. Effects combine by
maximum: `deny` > `require_human` > `allow`. No matching rule is a refusal.

Operators are validated eagerly at load time, so a misspelt operator fails when
the policy is loaded rather than silently producing a rule that never fires —
the most dangerous failure mode a policy language has.

## Alternatives rejected

- *Open Policy Agent / Rego.* Better language, and the right answer at fleet
  scale. Rejected here because it adds a Go runtime to a device where every
  transitive dependency is a line in an SBOM that must be defended under the CRA.
  The rule structures are deliberately close enough that a port is mechanical.
- *Permit by default with deny rules.* Almost every real policy incident is a
  missing rule rather than a wrong one, and permit-by-default turns every
  missing rule into a silent authorisation.

## Cost

Default deny means every new action must be authorised before it can run. That
friction is the product.
