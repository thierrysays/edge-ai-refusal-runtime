# ADR 0006 — No hardware root of trust (accepted gap)

**Status:** accepted · 2026-08-21

## Context

Signing keys are Ed25519 private keys stored as base64 in a JSON file. On a
Linux SBC, any process running as the same user can read them. Device
attestation, checkpoint signatures, and the whole admission chain rest on that
file.

## Decision

Ship it, and say so — here, in the README, and in the control map's
"claims deliberately not made" table.

The alternative available today would be to encrypt the key file with a
passphrase stored beside it, which changes the threat model not at all while
creating the appearance that it has.

## What would close the gap

A secure element with a non-extractable key: the ATECC608 on the Qwiic bus, the
secure element on the STM32U585 (UNO Q) or STM32H5 (VENTUNO Q), or Qualcomm's
secure boot chain on the Dragonwing parts. Each changes `SigningKey` and nothing
else — the signing interface was kept narrow for exactly this reason.

## Consequence

Any claim of *attestation* in this repository should be read as *signature by
whoever held the file*. That is materially weaker, and it is the honest
statement of what a software-only implementation buys.
