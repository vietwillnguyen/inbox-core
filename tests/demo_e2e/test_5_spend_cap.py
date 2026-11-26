"""The daily spend cap: once the model's budget is spent, visitors get the holding message.

The test restarts the gateway with a budget smaller than one call, then puts the
bundle's own budget back. The gateway counts spend per deployment, and a new
budget is a new deployment, so neither run inherits the other's spend.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterator

import pytest

from tests.demo_e2e.bundle import LOCAL, Visitor, audit_for, compose, until

ENV = LOCAL / "litellm.env"


def restart_gateway() -> None:
    compose("up", "-d", "--force-recreate", "--no-deps", "litellm")

    def ready() -> bool:
        try:
            compose(
                "exec",
                "-T",
                "inbox-core",
                "/app/.venv/bin/python",
                "-c",
                "import urllib.request; "
                "urllib.request.urlopen('http://litellm:4000/health/liveliness', timeout=3)",
            )
        except subprocess.CalledProcessError:
            return False
        return True

    until(ready, timeout=180, every=3)


@pytest.fixture
def tiny_budget() -> Iterator[None]:
    original = ENV.read_text()
    tiny = "DEMO_DAILY_BUDGET_USD=0.000001"
    ENV.write_text(re.sub(r"(?m)^DEMO_DAILY_BUDGET_USD=.*$", tiny, original))
    restart_gateway()
    try:
        yield
    finally:
        ENV.write_text(original)
        restart_gateway()


@pytest.mark.usefixtures("tiny_budget")
def test_a_spent_budget_stops_model_calls_and_fails_closed(
    visitor: Callable[[], Visitor],
) -> None:
    first = visitor()
    first.say("What are your opening hours?")
    until(first.replies)
    # The budget is now spent: the next visitor's message never reaches a model.
    person = visitor()
    person.say("What are your opening hours?")
    (reply,) = until(person.replies)
    assert "This one needs a person" in reply
    (record,) = until(lambda: audit_for(person.conversation_id or 0))
    assert record["decision"] == "handed_off"
    assert record["classifier"] == "unavailable"
