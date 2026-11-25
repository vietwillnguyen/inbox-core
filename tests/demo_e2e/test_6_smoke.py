"""The operator's smoke test passes against the running bundle."""

from __future__ import annotations

from tests.demo_e2e.bundle import demo


def test_the_smoke_test_passes_and_checks_the_answers_sources_in_the_audit() -> None:
    lines = demo("smoke").splitlines()
    assert lines, "the smoke test printed nothing"
    assert all(line.startswith("ok  ") for line in lines), lines
    assert "ok   the answer names no source to the visitor" in lines
    assert "ok   the audit record keeps the answer's sources" in lines
