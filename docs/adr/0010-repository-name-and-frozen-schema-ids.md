# ADR 0010 — The repository is renamed; the schema identifiers are not

**Status:** accepted · 2026-08-21

## Context

The name `governed-edge-ai` was already taken by an existing repository of the
same author: a five-board Arduino rig where log-before-act, witness-before-act
and human override are enforced in protocol and circuitry. That project is at
`v3.0.0` with 733 tests. This one is a simulation-first software runtime at
`v0.1.0` with 113. They share an author, a licence, a regulatory frame and the
same five target boards. They share no code and no history.

Publishing both under one name was never possible. Publishing this one as a
branch of the other was considered and rejected: with no common ancestor and no
overlapping source paths, the comparison renders as a wholesale replacement
rather than a diff, so it would not have informed the choice it was meant to
inform.

The name appears in three places with three different stability requirements,
and the mistake available here is to treat them as one.

1. The **repository slug and distribution name** — the thing that collided.
2. The **import package** `governed_edge_ai` and the console script `gea` —
   which collided with nothing.
3. The **schema identifiers**: `governed-edge-ai/journal-record/v1`,
   `.../model-card/v1`, `.../policy/v1`, `.../provenance/v1`,
   `.../trust-store/v1`, `.../signed-card/v1`, `.../tbs/v1`,
   `.../signing-key/v1`.

The third is not a naming matter. `journal-record/v1` is inside every hashed
journal record and `tbs/v1` is inside every signed to-be-signed payload, so the
identifier is covered by the digest and by the signature over it. Changing the
string changes every hash in the chain and invalidates every signature made
before the change.

## Decision

Rename the repository and the distribution to `edge-ai-refusal-runtime`.

Keep the import package `governed_edge_ai`, the console script `gea`, and every
schema identifier exactly as they are.

## Rationale

A schema identifier names the artefact format, not the repository that happened
to produce it. A journal retained under the Cyber Resilience Act must remain
verifiable by someone who has the file and not the repository — for at least
five years, across renames, forks and the disappearance of the original
publisher. An identifier that tracks the repository name is an identifier that
breaks when the repository is renamed, which is the failure this project exists
to argue against.

The freeze is cheap today and never cheap again. At `v0.1.0` nothing is
deployed and no auditor holds a retained journal, so this is the last moment at
which the identifiers could have been changed for free. Choosing not to change
them now is choosing not to change them later either.

With the identifiers frozen, keeping the import package aligned to them is the
coherent move rather than the lazy one: the code namespace and the evidence
namespace say the same word.

## Alternatives rejected

- *Rename the schema identifiers too, while it is free.* Consistent, and it
  teaches the wrong lesson. A format identifier that follows the repository name
  is one that will follow the next repository name.
- *Rename the import package to match the repository.* Mechanically safe and
  fully covered by the tests. It would leave the code namespace disagreeing with
  the evidence namespace, which is the more confusing of the two mismatches.
- *Keep the old repository name and rename the Arduino rig instead.* That
  project is published, at `v3.0.0`, and carries the name in its release
  history. The newer artefact yields.

## Cost

Real, and paid by the reader. `pip install edge-ai-refusal-runtime` is followed
by `import governed_edge_ai`, and artefacts produced by a repository called
`edge-ai-refusal-runtime` are stamped `governed-edge-ai/...`. Anyone who reads
the identifier as a source address will look for a repository under that name
and not find one. This file is the answer to that question, and the README
carries the short form.
