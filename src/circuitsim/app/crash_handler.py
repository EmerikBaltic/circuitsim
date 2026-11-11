"""Global unhandled exception hook, crash logging, and version diagnostics for CircuitSim."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import platform
import sys
import traceback

import PySide6

from circuitsim.app.settings import AppSettings

REPO_URL: str = "https://github.com/EmerikBaltic/circuitsim"
ISSUES_URL: str = "https://github.com/EmerikBaltic/circuitsim/issues"


def get_app_version() -> str:
    """Return the package version of CircuitSim."""
    try:
        import importlib.metadata

        return importlib.metadata.version("circuitsim")
    except Exception:
        pass
    # Fallback to pyproject.toml
    try:
        toml_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
        if toml_path.exists():
            import tomllib

            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
            return str(data.get("project", {}).get("version", "0.1.0"))
    except Exception:
        pass
    return "0.1.0"


def format_crash_report(
    exctype: type[BaseException],
    value: BaseException,
    tb: object,
) -> str:
    """Format structured crash diagnostics with system versions and traceback."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = [
        "=" * 70,
        f"CircuitSim Crash Report: {now}",
        f"Version:        {get_app_version()}",
        f"Python:         {sys.version.split()[0]} ({platform.python_implementation()})",
        f"PySide6:        {getattr(PySide6, '__version__', 'unknown')}",
        f"Platform:       {platform.platform()} ({sys.platform})",
        f"Repository:     {REPO_URL}",
        f"Report Issue:   {ISSUES_URL}",
        "=" * 70,
        "",
        "".join(traceback.format_exception(exctype, value, tb)),
        "",
    ]
    return "\n".join(lines)


def write_crash_log(
    exctype: type[BaseException],
    value: BaseException,
    tb: object,
    log_dir: Path | None = None,
) -> Path:
    """Write crash report to crash.log in log_dir (defaulting to AppSettings.default_data_dir())."""
    target_dir = log_dir or AppSettings.default_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "crash.log"
    report = format_crash_report(exctype, value, tb)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(report)
    return log_file


def install_global_exception_hook(log_dir: Path | None = None) -> None:
    """Install custom sys.excepthook to log unhandled exceptions and alert the user."""
    orig_excepthook = sys.excepthook

    def _excepthook(
        exctype: type[BaseException],
        value: BaseException,
        tb: object,
    ) -> None:
        if issubclass(exctype, (KeyboardInterrupt, SystemExit)):
            orig_excepthook(exctype, value, tb)
            return

        log_path: Path | None = None
        try:
            log_path = write_crash_log(exctype, value, tb, log_dir=log_dir)
        except Exception:
            pass

        # Print to standard error
        try:
            traceback.print_exception(exctype, value, tb)
        except Exception:
            pass

        # Show friendly dialog if interactive Qt application is running
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance()
            if (
                app is not None
                and os.environ.get("QT_QPA_PLATFORM") != "offscreen"
            ):
                msg = (
                    f"CircuitSim encountered an unexpected error:\n\n"
                    f"{value}\n\n"
                )
                if log_path:
                    msg += f"A crash log has been saved to:\n{log_path}\n\n"
                msg += f"Please report this issue at:\n{ISSUES_URL}"
                QMessageBox.critical(None, "CircuitSim Error", msg)
        except Exception:
            pass

    sys.excepthook = _excepthook
