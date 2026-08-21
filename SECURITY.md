# Security policy

## Reporting a vulnerability

Report privately through **GitHub Security Advisories**, the *Report a
vulnerability* button under the Security tab of this repository. Please do not
open a public issue for a security report.

Include, where you can: the affected version or commit, what an attacker gains,
the steps to reproduce, and whether you intend to disclose publicly and when.

## What to expect

| Stage | Target |
|---|---|
| Acknowledgement of receipt | 3 working days |
| Initial assessment, with a severity view | 10 working days |
| Fix or documented mitigation for a confirmed high-severity issue | 30 days |
| Public advisory | at the fix, or at 90 days, whichever comes first |

These are the targets of a single maintainer working outside professional hours,
stated plainly rather than dressed up as a vendor SLA.

## Scope

In scope: anything that makes a control fail *open*, a model admitted that
should have been refused, a journal alteration that verification does not
detect, an actuation that reaches the device without a policy decision, a stop
channel that reports disengaged while the relay is open.

Out of scope, because they are documented design positions rather than defects:

- **No hardware root of trust.** Signing keys sit in the clear on a Linux SBC.
  → [ADR 0006](docs/adr/0006-no-hardware-root-of-trust.md)
- **Tamper evidence, not tamper resistance.** An attacker holding the device key
  with write access can rewrite the journal consistently; closing that needs an
  external witness for checkpoint roots.
  → [ADR 0007](docs/adr/0007-external-anchoring-out-of-scope.md)
- **Truncation after the last checkpoint is undetectable from the file alone.**
  Pinned deliberately by
  `test_truncation_is_detected_only_against_a_checkpoint`.

If you think one of those positions is wrong, open an issue, that is a design
argument, not an advisory.

## Not a conformity assessment

This repository demonstrates mechanisms and shows their cost. It certifies
nothing under the AI Act, ISO/IEC 42001, or any other regime, and nothing in it
is legal advice.
