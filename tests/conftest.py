"""Shared pytest fixtures, offscreen QApplication, cleanup, and hang watchdog."""

from __future__ import annotations

import faulthandler
import os
import subprocess
import sys
import threading
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def assert_module_has_no_qt_imports(*module_names: str) -> None:
    """Run a clean subprocess importing *module_names* and assert no Qt bindings load."""
    imports = "\n".join(f"import {name}" for name in module_names)
    code = (
        "import sys\n"
        f"{imports}\n"
        "qt = [m for m in sys.modules if m.startswith('PySide6') or m.startswith('PyQt')]\n"
        "assert not qt, f'Unexpected Qt modules imported: {qt}'\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert res.returncode == 0, (
        f"Qt-free import check failed for {module_names}:\n"
        f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Provide one shared offscreen QApplication for the entire test session."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([sys.argv[0]])
    yield app
    app.closeAllWindows()
    app.processEvents()


@pytest.fixture(autouse=True)
def _qt_cleanup_and_watchdog(request: pytest.FixtureRequest, qapp) -> Iterator[None]:
    """Enforce a per-test hang timeout and clean up top-level widgets/threads after each test."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    timeout_s = 30.0
    timed_out = threading.Event()

    def _on_timeout() -> None:
        timed_out.set()
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        app = QApplication.instance()
        if app is not None:
            try:
                app.closeAllWindows()
                app.exit(1)
            except Exception:
                pass

    faulthandler.dump_traceback_later(timeout_s, repeat=False, file=sys.stderr)
    watchdog = threading.Timer(timeout_s, _on_timeout)
    watchdog.daemon = True
    watchdog.start()

    try:
        yield
    finally:
        watchdog.cancel()
        faulthandler.cancel_dump_traceback_later()

        # Clean up any open windows, dialogs, worker threads, and leftover timers.
        for widget in list(QApplication.topLevelWidgets()):
            try:
                if hasattr(widget, "_is_closing"):
                    widget._is_closing = True
                if hasattr(widget, "circuit_scene") and hasattr(widget.circuit_scene, "undo_stack"):
                    try:
                        widget.circuit_scene.undo_stack.setClean()
                    except RuntimeError:
                        pass
                if hasattr(widget, "sim_controller") and widget.sim_controller is not None:
                    try:
                        widget.sim_controller.shutdown()
                    except Exception:
                        pass
                for timer in widget.findChildren(QTimer):
                    try:
                        timer.stop()
                    except RuntimeError:
                        pass
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                pass

        from PySide6.QtCore import QEvent
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()
        qapp.processEvents()

        if "circuitsim.app.crash_handler" in sys.modules:
            try:
                sys.modules["circuitsim.app.crash_handler"].set_shutting_down(False)
            except Exception:
                pass

        if timed_out.is_set():
            pytest.fail(f"Test {request.node.nodeid} exceeded {timeout_s:.0f}s hang timeout")
