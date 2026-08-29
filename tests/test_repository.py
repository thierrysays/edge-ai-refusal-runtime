"""QA: properties of the repository itself, not of the code.

Documentation drifts silently, and in a repository whose product is a set of
claims, a stale claim is a defect of the same kind as a broken control. Three
sorts of drift fail the build here: a control-map row whose test no longer
exists, a link or an ADR reference that points at nothing, and a documented test
count that no longer matches the suite.

The control-map check is the load-bearing one. CONTROL_MAP.md is described in
CONTRIBUTING.md as a contract: adding a control adds a row plus its test, and
deleting a test deletes the row. Until now nothing enforced that.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TESTS = ROOT / "tests"

LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:)([^)#]+)")
BACKTICKED_TEST = re.compile(r"`(test_[A-Za-z0-9_]+)")
ADR_REFERENCE = re.compile(r"ADR (\d{4})")


def markdown_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and ".venv" not in path.parts
    )


def defined_tests() -> set[str]:
    names: set[str] = set()
    for path in TESTS.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            is_function = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            if is_function and node.name.startswith("test_"):
                names.add(node.name)
    return names


# ------------------------------------------------------- the control map is a contract

def test_every_test_named_in_the_control_map_exists():
    """A row whose test has gone is a claim with nothing behind it."""
    body = (DOCS / "CONTROL_MAP.md").read_text(encoding="utf-8")
    known = defined_tests()
    missing = sorted(
        name for name in set(BACKTICKED_TEST.findall(body))
        # Parametrised rows are written as `test_x[case]` and truncate here.
        if name not in known and not any(k.startswith(name) for k in known)
    )
    assert not missing, f"control map names tests that do not exist: {missing}"


def test_the_control_map_covers_every_test_file():
    """Every suite file should be represented, or the map is partial."""
    body = (DOCS / "CONTROL_MAP.md").read_text(encoding="utf-8")
    named = set(BACKTICKED_TEST.findall(body))
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name in {"test_smoke.py", "test_repository.py", "test_cli.py"}:
            continue  # layers that assert on the harness, not on a control
        tree = ast.parse(path.read_text(encoding="utf-8"))
        in_file = {
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        }
        # Rows may cite a parametrised test by its prefix, as `test_A6` does.
        covered = any(
            name in named or any(cited and name.startswith(cited) for cited in named)
            for name in in_file
        )
        assert covered, f"{path.name} has no test named in the control map"


# ------------------------------------------------------------------------ links

@pytest.mark.parametrize(
    "document", markdown_files(), ids=lambda p: str(p.relative_to(ROOT))
)
def test_every_relative_link_resolves(document):
    for target in LINK.findall(document.read_text(encoding="utf-8")):
        resolved = (document.parent / target.strip()).resolve()
        assert resolved.exists(), f"{document.relative_to(ROOT)} points at {target}"


@pytest.mark.parametrize(
    "document", markdown_files(), ids=lambda p: str(p.relative_to(ROOT))
)
def test_every_adr_reference_has_a_file(document):
    adrs = {path.name[:4] for path in (DOCS / "adr").glob("*.md")}
    for number in ADR_REFERENCE.findall(document.read_text(encoding="utf-8")):
        assert number in adrs, f"{document.relative_to(ROOT)} cites a missing ADR {number}"


# -------------------------------------------------------------------- the claims

def test_the_documented_test_count_matches_the_suite():
    """CLAUDE.md states a number. It has been wrong before."""
    claimed = re.search(r"(\d+) test functions", (ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
    assert claimed, "CLAUDE.md no longer states a test count"
    assert int(claimed.group(1)) == len(defined_tests())


def test_every_energy_model_is_still_labelled_an_estimate():
    """Invariant 10, enforced rather than remembered."""
    from governed_edge_ai.hal.devices import PROFILES

    for profile in PROFILES.values():
        assert "estimate" in profile.energy_model_source, profile.device_class


def test_the_build_log_is_bilingual():
    english = (DOCS / "BUILD_LOG.en.md").read_text(encoding="utf-8")
    french = (DOCS / "BUILD_LOG.fr.md").read_text(encoding="utf-8")
    assert "2026-08-21" in english
    assert "21 août 2026" in french


def test_the_schema_identifiers_are_frozen():
    """Invariant 11. Changing either string invalidates every artefact made before."""
    from governed_edge_ai.journal.chain import RECORD_SCHEMA
    from governed_edge_ai.registry.schema import SCHEMA_ID

    assert RECORD_SCHEMA == "governed-edge-ai/journal-record/v1"
    assert SCHEMA_ID == "governed-edge-ai/model-card/v1"
