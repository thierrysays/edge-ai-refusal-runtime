"""Optional crash reporting for dev/CI tooling, and nothing else.

`governed_edge_ai` does not import this module and never will: the shipped
runtime keeps its one runtime dependency (`cryptography`) and makes no network
call of its own, and adding Sentry here would spend both. What lives here
instead is a way for `tools/fuzz_evidence.py` to send an unexpected-crash
finding to Sentry in addition to the stderr line it already prints, so a
finding survives past the CI log that raised it and can be triaged, deduped
and alerted on across runs.

Off by default, and safe to leave off. With no `SENTRY_DSN` in the
environment, or without `sentry-sdk` installed (it is not part of
`pip install -e ".[dev]"`; it lives in the `ci` extra), `report()` prints why
it is skipping and returns. Every failure mode here is caught and logged
rather than raised: Sentry is observability of the tooling, not a control, and
it does not get a vote in whether a check passes.
"""

from __future__ import annotations

import os
import sys
from typing import Any

_initialised = False
_enabled = False


def _ci_tags() -> dict[str, str]:
    """Tags read from the GitHub Actions environment, when present."""
    tags = {}
    for env_name, tag_name in (
        ("GITHUB_REPOSITORY", "repository"),
        ("GITHUB_WORKFLOW", "workflow"),
        ("GITHUB_JOB", "job"),
        ("GITHUB_RUN_ID", "run_id"),
        ("GITHUB_REF_NAME", "ref"),
    ):
        value = os.environ.get(env_name)
        if value:
            tags[tag_name] = value
    return tags


def _init() -> bool:
    global _initialised, _enabled
    if _initialised:
        return _enabled
    _initialised = True

    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        print(
            "sentry_ci: SENTRY_DSN is set but sentry-sdk is not installed "
            '(pip install -e ".[ci]"), skipping',
            file=sys.stderr,
        )
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "ci"),
            release=os.environ.get("GITHUB_SHA"),
            traces_sample_rate=0.0,
        )
    except Exception as exc:  # noqa: BLE001 - reporting must never break a build
        print(f"sentry_ci: init failed, skipping: {exc}", file=sys.stderr)
        return False

    _enabled = True
    return True


def report(exc: BaseException, **tags: Any) -> None:
    """Send an unexpected exception found by dev tooling to Sentry, best-effort.

    `**tags` are finding-specific context (seed, iteration, the parser under
    test); `_ci_tags()` adds what the CI environment knows about the run.
    """
    if not _init():
        return

    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for key, value in {**_ci_tags(), **tags}.items():
                scope.set_tag(key, str(value))
            sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=5)
    except Exception as report_exc:  # noqa: BLE001 - never let reporting fail the build
        print(f"sentry_ci: report failed, continuing: {report_exc}", file=sys.stderr)
