"""Tests for Qt-free circuitsim.app_info single source of truth and app identity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
        ORG_NAME,
        REPO_URL,
        get_app_version,
    )

    assert APP_NAME == "Ohmbench"
    assert ORG_NAME == "Ohmbench"
    assert REPO_URL == "https://github.com/EmerikBaltic/ohmbench"
    assert ISSUES_URL == "https://github.com/EmerikBaltic/ohmbench/issues"
    assert "MIT" in LICENSE_NAME
    assert APP_VERSION == get_app_version()
    assert len(APP_VERSION) >= 3


def test_qt_application_identity_and_windows_app_user_model_id(qapp) -> None:
    from PySide6.QtCore import QCoreApplication
    from circuitsim.app.settings import (
        get_default_data_dir,
        set_windows_app_user_model_id,
    )
    from circuitsim.app_info import APP_NAME, ORG_NAME

    assert QCoreApplication.organizationName() == ORG_NAME
    assert QCoreApplication.applicationName() == APP_NAME
    default_dir = get_default_data_dir()
    assert default_dir.name == APP_NAME

    if sys.platform == "win32":
        assert set_windows_app_user_model_id() is True


def test_legacy_data_migration_copies_once_never_deletes(tmp_path: Path, monkeypatch) -> None:
    from circuitsim.app.settings import (
        AppSettings,
        get_default_data_dir,
        migrate_legacy_data_files,
    )

    # Injected path and env override continue working seamlessly
    custom_env_dir = tmp_path / "env_dir"
    monkeypatch.setenv("OHMBENCH_DATA_DIR", str(custom_env_dir))
    assert get_default_data_dir() == custom_env_dir

    injected_dir = tmp_path / "injected"
    s = AppSettings(data_dir=injected_dir)
    assert s.data_dir == injected_dir

    # Legacy AppData\Roaming\python -> new Ohmbench dir migration
    legacy_python = tmp_path / "AppData" / "Roaming" / "python"
    legacy_python.mkdir(parents=True)
    legacy_settings = {"recent_files": ["a.circ"], "number_format": "comma"}
    (legacy_python / "settings.json").write_text(json.dumps(legacy_settings), encoding="utf-8")
    (legacy_python / "crash.log").write_text("old crash", encoding="utf-8")
    (legacy_python / "recent_files.json").write_text('["b.circ"]', encoding="utf-8")

    new_dir = tmp_path / "AppData" / "Roaming" / "Ohmbench"
    copied = migrate_legacy_data_files(new_dir, legacy_dirs=[legacy_python])
    assert set(copied) == {"settings.json", "crash.log", "recent_files.json"}

    # Originals MUST NOT be deleted
    assert (legacy_python / "settings.json").exists()
    assert (legacy_python / "crash.log").exists()
    assert (legacy_python / "recent_files.json").exists()

    # Copied settings load properly in new dir
    migrated_settings = AppSettings(data_dir=new_dir)
    assert migrated_settings.get_recent_files() == ["a.circ"]
    assert migrated_settings.get_number_format() == "comma"

    # Existing files in new_dir are never overwritten on subsequent runs
    (new_dir / "crash.log").write_text("newer crash", encoding="utf-8")
    copied_again = migrate_legacy_data_files(new_dir, legacy_dirs=[legacy_python])
    assert copied_again == []
    assert (new_dir / "crash.log").read_text(encoding="utf-8") == "newer crash"
