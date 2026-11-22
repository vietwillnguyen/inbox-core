"""The package itself: importable, versioned, typed, and side-effect free on import."""

import importlib
import logging
from importlib import resources
from pathlib import Path

import pytest

import inbox_core


def test_version_is_exposed_and_matches_metadata() -> None:
    from importlib.metadata import version

    assert inbox_core.__version__ == version("inbox-core")


def test_package_ships_a_py_typed_marker() -> None:
    assert resources.files("inbox_core").joinpath("py.typed").is_file()


def test_import_adds_no_handlers_beyond_a_null_handler() -> None:
    # A library must never configure logging for its host application.
    importlib.reload(inbox_core)
    handlers = logging.getLogger("inbox_core").handlers
    assert all(isinstance(handler, logging.NullHandler) for handler in handlers)
    assert logging.getLogger("inbox_core").propagate is True


def test_import_creates_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    importlib.reload(inbox_core)
    assert list(tmp_path.iterdir()) == []
