"""Tests for user design decisions overriding initial specifications.

Items covered:
1. Removal of Saved Parts Bar and freeing of digit keys.
2. Removal of placeholder Oscilloscope dock and empty actions.
3. Lowest free number generation for component names across add/delete/paste/undo/redo/load.
4. Upright symbols for voltmeter/ammeter and un-cut value labels.
"""

from __future__ import annotations

import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDockWidget, QToolBar

from circuitsim.app.main_window import MainWindow


def _get_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_1_no_saved_parts_bar() -> None:
    """Verify that the 10-slot Saved Parts bar and placeholder are completely removed."""
    _get_qapp()
    win = MainWindow()
    try:
        # Check toolbars
        toolbars = win.findChildren(QToolBar)
        toolbar_titles = [tb.windowTitle() for tb in toolbars]
        assert "Saved Parts Bar" not in toolbar_titles

        # Attribute check
        assert not hasattr(win, "saved_slot_buttons")

        # Check digit keys: no actions on window have single digit shortcuts '0'-'9'
        for act in win.findChildren(QAction):
            sc_text = act.shortcut().toString()
            assert sc_text not in [str(i) for i in range(10)], f"Digit shortcut {sc_text} reserved on {act.text()}"
    finally:
        win.close()
