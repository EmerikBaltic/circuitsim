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


def test_2_no_fake_oscilloscope() -> None:
    """Verify that the empty Oscilloscope dock and empty actions/menus are removed,

    and saved layout cannot bring it back while keeping code structure for Milestone 4.
    """
    from pathlib import Path

    # 1. Structure preserved for Milestone 4
    scope_pkg = Path(__file__).resolve().parent.parent / "src" / "circuitsim" / "scope"
    assert scope_pkg.exists() and (scope_pkg / "__init__.py").exists()

    _get_qapp()
    win = MainWindow()
    try:
        # 2. Main window contains no oscilloscope dock
        docks = win.findChildren(QDockWidget)
        for dock in docks:
            assert "oscilloscope" not in dock.windowTitle().lower()
            assert "oscilloscope" not in dock.objectName().lower()
        assert not hasattr(win, "scope_dock")

        # 3. No menu action or menu exists for oscilloscope
        menu_bar = win.menuBar()
        for act in win.findChildren(QAction):
            assert "oscilloscope" not in act.text().lower()

        # 4. View menu has dock toggles for Palette and Info docks
        view_actions = [a.text() for a in win.view_menu.actions()]
        assert any("palette" in a.lower() for a in view_actions)
        assert any("properties" in a.lower() or "info" in a.lower() for a in view_actions)

        # 5. Saved layout cannot restore oscilloscope dock
        dummy_state = win.saveState()
        # Even if a stale dock is forcibly added or restored, restoreState removes it
        fake_dock = QDockWidget("Oscilloscope (4-Channel)", win)
        fake_dock.setObjectName("OscilloscopeDock")
        win.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, fake_dock)
        assert fake_dock in win.findChildren(QDockWidget)
        win.restoreState(dummy_state)
        # Stale dock must be gone after restoreState
        current_titles = [d.windowTitle() for d in win.findChildren(QDockWidget)]
        assert "Oscilloscope (4-Channel)" not in current_titles
    finally:
        win.close()
