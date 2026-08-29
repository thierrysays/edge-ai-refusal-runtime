"""Fail the build when a documented test count no longer matches the suite.

A number written next to a command is stale the moment somebody adds a test, and
nothing else in the gate notices. `CLAUDE.md` and `CONTRIBUTING.md` both quote
`make test # N tests` as current guidance, and both drifted from 113 to wrong
without a single check complaining.

Scope is deliberately narrow. This checks the files that state a count as
*current*, and leaves the dated records alone: `docs/BUILD_LOG.*` records the
state at the end of day one, `docs/adr/0010` cites the count at v0.1.0, and
`docs/AUDIT-2026-08-21.md` records what passed on the day of the audit. Each was
true when written, and a gate that rewrites history to match today produces a
worse record than no gate at all.

The count is taken from pytest's own collection rather than from parsing its
output, so it does not break when a pytest release changes its summary line.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Files that quote a count as current guidance, and must therefore be right.
WATCHED = ("CLAUDE.md", "CONTRIBUTING.md")

#: `make test  # 132 tests` and `make test  # 132 tests, ~0.5s` both match.
DOCUMENTED = re.compile(r"#\s*(\d+)\s+tests\b")


class _CollectionCounter:
    """Records how many tests pytest collected, without running any of them."""

    def __init__(self) -> None:
        self.count = 0

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        self.count = len(items)


def collected_test_count() -> int:
    counter = _CollectionCounter()
    # Collection prints one line per test file. A gate step should say whether
    # it passed and nothing else, so the listing is swallowed and only surfaced
    # if collection itself fails.
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        status = pytest.main(
            [
                "--collect-only",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                str(ROOT / "tests"),
            ],
            plugins=[counter],
        )
    if status != 0:
        print(captured.getvalue(), file=sys.stderr)
        raise SystemExit(f"collection failed with pytest exit status {status}")
    return counter.count


def documented_counts() -> list[tuple[Path, int, int]]:
    """Every documented count, as (path, line number, value)."""
    found: list[tuple[Path, int, int]] = []
    for name in WATCHED:
        path = ROOT / name
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            match = DOCUMENTED.search(line)
            if match:
                found.append((path, lineno, int(match.group(1))))
    return found


def main() -> int:
    actual = collected_test_count()
    documented = documented_counts()

    if not documented:
        print(
            "no documented test count found in "
            + ", ".join(WATCHED)
            + "\nthe check passes vacuously when the number it guards is deleted, "
            "so its absence is a failure rather than a pass",
            file=sys.stderr,
        )
        return 1

    stale = [(p, n, v) for p, n, v in documented if v != actual]
    for path, lineno, value in stale:
        print(
            f"{path.relative_to(ROOT)}:{lineno}: documented {value} tests, "
            f"the suite collects {actual}",
            file=sys.stderr,
        )
    if stale:
        print(
            f"\nfix the number, or run `make test` and read it off. "
            f"The suite collects {actual}.",
            file=sys.stderr,
        )
        return 1

    print(f"documented test count is current: {actual} in {len(documented)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
