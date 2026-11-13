"""Application identity, version, and project metadata (pure Python, no Qt imports)."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
import tomllib

APP_NAME: str = "Ohmbench"
ORG_NAME: str = "Ohmbench"
LEGACY_APP_NAME: str = "CircuitSim"
APP_SUBTITLE: str = "Electrical Circuit Simulator"
APP_DESCRIPTION: str = (
    "Educational desktop electrical circuit simulator built with "
    "Python, NumPy/SciPy, and PySide6."
)
REPO_URL: str = "https://github.com/EmerikBaltic/ohmbench"
ISSUES_URL: str = f"{REPO_URL}/issues"
LICENSE_NAME: str = "MIT License"
APP_USER_MODEL_ID: str = "EmerikBaltic.Ohmbench.Desktop"


def get_app_version() -> str:
    """Return the installed package version with safe pyproject.toml fallback."""
    for dist_name in ("ohmbench", "circuitsim"):
        try:
            return importlib.metadata.version(dist_name)
        except importlib.metadata.PackageNotFoundError:
            pass
        except Exception:
            pass

    try:
        toml_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if toml_path.exists():
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
            return str(data.get("project", {}).get("version", "0.1.0"))
    except Exception:
        pass
    return "0.1.0"


APP_VERSION: str = get_app_version()
