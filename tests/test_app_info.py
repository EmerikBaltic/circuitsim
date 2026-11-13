"""Tests for Qt-free circuitsim.app_info single source of truth."""

from __future__ import annotations

from tests.conftest import assert_module_has_no_qt_imports


def test_app_info_has_no_qt_imports() -> None:
    """circuitsim.app_info must remain pure Python with zero PySide6 imports."""
    assert_module_has_no_qt_imports("circuitsim.app_info")


def test_app_info_values() -> None:
    from circuitsim.app_info import (
        APP_NAME,
        APP_VERSION,
        ISSUES_URL,
        LICENSE_NAME,
        REPO_URL,
        get_app_version,
    )

    assert APP_NAME == "Ohmbench"
    assert REPO_URL == "https://github.com/EmerikBaltic/ohmbench"
    assert ISSUES_URL == "https://github.com/EmerikBaltic/ohmbench/issues"
    assert "MIT" in LICENSE_NAME
    assert APP_VERSION == get_app_version()
    assert len(APP_VERSION) >= 3
