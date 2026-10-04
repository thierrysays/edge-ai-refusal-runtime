"""Smoke: does it start, and does every entry point answer at all.

Runs first and finishes in under a second. A failure here makes every other
layer's output noise, so the suite is ordered to find it before anything else
has had a chance to fail for a more interesting reason.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import governed_edge_ai
from governed_edge_ai.cli import build_parser, main

SUBCOMMANDS = ["demo", "verify", "keygen", "truststore", "sign", "admit", "devices", "policy"]


def test_the_package_imports_and_declares_a_version():
    assert governed_edge_ai.__version__


def test_every_subcommand_is_registered():
    parser = build_parser()
    registered: set[str] = set()
    for action in parser._actions:
        if isinstance(getattr(action, "choices", None), dict):
            registered |= set(action.choices)
    assert set(SUBCOMMANDS) <= registered


@pytest.mark.parametrize("command", SUBCOMMANDS)
def test_every_subcommand_answers_help_without_a_traceback(command, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([command, "--help"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip()


def test_running_with_no_arguments_is_an_error_rather_than_a_crash():
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2


def test_the_device_table_prints(capsys):
    assert main(["devices"]) == 0
    output = capsys.readouterr().out
    assert "uno-q" in output
    # The board that cannot hold a journal is the one worth seeing in a smoke
    # test, because its absence would mean the profiles stopped being honest.
    assert "uno-r4-wifi" in output


def test_the_module_runs_as_a_script():
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "governed_edge_ai.cli", "devices"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "ventuno-q" in result.stdout
