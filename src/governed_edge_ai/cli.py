"""Command line interface.

Two commands matter: ``demo`` produces evidence, ``verify`` checks it. The rest
exist so that the evidence can be produced by someone other than the person who
checks it, which is the only arrangement in which verification means anything.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from typing import Any

from . import __version__
from .canonical import digest_file
from .clock import SystemClock
from .hal.devices import PROFILES
from .journal import verify_journal
from .observability import init_sentry, report_crash
from .policy import PolicyEngine
from .registry import RuntimeContext, SigningKey, TrustStore, admit, sign_card
from .registry.signing import TRUST_STORE_SCHEMA


def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump(path: str, payload: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


# ----------------------------------------------------------------------- demo
def cmd_demo(args: argparse.Namespace) -> int:
    from .agent import run_scenario, write_scenario_artifacts

    result = run_scenario(args.out, parts=args.parts)
    paths = write_scenario_artifacts(args.out, result)

    counters = result["report"]["counters"]
    print(f"scenario complete, artefacts in {args.out}")
    print(f"  journal      : {result['journal_path']}")
    print(f"  trace        : {paths['trace']}")
    print(f"  trust store  : {paths['trust_store']}")
    print()
    print("  inferences   :", counters["inferences"])
    print("  requests     :", counters["requests"])
    print("  allowed      :", counters["allowed"])
    print("  refused      :", counters["denied"], " <- the number that matters")
    print("  escalated    :", counters["escalated"],
          f"({counters['escalations_approved']} approved)")
    print()
    for step in result["trace"]:
        if step.get("step") == "inference" or "performed" not in step:
            continue
        mark = "✓" if step["performed"] else "✗"
        reason = step["reasons"][0] if step["reasons"] else ""
        print(f"  {mark} {step['step']:<34} {step['effect']:<14} {reason[:78]}")
    print()
    print("now verify the evidence independently:")
    print(f"  gea verify --journal {result['journal_path']} "
          f"--trust-store {paths['trust_store']}")
    return 0


# --------------------------------------------------------------------- verify
def cmd_verify(args: argparse.Namespace) -> int:
    store = TrustStore(_load(args.trust_store)) if args.trust_store else None
    report = verify_journal(args.journal, store)
    print(report.summary())
    if args.json:
        print(json.dumps(
            {
                "ok": report.ok,
                "entries": report.entries,
                "checkpoints": report.checkpoints,
                "head": report.head,
                "broken_at": report.broken_at,
                "reasons": list(report.reasons),
            },
            indent=2,
        ))
    return 0 if report.ok else 1


# --------------------------------------------------------------------- keygen
def cmd_keygen(args: argparse.Namespace) -> int:
    key = SigningKey.generate(args.key_id, args.role)
    _dump(args.out, key.to_document())
    print(f"private key written to {args.out} (unprotected, see ADR 0006)")
    now = SystemClock().now()
    entry = key.public_entry(now, now + timedelta(days=args.valid_days))
    print(json.dumps(entry, indent=2))
    return 0


def cmd_truststore(args: argparse.Namespace) -> int:
    now = SystemClock().now()
    keys = [SigningKey.from_document(_load(path)) for path in args.key]
    document = {
        "schema": TRUST_STORE_SCHEMA,
        "keys": [
            k.public_entry(now, now + timedelta(days=args.valid_days)) for k in keys
        ],
    }
    TrustStore(document)  # validate before writing
    _dump(args.out, document)
    print(f"trust store with {len(keys)} key(s) written to {args.out}")
    return 0


# ----------------------------------------------------------------------- sign
def cmd_sign(args: argparse.Namespace) -> int:
    card = _load(args.card)
    if args.artifact:
        card["artifact_digest"] = digest_file(args.artifact)
    keys = [SigningKey.from_document(_load(path)) for path in args.key]
    envelope = sign_card(card, keys)
    _dump(args.out, envelope)
    roles = ", ".join(sorted({k.role for k in keys}))
    print(f"signed by {len(keys)} key(s) [{roles}] -> {args.out}")
    return 0


# ---------------------------------------------------------------------- admit
def cmd_admit(args: argparse.Namespace) -> int:
    profile = PROFILES.get(args.device)
    if profile is None:
        print(f"unknown device class {args.device!r}; known: {sorted(PROFILES)}",
              file=sys.stderr)
        return 2
    runtime = RuntimeContext(
        device_class=profile.device_class,
        available_controls=frozenset(profile.available_controls),
        operator_id=args.operator or "unattended",
    )
    decision = admit(
        _load(args.envelope),
        TrustStore(_load(args.trust_store)),
        runtime,
        artifact_path=args.artifact,
    )
    verdict = "ADMITTED" if decision.admitted else "REFUSED"
    print(f"{verdict}: {decision.model_id} {decision.version} on {args.device}")
    for name, passed in decision.checks:
        print(f"  [{'ok' if passed else 'FAIL'}] {name}")
    for reason in decision.reasons:
        print(f"  - {reason}")
    if decision.admitted:
        print("  obligations:", ", ".join(decision.obligations))
    return 0 if decision.admitted else 1


# -------------------------------------------------------------------- devices
def cmd_devices(args: argparse.Namespace) -> int:
    for name in sorted(PROFILES):
        profile = PROFILES[name]
        print(f"{name}")
        print(f"  {profile.description}")
        print(f"  controls: {', '.join(sorted(profile.available_controls))}")
        print(f"  energy model: {profile.energy_model_source}")
        print()
    return 0


# --------------------------------------------------------------------- policy
def cmd_policy(args: argparse.Namespace) -> int:
    engine = PolicyEngine.from_file(args.policy)
    print(f"{engine.name} v{engine.version}, {len(engine.rules)} rules "
          f"(default: deny)")
    for rule in engine.rules:
        print(f"  [{rule.effect:<14}] {rule.id}")
        print(f"      when   {json.dumps(rule.when, ensure_ascii=False)}")
        print(f"      because {rule.because}")
    return 0


# ----------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gea",
        description="governed-edge-ai, governance controls that either fire, or do not.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run the deterministic inspection scenario")
    demo.add_argument("--out", default="./run", help="output directory")
    demo.add_argument("--parts", type=int, default=16)
    demo.set_defaults(func=cmd_demo)

    verify = sub.add_parser("verify", help="verify a journal independently")
    verify.add_argument("--journal", required=True)
    verify.add_argument("--trust-store", default=None)
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=cmd_verify)

    keygen = sub.add_parser("keygen", help="generate an Ed25519 signing key")
    keygen.add_argument("--key-id", required=True)
    keygen.add_argument("--role", required=True,
                        choices=["model_owner", "risk_officer", "operator"])
    keygen.add_argument("--out", required=True)
    keygen.add_argument("--valid-days", type=int, default=365)
    keygen.set_defaults(func=cmd_keygen)

    store = sub.add_parser("truststore", help="build a trust store from key files")
    store.add_argument("--key", action="append", required=True)
    store.add_argument("--out", required=True)
    store.add_argument("--valid-days", type=int, default=365)
    store.set_defaults(func=cmd_truststore)

    sign = sub.add_parser("sign", help="sign a model card")
    sign.add_argument("--card", required=True)
    sign.add_argument("--key", action="append", required=True)
    sign.add_argument("--artifact", default=None,
                      help="recompute artifact_digest from this file before signing")
    sign.add_argument("--out", required=True)
    sign.set_defaults(func=cmd_sign)

    gate = sub.add_parser("admit", help="run the admission gate")
    gate.add_argument("--envelope", required=True)
    gate.add_argument("--trust-store", required=True)
    gate.add_argument("--device", required=True)
    gate.add_argument("--artifact", default=None)
    gate.add_argument("--operator", default=None)
    gate.set_defaults(func=cmd_admit)

    devices = sub.add_parser("devices", help="list device profiles and their controls")
    devices.set_defaults(func=cmd_devices)

    policy = sub.add_parser("policy", help="load a policy and print its rules")
    policy.add_argument("--policy", required=True)
    policy.set_defaults(func=cmd_policy)

    return parser


def main(argv: list[str] | None = None) -> int:
    init_sentry(release=f"governed-edge-ai@{__version__}")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        report_crash(exc)
        raise


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
