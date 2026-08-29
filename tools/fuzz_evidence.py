"""Mutation fuzzer over the two parsers that read attacker-influenced input.

`verify_journal()` reads a file an auditor may have received from anywhere, and
`validate_card()` reads a model card submitted by a provider. Both are the
outermost edge of this system, and both are supposed to answer in exactly one
of two ways: a result, or a named governance error.

That is the whole property under test here. Not that the verifier finds every
tamper, which the unit tests cover, but that no input at all makes it fall over.
A tool that crashes has not verified anything, and a traceback where a refusal
was promised trains an operator to stop reading the output.

Deterministic: the seed is an argument, and a failing seed reproduces exactly.

    python tools/fuzz_evidence.py --iterations 4000 --seed 12
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from governed_edge_ai.canonical import canonical_bytes  # noqa: E402
from governed_edge_ai.errors import ConfigurationError, JournalIntegrityError  # noqa: E402
from governed_edge_ai.journal.chain import verify_journal  # noqa: E402
from governed_edge_ai.registry.schema import validate_card  # noqa: E402

NASTY: list[Any] = [
    None, True, False, 0, -1, 2**63, 1e308, "", " ", "\x00", "\x1b[2J", "\n",
    # The bidi override is written as an escape rather than as itself. A literal
    # U+202E in a source file is the Trojan Source pattern, and a repository
    # that ships one while lecturing about provenance deserves the finding.
    "../../etc/passwd", "..", "\u202e", "sha256:" + "z" * 64, "NaN", "Infinity",
    [], {}, [1, 2, 3], {"nested": {"deeper": [1]}}, "x" * 4000,
]


def pick(rng: random.Random) -> Any:
    # Deep-copied: handing the same container object out twice can nest it
    # inside itself, which produces a circular reference and a finding that is
    # about the fuzzer rather than about the code under test.
    return deepcopy(rng.choice(NASTY))


def mutate(rng: random.Random, body: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(body))
    for _ in range(rng.randint(1, 3)):
        choice = rng.random()
        keys = list(out)
        if choice < 0.45 and keys:
            out[rng.choice(keys)] = pick(rng)
        elif choice < 0.65 and keys:
            del out[rng.choice(keys)]
        elif choice < 0.8:
            name = "".join(rng.choices(string.ascii_letters, k=rng.randint(1, 8)))
            out[name] = pick(rng)
        elif keys:
            # Reach one level down, where the interesting structure lives.
            key = rng.choice(keys)
            if isinstance(out[key], dict) and out[key]:
                out[key][rng.choice(list(out[key]))] = pick(rng)
            else:
                out[key] = pick(rng)
    return out


def fuzz_journal(rng: random.Random, iterations: int, sample: list[dict[str, Any]]) -> int:
    """verify_journal returns a report or raises JournalIntegrityError."""
    failures = 0
    with tempfile.TemporaryDirectory() as workspace:
        path = str(Path(workspace) / "journal.jsonl")
        for iteration in range(iterations):
            lines = []
            for record in sample:
                mutated = mutate(rng, record) if rng.random() < 0.5 else record
                try:
                    lines.append(json.dumps(mutated))
                except (TypeError, ValueError):
                    lines.append("{")
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            try:
                verify_journal(path)
            except JournalIntegrityError:
                continue
            except Exception as exc:  # noqa: BLE001 - that is the finding
                print(
                    f"FAIL journal seed={rng_seed} iteration={iteration}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                failures += 1
                if failures > 3:
                    return failures
    return failures


def fuzz_card(rng: random.Random, iterations: int, sample: dict[str, Any]) -> int:
    """validate_card returns a dict or raises ConfigurationError."""
    failures = 0
    for iteration in range(iterations):
        mutated = mutate(rng, sample)
        try:
            result = validate_card(mutated)
        except ConfigurationError:
            continue
        except Exception as exc:  # noqa: BLE001 - that is the finding
            print(
                f"FAIL card seed={rng_seed} iteration={iteration}: "
                f"{type(exc).__name__}: {exc}\n  input: {json.dumps(mutated)[:400]}",
                file=sys.stderr,
            )
            failures += 1
            if failures > 3:
                return failures
            continue
        if not isinstance(result, dict):
            print(f"FAIL card seed={rng_seed}: validate_card returned {type(result)}",
                  file=sys.stderr)
            failures += 1
        # A card that validates must still serialise canonically, because the
        # next thing anyone does with it is hash it.
        try:
            canonical_bytes(result)
        except Exception as exc:  # noqa: BLE001
            print(
                f"FAIL card seed={rng_seed} iteration={iteration}: validated a card "
                f"that cannot be canonicalised: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            failures += 1
    return failures


def load_samples() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(__file__).resolve().parent.parent
    journal = [
        json.loads(line)
        for line in (root / "examples" / "journal.sample.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    card = json.loads((root / "examples" / "model-card.example.json").read_text(encoding="utf-8"))
    return journal, card


rng_seed = 12


def main(argv: list[str] | None = None) -> int:
    global rng_seed
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=12)
    args = parser.parse_args(argv)
    rng_seed = args.seed

    journal_sample, card_sample = load_samples()
    # A fuzzer needs a reproducible sequence rather than an unpredictable one:
    # the seed is an argument precisely so that a failing run can be repeated.
    rng = random.Random(args.seed)  # noqa: S311  # nosec B311

    failures = fuzz_journal(rng, args.iterations // 4, journal_sample[:6])
    failures += fuzz_card(rng, args.iterations, card_sample)

    if failures:
        print(f"{failures} unexpected exception(s)", file=sys.stderr)
        return 1
    print(
        f"seed {args.seed}: {args.iterations // 4} journals and {args.iterations} "
        "cards fuzzed, 0 unexpected exceptions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
