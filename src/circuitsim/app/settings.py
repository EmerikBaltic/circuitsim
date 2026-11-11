"""Application settings, recent files, and atomic JSON persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths

MAX_RECENT_FILES: int = 8
SETTINGS_FILENAME: str = "settings.json"


def get_default_data_dir() -> Path:
    """Return default user application data directory for CircuitSim."""
    override = os.environ.get("CIRCUITSIM_DATA_DIR")
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    p = Path(loc) if loc else (Path.home() / ".circuitsim")
    p.mkdir(parents=True, exist_ok=True)
    return p


class AppSettings:
    """Manages application settings and recent files with atomic persistence."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir: Path = (
            Path(data_dir) if data_dir is not None else get_default_data_dir()
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path: Path = self.data_dir / SETTINGS_FILENAME
        self._data: dict[str, Any] = {
            "recent_files": [],
            "number_format": "auto",  # auto, dot, comma
        }
        self.load()

    def load(self) -> None:
        """Load settings from JSON file if it exists."""
        if not self.file_path.exists():
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data.update(loaded)
        except Exception:
            # If damaged or unreadable, ignore and keep defaults
            pass

    def save(self) -> None:
        """Atomically write settings to disk."""
        tmp_path = self.file_path.with_suffix(".tmp")
        payload = json.dumps(self._data, indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.file_path)

    # -------------------------------------------------------------
    # Recent files
    # -------------------------------------------------------------
    def get_recent_files(self) -> list[str]:
        """Return list of up to 8 recent file paths (most recent first)."""
        raw = self._data.get("recent_files", [])
        if not isinstance(raw, list):
            return []
        return [str(p) for p in raw]

    def add_recent_file(self, file_path: str | Path) -> None:
        """Add or promote file_path to the top of the recent files list."""
        resolved = str(Path(file_path).resolve())
        current = self.get_recent_files()
        current = [p for p in current if p != resolved]
        current.insert(0, resolved)
        self._data["recent_files"] = current[:MAX_RECENT_FILES]
        self.save()

    def remove_recent_file(self, file_path: str | Path) -> None:
        """Remove file_path from the recent files list."""
        resolved = str(Path(file_path).resolve())
        current = [p for p in self.get_recent_files() if p != resolved]
        self._data["recent_files"] = current
        self.save()

    def clear_recent_files(self) -> None:
        """Clear all recent files."""
        self._data["recent_files"] = []
        self.save()

    # -------------------------------------------------------------
    # Number format setting (Task 9)
    # -------------------------------------------------------------
    def get_number_format(self) -> str:
        return str(self._data.get("number_format", "auto"))

    def set_number_format(self, fmt: str) -> None:
        if fmt not in ("auto", "dot", "comma"):
            raise ValueError(
                f"Invalid number format {fmt!r}, expected 'auto', 'dot', or 'comma'."
            )
        self._data["number_format"] = fmt
        self.save()
