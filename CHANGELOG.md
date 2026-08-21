# Changelog

Notable changes to this project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file, not a git tag, is the authoritative record of what each release
contains. A tag is a pointer; this is the statement.

## [0.1.0] — 2026-08-21

First public release. Commit `b3922c5`.

Governance controls for edge AI that either fire, or do not. The demonstration
refuses four requests and escalates one, and the journal it writes verifies
independently of the process that wrote it.

### Added

- **Admission gate** (`registry/`) — Ed25519-signed model cards checked before
  anything loads. Eight named checks; a high-risk card needs two distinct signer
  roles, one of them `risk_officer`. Roles resolve from the trust store at
  verification time, never from the envelope.
- **Inference journal** (`journal/`) — hash-chained JSONL with Merkle
  checkpoints and an independent verifier that shares no state with the writer.
  Records carry digests, never payloads.
- **Policy engine** (`policy/`) — default deny, rules as JSON data so a risk
  officer can diff what was in force on a given date. Booleans are excluded from
  numeric comparisons on purpose.
- **Stop channel** (`oversight/`) — boots engaged; release requires a named
  operator. `""` and `"unattended"` are refused.
- **Budgets** (`policy/budget.py`) — exhaustion engages the stop rather than
  merely declining the next request.
- **Output marking** (`marking/`) — detached AI Act Article 50 provenance
  manifests carrying digests, so provenance can be published without disclosing
  the input.
- **Device profiles** (`hal/devices.py`) for five Arduino boards. `uno-r4-wifi`
  deliberately lacks the inference journal, so a high-risk card is refused on it.
- **Adversarial suite** (`tests/test_adversarial.py`) — 19 attacks on the
  controls rather than exercises of them. `test_B4` passes deliberately, pinning
  the limitation ADR 0007 accepts.
- **Quality gate** — `ruff`, `mypy --strict`, `bandit`, `pip-audit` and a
  coverage floor, all failing the build in CI.
- **Documentation** — getting started, architecture, functional specification,
  technical reference, threat model, control map, ten ADRs, bilingual build log,
  and the pre-release audit.

### Fixed

Found by the pre-release audit; both predate any published release.

- The verifier raised `IsADirectoryError` or `UnicodeDecodeError` instead of
  refusing with a reason. An auditor could not tell a crash from a finding.
- An erased journal reported `journal verified: 0 entries` and exited `0`. An
  empty file and a wiped one are the same bytes; affirming either is the
  manufactured assurance this project exists to refuse.

### Corrected

- The Digital Omnibus on AI was described as "politically agreed on 6 May 2026".
  Provisional agreement was **7 May**, and it has been **in force since 27 July
  2026** (OJ, 24 July).
- Added the Article 50(2) carve-out: generative systems already on the market
  before 2 August 2026 have until **2 December 2026** for machine-readable
  marking.

### Known limitations

Accepted by decision, not oversight. Each has an ADR and, where testable, a test
that pins it.

- Tamper-**evident**, not tamper-resistant: a holder of the device key can
  rewrite the journal consistently. → ADR 0007
- No hardware root of trust; signing keys sit in the clear. → ADR 0006
- Truncation after the last checkpoint is undetectable from the file alone.
- **Nothing has run on hardware.** Every backend but the simulator raises
  `NotPortedError`.

### Notes

- The distribution is `edge-ai-refusal-runtime`; the import package is
  `governed_edge_ai` and every schema identifier reads `governed-edge-ai/…`.
  Frozen deliberately, so a retained journal stays verifiable across a
  repository rename. → ADR 0010

[0.1.0]: https://github.com/thierrysays/edge-ai-refusal-runtime/commits/main
