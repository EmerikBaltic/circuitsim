"""Global unhandled exception hook, crash logging, and version diagnostics for CircuitSim."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import platform
import re
import sys
import time
import traceback
from typing import Any, Callable

import PySide6

try:
    from PySide6.QtWidgets import QMessageBox

    _orig_critical: Any = getattr(QMessageBox, "critical", None)
except Exception:
    _orig_critical = None

from circuitsim.app.settings import AppSettings, get_default_data_dir

REPO_URL: str = "https://github.com/EmerikBaltic/circuitsim"
ISSUES_URL: str = "https://github.com/EmerikBaltic/circuitsim/issues"

_shutting_down: bool = False
_dialog_active: bool = False
_dialog_call_count: int = 0
_dialog_handler: Callable[[str, int, Path | None], None] | None = None
_recent_errors: dict[tuple[str, str, str], dict[str, Any]] = {}
_global_log_dir: Path | None = None


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
    global _dialog_active, _dialog_call_count, _dialog_handler, _global_log_dir
    _recent_errors.clear()
    _dialog_active = False
    _dialog_call_count = 0
    _dialog_handler = None
    _global_log_dir = None


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
    """Write crash report to crash.log in log_dir (defaulting to _global_log_dir or get_default_data_dir())."""
    target_dir = log_dir or _global_log_dir or get_default_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "crash.log"
    report = format_crash_report(exctype, value, tb, count=count)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(report)
    return log_file


def update_crash_log_count(
    log_file: Path,
    new_count: int,
) -> None:
    """Update occurrence count in the last report block of crash.log."""
    try:
        if not log_file.exists():
            return
        text = log_file.read_text(encoding="utf-8")
        pattern = r"Occurrences:\s+\d+"
        matches = list(re.finditer(pattern, text))
        if matches:
            last_match = matches[-1]
            start, end = last_match.span()
            updated = text[:start] + f"Occurrences:    {new_count}" + text[end:]
            log_file.write_text(updated, encoding="utf-8")
    except Exception:
        pass


def is_inside_paint(value: BaseException | None = None, tb: object = None) -> bool:
    """Return True if exception occurred inside a paint or render call."""
    if value is not None and "paint" in str(value).lower():
        return True
    curr = tb
    while curr is not None:
        f = getattr(curr, "tb_frame", None)
        if f and hasattr(f, "f_code"):
            name = f.f_code.co_name.lower()
            if any(p in name for p in ("paint", "drawforeground", "drawbackground", "paintevent", "_paint_impl")):
                return True
        curr = getattr(curr, "tb_next", None)
    try:
        frame = sys._getframe(1)
        while frame is not None:
            if hasattr(frame, "f_code"):
                name = frame.f_code.co_name.lower()
                if any(p in name for p in ("paint", "drawforeground", "drawbackground", "paintevent", "_paint_impl")):
                    return True
            frame = frame.f_back
    except Exception:
        pass
    return False


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
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app is None:
            return False

        if _orig_critical is not None and QMessageBox.critical is not _orig_critical:
            msg = f"CircuitSim encountered an unexpected error:\n\n{message}\n\n"
            if count > 1:
                msg += f"This error occurred {count} times.\n\n"
            if log_path:
                msg += f"A crash log has been saved to:\n{log_path}\n\n"
            msg += f"Please report this issue at:\n{ISSUES_URL}"
            return QMessageBox.critical(parent, "CircuitSim Error", msg)

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
    global _global_log_dir
    if log_dir is not None:
        _global_log_dir = log_dir
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
            lp = _recent_errors[sig].get("log_path")
            if lp:
                update_crash_log_count(lp, _recent_errors[sig]["count"])
            return

        # Write crash log immediately on first occurrence so file exists synchronously
        log_path: Path | None = None
        try:
            log_path = write_crash_log(exctype, value, tb, log_dir=log_dir, count=1)
        except Exception:
            pass

        entry: dict[str, Any] = {
            "first_time": now,
            "last_time": now,
            "count": 1,
            "exctype": exctype,
            "value": value,
            "tb": tb,
            "dialog_shown": False,
            "log_path": log_path,
        }
        _recent_errors[sig] = entry

        # Print to standard error
        try:
            traceback.print_exception(exctype, value, tb)
        except Exception:
            pass

        # During shutdown, errors go to the log file but must not open a modal dialog
        if is_shutting_down():
            return

        def _dispatch_dialog(target_sig: tuple[str, str, str]) -> None:
            global _dialog_active, _dialog_call_count
            if is_shutting_down():
                return
            if _dialog_active:
                return

            current_entry = _recent_errors.get(target_sig)
            if current_entry is None or current_entry.get("dialog_shown"):
                return

            total_count = current_entry["count"]
            current_log_path = current_entry.get("log_path")
            if total_count > 1 and current_log_path:
                update_crash_log_count(current_log_path, total_count)

            _dialog_active = True
            _dialog_call_count += 1
            current_entry["dialog_shown"] = True
            try:
                if _dialog_handler is not None:
                    _dialog_handler(str(current_entry["value"]), total_count, current_log_path)
                else:
                    show_crash_dialog(str(current_entry["value"]), total_count, current_log_path)
            finally:
                _dialog_active = False

        if is_inside_paint(value, tb):
            try:
                from PySide6.QtCore import QTimer
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    QTimer.singleShot(0, lambda: _dispatch_dialog(sig))
                    return
            except Exception:
                pass

        _dispatch_dialog(sig)

    sys.excepthook = _excepthook
