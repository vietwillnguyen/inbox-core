"""The demo bundle's end-to-end suite: opt-in, against the bundle running locally.

    DEMO_RATE_MESSAGES_PER_MINUTE=60 DEMO_RATE_MESSAGES_BURST=20 \\
    DEMO_RATE_CONTACTS_PER_HOUR=600 DEMO_RATE_CONTACTS_BURST=60 ./deploy/demo/demo.sh up
    uv run pytest -m demo_e2e tests/demo_e2e

The suite posts more than one visitor would, all from one address, so it is run
against a bundle brought up with higher rate limits; the rate-limit test checks
that the limit it was given holds. Every test here is marked ``demo_e2e``,
which the default run deselects. If the bundle is not up, they are skipped.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from tests.demo_e2e.bundle import LOCAL, Owner, Visitor, read_env


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/demo_e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.demo_e2e)


@pytest.fixture(scope="session")
def bundle() -> dict[str, str]:
    if not (LOCAL / "tokens.env").exists():
        pytest.skip("the demo bundle is not set up: run deploy/demo/demo.sh up")
    values = {**read_env("bundle.env"), **read_env("tokens.env")}
    try:
        httpx.get(values["PAGE_ORIGIN"], timeout=5).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("the demo bundle is not running: run deploy/demo/demo.sh up")
    return values


@pytest.fixture(scope="session")
def owner(bundle: dict[str, str]) -> Owner:
    return Owner(
        bundle["CHAT_ORIGIN"], bundle["CHATWOOT_ADMIN_TOKEN"], int(bundle["CHATWOOT_ACCOUNT_ID"])
    )


@pytest.fixture
def visitor(bundle: dict[str, str]) -> Callable[[], Visitor]:
    return lambda: Visitor(bundle["CHAT_ORIGIN"], bundle["CHATWOOT_WEBSITE_TOKEN"])


@pytest.fixture(scope="session")
def tab_session(bundle: dict[str, str]) -> str:
    """The owner signed in to the draft tab, through the proxy, with their own token."""
    response = httpx.post(
        f"{bundle['BOT_ORIGIN']}/tab/session",
        headers={"Origin": bundle["BOT_ORIGIN"]},
        json={"chatwoot_token": bundle["CHATWOOT_ADMIN_TOKEN"]},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    session: str = response.json()["session_token"]
    return session
