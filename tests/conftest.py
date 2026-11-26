"""Test configuration: the core's own opt-in pytest plugin, used as a client would."""

from collections.abc import Iterator

import pytest

from tests.helpers import OPEN_STORES

pytest_plugins = ["inbox_core.testing.pytest_plugin"]


@pytest.fixture(autouse=True)
def _close_stores() -> Iterator[None]:
    # Python 3.13 warns about an unclosed sqlite connection, and the suite
    # treats warnings as errors: every SQL store a test builds is closed.
    yield
    while OPEN_STORES:
        close = getattr(OPEN_STORES.pop(), "close", None)
        if close:
            close()
