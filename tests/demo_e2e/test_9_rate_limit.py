"""The proxy's per-address limit on what visitors post. Runs last: it spends the limit."""

from __future__ import annotations

from collections.abc import Callable

from tests.demo_e2e.bundle import Visitor


def test_posting_faster_than_the_limit_is_refused_at_the_proxy(
    visitor: Callable[[], Visitor], bundle: dict[str, str]
) -> None:
    burst = int(bundle["DEMO_RATE_MESSAGES_BURST"])
    person = visitor()
    statuses = [person.post(f"Message {n}").status_code for n in range(burst + 15)]
    assert statuses[0] == 200
    assert 429 in statuses
    refused = statuses.index(429)
    assert refused >= burst - 1
    assert set(statuses) <= {200, 429}
