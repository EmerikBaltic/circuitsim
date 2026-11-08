"""Tests for user design decisions overriding initial specifications.

Items covered:
1. Removal of Saved Parts Bar and freeing of digit keys.
2. Removal of placeholder Oscilloscope dock and empty actions.
3. Lowest free number generation for component names across add/delete/paste/undo/redo/load.
4. Upright symbols for voltmeter/ammeter and un-cut value labels.
"""

from __future__ import annotations

import os
from PySide6.QtCore import QPointF, Qt
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


def test_3_lowest_free_number_for_component_names(tmp_path) -> None:
    """Verify lowest free number assignment across add, delete, paste, undo, redo, and save/load."""
    _get_qapp()
    from circuitsim.canvas.symbol_renderer import SymbolLibrary
    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.io.circ_serializer import save_document, load_document

    lib = SymbolLibrary()
    scene = CircuitScene(lib)

    # 1. Prefix checks
    prefixes_to_test = [
        ("resistor", "R1"),
        ("capacitor", "C1"),
        ("inductor", "L1"),
        ("dc_voltage", "V1"),
        ("voltmeter", "VM1"),
        ("ammeter", "A1"),
        ("lightbulb", "B1"),
        ("switch", "SW1"),
        ("ground", "GND1"),
    ]
    items = {}
    x = 0
    for comp_id, expected_name in prefixes_to_test:
        it = scene.place_new_component(comp_id, QPointF(x, 0))
        assert it.component.name == expected_name
        items[comp_id] = it
        x += 100

    # Add a second voltmeter: VM2
    vm2 = scene.place_new_component("voltmeter", QPointF(x, 0))
    assert vm2.component.name == "VM2"

    # Current names stay unique
    names_before = [it.component.name for it in scene.placed_items]
    assert len(names_before) == len(set(names_before))

    # 2. Delete VM1
    vm1 = items["voltmeter"]
    scene.clearSelection()
    vm1.setSelected(True)
    assert scene.delete_selected()

    # VM1 is gone, VM2 remains
    remaining_names = [it.component.name for it in scene.placed_items]
    assert "VM1" not in remaining_names
    assert "VM2" in remaining_names

    # Adding a meter gives VM1 again (lowest free number)
    vm1_new = scene.place_new_component("voltmeter", QPointF(x + 100, 0))
    assert vm1_new.component.name == "VM1"

    # 3. Pasting gets lowest free number too
    scene.clearSelection()
    vm2.setSelected(True)
    assert scene.copy_selected()
    assert scene.paste_clipboard()

    pasted_vm = [it for it in scene.placed_items if it not in (vm1_new, vm2) and it.component.component_type == "voltmeter"][0]
    assert pasted_vm.component.name == "VM3"

    # Verify names remain unique
    names_with_paste = [it.component.name for it in scene.placed_items]
    assert len(names_with_paste) == len(set(names_with_paste))

    # 4. Undo / Redo sequence
    # Undo paste -> VM3 gone
    scene.undo_stack.undo()
    assert "VM3" not in [it.component.name for it in scene.placed_items]

    # Undo add vm1_new -> VM1 gone, only VM2 remains
    scene.undo_stack.undo()
    assert "VM1" not in [it.component.name for it in scene.placed_items]
    assert "VM2" in [it.component.name for it in scene.placed_items]

    # Undo delete vm1 -> original VM1 is restored!
    scene.undo_stack.undo()
    names_restored = [it.component.name for it in scene.placed_items]
    assert "VM1" in names_restored
    assert "VM2" in names_restored
    assert len(names_restored) == len(set(names_restored))

    # Redo delete -> VM1 deleted again
    scene.undo_stack.redo()
    assert "VM1" not in [it.component.name for it in scene.placed_items]

    # Redo add -> vm1_new re-added
    scene.undo_stack.redo()
    assert "VM1" in [it.component.name for it in scene.placed_items]

    # Redo paste -> VM3 re-added
    scene.undo_stack.redo()
    assert "VM3" in [it.component.name for it in scene.placed_items]

    # 5. Save / Load round trip keeps names
    save_file = tmp_path / "test_names.circ"
    doc = scene.to_document()
    save_document(save_file, doc)

    loaded_doc = load_document(save_file)
    scene2 = CircuitScene(lib)
    scene2.load_document(loaded_doc)

    loaded_names = [it.component.name for it in scene2.placed_items]
    assert set(loaded_names) == set(names_with_paste)
    assert "VM1" in loaded_names and "VM2" in loaded_names and "VM3" in loaded_names

    # After loading, next added meter gets lowest free number (VM4)
    vm4 = scene2.place_new_component("voltmeter", QPointF(x + 200, 0))
    assert vm4.component.name == "VM4"

