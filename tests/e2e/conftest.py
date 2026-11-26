"""The end-to-end suite: opt-in, against the real local stack.

    ./deploy/chatwoot/stack.sh up
    uv run pytest -m e2e tests/e2e

Every test here is marked ``e2e``, which the default run deselects. If the
stack is not up, the tests are skipped rather than failed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.e2e.stack import LOCAL, SERVICE, Agent, Visitor, read_env, stack


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def tokens() -> dict[str, str]:
    if not (LOCAL / "tokens.env").exists():
        pytest.skip("the stack is not set up: run deploy/chatwoot/stack.sh up")
    try:
        httpx.get(f"{SERVICE}/healthz", timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("the inbox-core service is not running: run deploy/chatwoot/stack.sh up")
    return {**read_env("tokens.env"), **read_env("secrets.env")}


@pytest.fixture(scope="session")
def account(tokens: dict[str, str]) -> int:
    return int(tokens["CHATWOOT_ACCOUNT_ID"])


@pytest.fixture(scope="session")
def admin(tokens: dict[str, str], account: int) -> Agent:
    return Agent(tokens["CHATWOOT_ADMIN_TOKEN"], account)


@pytest.fixture(scope="session")
def volunteer(tokens: dict[str, str], account: int) -> Agent:
    return Agent(tokens["CHATWOOT_AGENT_TOKEN"], account)


@pytest.fixture
def visitor(tokens: dict[str, str]) -> Callable[[], Visitor]:
    return lambda: Visitor(tokens["CHATWOOT_WEBSITE_TOKEN"])


@pytest.fixture(scope="module")
def mode(request: pytest.FixtureRequest, tokens: dict[str, str]) -> Any:
    wanted = getattr(request.module, "MODE", "auto")
    stack("mode", wanted)
    return wanted
