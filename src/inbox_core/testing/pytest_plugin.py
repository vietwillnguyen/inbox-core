"""An opt-in pytest plugin exposing the privacy sweep as a fixture.

Enable it in a ``conftest.py``::

    pytest_plugins = ["inbox_core.testing.pytest_plugin"]

then::

    def test_no_content_is_written_down(privacy_sweep):
        privacy_sweep(build_my_pipeline, my_corpus, logger_names=("my_app",))

It is not registered automatically, so installing the package never changes
another project's test run.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

import pytest

from inbox_core.testing.privacy import SweepReport, run_privacy_sweep

__all__ = ["privacy_sweep"]


@pytest.fixture
def privacy_sweep(caplog: pytest.LogCaptureFixture) -> Callable[..., SweepReport]:
    """:func:`inbox_core.testing.privacy.run_privacy_sweep` with ``caplog`` already bound."""
    return functools.partial(run_privacy_sweep, caplog=caplog)
