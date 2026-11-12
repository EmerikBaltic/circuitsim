"""Global unhandled exception hook, crash logging, and version diagnostics for CircuitSim."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import platform
import sys
import time
import traceback
from typing import Any, Callable

import PySide6

from circuitsim.app.settings import AppSettings, get_default_data_dir

REPO_URL: str = "https://github.com/EmerikBaltic/circuitsim"
ISSUES_URL: str = "https://github.com/EmerikBaltic/circuitsim/issues"

_shutting_down: bool = False
_dialog_active: bool = False
_dialog_call_count: int = 0
_dialog_handler: Callable[[str, int, Path | None], None] | None = None
_recent_errors: dict[tuple[str, str, str], dict[str, Any]] = {}


def set_shutting_down(shutting_down: bool = True) -> None:
    """Mark whether application shutdown is in progress."""
    global _shutting_down
    _shutting_down = shutting_down


def is_shutting_down() -> bool:
    """Return True if application is in the process of shutting down."""
    if _shutting_down:
        return True
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and app.closingDown():
            return True
    except Exception:
        pass
    return False


def get_dialog_call_count() -> int:
    """Return total number of error dialog invocations."""
    return _dialog_call_count


def set_dialog_handler(
    handler: Callable[[str, int, Path | None], None] | None,
) -> None:
    """Set custom dialog display callback for testing (args: message, count, log_path)."""
    global _dialog_handler
    _dialog_handler = handler


def reset_crash_state() -> None:
    """Reset recent error deduplication cache and dialog counters (primarily for tests)."""
    global _dialog_active, _dialog_call_count, _dialog_handler
    _recent_errors.clear()
    _dialog_active = False
    _dialog_call_count = 0
    _dialog_handler = None


def compute_error_signature(
    exctype: type[BaseException],
    value: BaseException,
    tb: object,
) -> tuple[str, str, str]:
    """Compute (exception_type, message, top_frame) deduplication signature."""
    exc_name = getattr(exctype, "__name__", str(exctype))
    msg = str(value)

    top_frame = ""
    if tb is not None:
        curr: Any = tb
        last_frame = curr
        while getattr(curr, "tb_next", None) is not None:
            curr = curr.tb_next
            last_frame = curr
        f = getattr(last_frame, "tb_frame", None)
        if f is not None and hasattr(f, "f_code"):
            top_frame = f"{f.f_code.co_filename}:{getattr(last_frame, 'tb_lineno', 0)}:{f.f_code.co_name}"

    return (exc_name, msg, top_frame)


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
    count: int = 1,
) -> str:
    """Format structured crash diagnostics with system versions, repeat count, and traceback."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = [
        "=" * 70,
        f"CircuitSim Crash Report: {now}",
        f"Occurrences:    {count}",
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
    count: int = 1,
) -> Path:
    """Write crash report to crash.log in log_dir (defaulting to get_default_data_dir())."""
    target_dir = log_dir or get_default_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "crash.log"
    report = format_crash_report(exctype, value, tb, count=count)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(report)
    return log_file


def create_crash_dialog(
    message: str,
    count: int = 1,
    log_path: Path | None = None,
    parent: Any = None,
) -> Any:
    """Construct a QMessageBox error dialog with OK and Quit buttons and repeat count."""
    from PySide6.QtWidgets import QMessageBox

    msg = f"CircuitSim encountered an unexpected error:\n\n{message}\n\n"
    if count > 1:
        msg += f"This error occurred {count} times.\n\n"
    if log_path:
        msg += f"A crash log has been saved to:\n{log_path}\n\n"
    msg += f"Please report this issue at:\n{ISSUES_URL}"

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("CircuitSim Error")
    box.setText(msg)
    ok_btn = box.addButton(QMessageBox.StandardButton.Ok)
    quit_btn = box.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(ok_btn)
    box.setProperty("quit_button", quit_btn)
    box.setProperty("ok_button", ok_btn)
    return box


def show_crash_dialog(
    message: str,
    count: int = 1,
    log_path: Path | None = None,
    parent: Any = None,
) -> Any:
    """Show modal error dialog with OK and Quit buttons and repeat count. Returns True if Quit was clicked."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return False

        box = create_crash_dialog(message, count=count, log_path=log_path, parent=parent)

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            # In offscreen platform, do not block on modal event loop
            box.show()
            return box

        box.exec()
        quit_btn = box.property("quit_button")
        if box.clickedButton() == quit_btn:
            app.quit()
            return True
        return False
    except Exception:
        pass
    return False


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

        now = time.monotonic()
        sig = compute_error_signature(exctype, value, tb)

        # 1. Deduplicate by signature within 60 seconds
        if sig in _recent_errors and (now - _recent_errors[sig]["first_time"]) < 60.0:
            _recent_errors[sig]["count"] += 1
            _recent_errors[sig]["last_time"] = now
            return

        entry: dict[str, Any] = {
            "first_time": now,
            "last_time": now,
            "count": 1,
            "exctype": exctype,
            "value": value,
            "tb": tb,
            "dialog_shown": False,
            "logged": False,
        }
        _recent_errors[sig] = entry

        # Print to standard error
        try:
            traceback.print_exception(exctype, value, tb)
        except Exception:
            pass

        # During shutdown, errors go to the log file but must not open a modal dialog
        if is_shutting_down():
            try:
                write_crash_log(exctype, value, tb, log_dir=log_dir, count=1)
            except Exception:
                pass
            return

        # 2. Never open modal dialog from inside paint call: show from event loop via QTimer.singleShot
        def _deferred_dispatch() -> None:
            global _dialog_active, _dialog_call_count
            if is_shutting_down():
                return
            # Re-entrancy guard: never open while another error dialog is open
            if _dialog_active:
                return

            current_entry = _recent_errors.get(sig, entry)
            total_count = current_entry["count"]

            log_path: Path | None = None
            try:
                log_path = write_crash_log(
                    current_entry["exctype"],
                    current_entry["value"],
                    current_entry["tb"],
                    log_dir=log_dir,
                    count=total_count,
                )
                current_entry["logged"] = True
            except Exception:
                pass

            _dialog_active = True
            _dialog_call_count += 1
            current_entry["dialog_shown"] = True
            try:
                if _dialog_handler is not None:
                    _dialog_handler(str(current_entry["value"]), total_count, log_path)
                else:
                    show_crash_dialog(str(current_entry["value"]), total_count, log_path)
            finally:
                _dialog_active = False

        try:
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(0, _deferred_dispatch)
                return
        except Exception:
            pass

        # Fallback if Qt event loop is not active
        try:
            write_crash_log(exctype, value, tb, log_dir=log_dir, count=1)
        except Exception:
            pass

    sys.excepthook = _excepthook
