"""Signing, trust store, and signature verification.

Ed25519 throughout: small keys, small signatures, constant-time verification,
and no parameter choices to get wrong on a device that will be deployed by
someone who is not a cryptographer.

Threat model addressed here:
  * **Signature transplant** — a valid signature is lifted from card A and
    replayed on card B. Prevented by signing a to-be-signed structure that
    binds the card digest to the signer identity and the signing time.
  * **Role confusion** — a model owner's signature is counted towards the
    risk officer quorum. Prevented by resolving the role from the trust store
    at verification time, never from the envelope.
  * **Expired or revoked keys** — checked against the trust store, fail-closed.

Explicitly *not* addressed: key custody. Software keys on a Linux SBC have no
hardware root of trust. See docs/adr/0006-no-hardware-root-of-trust.md — the
honest statement of that gap is part of the deliverable.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..canonical import canonical_bytes, digest
from ..clock import Clock, SystemClock, iso, parse_iso
from ..errors import ConfigurationError, SignatureInvalid

TRUST_STORE_SCHEMA = "governed-edge-ai/trust-store/v1"
ENVELOPE_SCHEMA = "governed-edge-ai/signed-card/v1"
TBS_SCHEMA = "governed-edge-ai/tbs/v1"

#: Roles that may appear in the trust store. A quorum is counted over
#: *distinct* roles, so adding a role here changes who can co-sign what.
ROLES = ("model_owner", "risk_officer", "operator")


def b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001 - normalised into a governance error
        raise ConfigurationError(f"invalid base64 value: {exc}") from exc


@dataclass(frozen=True)
class SigningKey:
    """A private key plus the identity it signs under."""

    key_id: str
    role: str
    private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls, key_id: str, role: str) -> "SigningKey":
        if role not in ROLES:
            raise ConfigurationError(f"unknown role: {role!r}")
        return cls(key_id=key_id, role=role, private_key=Ed25519PrivateKey.generate())

    def to_document(self) -> dict[str, Any]:
        """Serialise the private key.

        Stored in the clear, which is the correct level of protection for a
        demonstration and the wrong level for anything else. The production
        answer is a secure element or an HSM; the honest interim answer is to
        say so rather than to encrypt the file with a passphrase kept beside it.
        """
        return {
            "schema": "governed-edge-ai/signing-key/v1",
            "key_id": self.key_id,
            "role": self.role,
            "alg": "ed25519",
            "private_key": b64encode(
                self.private_key.private_bytes_raw()
            ),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "SigningKey":
        if document.get("alg") != "ed25519":
            raise ConfigurationError("unsupported key algorithm")
        raw = b64decode(document["private_key"])
        if len(raw) != 32:
            raise ConfigurationError("ed25519 private key must be 32 raw bytes")
        return cls(
            key_id=document["key_id"],
            role=document["role"],
            private_key=Ed25519PrivateKey.from_private_bytes(raw),
        )

    def public_entry(
        self, valid_from: datetime, valid_until: datetime
    ) -> dict[str, Any]:
        """The trust-store entry corresponding to this key."""
        raw = self.private_key.public_key().public_bytes_raw()
        return {
            "key_id": self.key_id,
            "role": self.role,
            "alg": "ed25519",
            "public_key": b64encode(raw),
            "valid_from": iso(valid_from),
            "valid_until": iso(valid_until),
            "revoked_at": None,
        }


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    role: str
    public_key: Ed25519PublicKey
    valid_from: datetime
    valid_until: datetime
    revoked_at: datetime | None

    def usable_at(self, moment: datetime) -> tuple[bool, str]:
        if self.revoked_at is not None:
            return False, f"key {self.key_id} was revoked at {iso(self.revoked_at)}"
        if moment < self.valid_from:
            return False, f"key {self.key_id} not yet valid at {iso(moment)}"
        if moment > self.valid_until:
            return False, f"key {self.key_id} expired at {iso(self.valid_until)}"
        return True, ""


class TrustStore:
    """The set of keys this device will accept signatures from.

    Deliberately a closed set loaded from a file. There is no discovery, no
    key-from-the-envelope fallback, and no TOFU: an unknown key_id is a
    refusal, not a prompt.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        if document.get("schema") != TRUST_STORE_SCHEMA:
            raise ConfigurationError(
                f"trust store schema must be {TRUST_STORE_SCHEMA!r}"
            )
        entries = document.get("keys")
        if not isinstance(entries, list) or not entries:
            raise ConfigurationError("trust store must contain at least one key")

        self._keys: dict[str, TrustedKey] = {}
        for entry in entries:
            key = self._parse_entry(entry)
            if key.key_id in self._keys:
                raise ConfigurationError(f"duplicate key_id in trust store: {key.key_id}")
            self._keys[key.key_id] = key

    @staticmethod
    def _parse_entry(entry: Any) -> TrustedKey:
        if not isinstance(entry, dict):
            raise ConfigurationError("trust store entry must be an object")
        for field in ("key_id", "role", "alg", "public_key", "valid_from", "valid_until"):
            if field not in entry:
                raise ConfigurationError(f"trust store entry missing {field!r}")
        if entry["alg"] != "ed25519":
            raise ConfigurationError(f"unsupported algorithm: {entry['alg']!r}")
        if entry["role"] not in ROLES:
            raise ConfigurationError(f"unknown role: {entry['role']!r}")

        raw = b64decode(entry["public_key"])
        if len(raw) != 32:
            raise ConfigurationError("ed25519 public key must be 32 raw bytes")

        revoked = entry.get("revoked_at")
        return TrustedKey(
            key_id=entry["key_id"],
            role=entry["role"],
            public_key=Ed25519PublicKey.from_public_bytes(raw),
            valid_from=parse_iso(entry["valid_from"]),
            valid_until=parse_iso(entry["valid_until"]),
            revoked_at=parse_iso(revoked) if revoked else None,
        )

    def get(self, key_id: str) -> TrustedKey | None:
        return self._keys.get(key_id)

    def __len__(self) -> int:
        return len(self._keys)

    @classmethod
    def from_keys(
        cls,
        keys: list[SigningKey],
        valid_from: datetime,
        valid_until: datetime,
    ) -> "TrustStore":
        return cls(
            {
                "schema": TRUST_STORE_SCHEMA,
                "keys": [k.public_entry(valid_from, valid_until) for k in keys],
            }
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "schema": TRUST_STORE_SCHEMA,
            "keys": [
                {
                    "key_id": k.key_id,
                    "role": k.role,
                    "alg": "ed25519",
                    "public_key": b64encode(k.public_key.public_bytes_raw()),
                    "valid_from": iso(k.valid_from),
                    "valid_until": iso(k.valid_until),
                    "revoked_at": iso(k.revoked_at) if k.revoked_at else None,
                }
                for k in self._keys.values()
            ],
        }


def to_be_signed(card: dict[str, Any], key_id: str, signed_at: datetime) -> dict[str, Any]:
    """The structure that is actually signed.

    Binding ``key_id`` and ``signed_at`` into the signed bytes is what makes a
    signature non-transplantable and non-replayable across identities.
    """
    return {
        "schema": TBS_SCHEMA,
        "card_digest": digest(card),
        "key_id": key_id,
        "signed_at": iso(signed_at),
    }


def sign_card(
    card: dict[str, Any],
    keys: list[SigningKey],
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Produce a signed envelope for ``card``."""
    clock = clock or SystemClock()
    now = clock.now()
    signatures = []
    for key in keys:
        tbs = to_be_signed(card, key.key_id, now)
        signature = key.private_key.sign(canonical_bytes(tbs))
        signatures.append(
            {
                "key_id": key.key_id,
                "alg": "ed25519",
                "signed_at": iso(now),
                "signature": b64encode(signature),
            }
        )
    return {"schema": ENVELOPE_SCHEMA, "card": card, "signatures": signatures}


@dataclass(frozen=True)
class VerifiedSignature:
    key_id: str
    role: str
    signed_at: datetime


def verify_envelope(
    envelope: Any,
    trust_store: TrustStore,
    now: datetime,
) -> list[VerifiedSignature]:
    """Verify every signature on an envelope.

    Returns the list of signatures that verified. Raises rather than returning
    an empty list when the envelope itself is malformed, so a caller cannot
    confuse "nothing signed this" with "this is not an envelope".
    """
    if not isinstance(envelope, dict) or envelope.get("schema") != ENVELOPE_SCHEMA:
        raise SignatureInvalid(f"expected an envelope with schema {ENVELOPE_SCHEMA!r}")
    card = envelope.get("card")
    if not isinstance(card, dict):
        raise SignatureInvalid("envelope.card must be an object")
    raw_signatures = envelope.get("signatures")
    if not isinstance(raw_signatures, list) or not raw_signatures:
        raise SignatureInvalid("envelope carries no signatures")

    verified: list[VerifiedSignature] = []
    seen_key_ids: set[str] = set()

    for entry in raw_signatures:
        if not isinstance(entry, dict):
            raise SignatureInvalid("signature entry must be an object")
        for field in ("key_id", "alg", "signed_at", "signature"):
            if field not in entry:
                raise SignatureInvalid(f"signature entry missing {field!r}")
        if entry["alg"] != "ed25519":
            raise SignatureInvalid(f"unsupported signature algorithm: {entry['alg']!r}")

        key_id = entry["key_id"]
        if key_id in seen_key_ids:
            # Otherwise one compromised key could satisfy a quorum on its own.
            raise SignatureInvalid(f"duplicate signature from key {key_id!r}")
        seen_key_ids.add(key_id)

        trusted = trust_store.get(key_id)
        if trusted is None:
            raise SignatureInvalid(f"unknown key_id: {key_id!r}")

        signed_at = parse_iso(entry["signed_at"])
        if signed_at > now:
            raise SignatureInvalid(
                f"signature from {key_id!r} is dated in the future ({iso(signed_at)})"
            )

        usable, reason = trusted.usable_at(signed_at)
        if not usable:
            raise SignatureInvalid(reason)
        # A revoked key is also unusable *now*, not merely at signing time.
        usable_now, reason_now = trusted.usable_at(now)
        if not usable_now and trusted.revoked_at is not None:
            raise SignatureInvalid(reason_now)

        tbs = canonical_bytes(to_be_signed(card, key_id, signed_at))
        try:
            trusted.public_key.verify(b64decode(entry["signature"]), tbs)
        except InvalidSignature as exc:
            raise SignatureInvalid(
                f"signature from {key_id!r} does not verify against the card"
            ) from exc

        verified.append(
            VerifiedSignature(key_id=key_id, role=trusted.role, signed_at=signed_at)
        )

    return verified
