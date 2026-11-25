"""The operator's smoke test passes against the running bundle."""

from __future__ import annotations

import subprocess

from tests.demo_e2e.bundle import demo, refill_message_limit


def test_the_smoke_test_passes_and_checks_the_answers_sources_in_the_audit(
    bundle: dict[str, str],
) -> None:
    # The smoke test posts as a new visitor from the address the suite drained.
    refill_message_limit(bundle)
    try:
        lines = demo("smoke").splitlines()
    except subprocess.CalledProcessError as failed:
        raise AssertionError(f"the smoke test failed:\n{failed.stdout}") from None
    assert lines, "the smoke test printed nothing"
    assert all(line.startswith("ok  ") for line in lines), lines
    assert "ok   the answer names no source to the visitor" in lines
    assert "ok   the audit record keeps the answer's sources" in lines
