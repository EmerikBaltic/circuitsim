"""Unit tests for Item 4:
a) Clicking a switch marks file modified (title asterisk) but is NOT undoable.
b) Selection box of voltage source does not touch GND2 label (geometry clearance).
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def test_switch_toggle_marks_file_modified_without_undo(qapp) -> None:
    """Toggling a switch adds asterisk to title and sets has_unsaved_changes, but does not push to QUndoStack."""
    from PySide6.QtCore import QPointF
    from circuitsim.app.main_window import MainWindow

    win = MainWindow()
    scene = win.circuit_scene

    sw_item = scene.place_new_component("switch", QPointF(100.0, 100.0))
    scene.undo_stack.clear()
    scene.undo_stack.setClean()
    win._switch_modified = False
    win._update_window_title()

    assert not win.has_unsaved_changes()
    assert "*" not in win.windowTitle()
    assert not scene.undo_stack.canUndo()
    initial_undo_count = scene.undo_stack.count()

    scene.toggle_switch_item(sw_item)

    assert "*" in win.windowTitle(), f"Title lacks asterisk: {win.windowTitle()}"
    assert win.has_unsaved_changes()
    assert scene.undo_stack.count() == initial_undo_count, "Undo stack count changed on switch toggle"
    assert not scene.undo_stack.canUndo(), "Switch toggle was pushed to QUndoStack"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "test.circ"
        saved = win.save_to_path(save_path)
        assert saved
        assert not win.has_unsaved_changes()
        assert "*" not in win.windowTitle()


def test_voltage_source_selection_box_does_not_touch_ground_label(qapp) -> None:
    """Selection box of voltage source does not touch the label of an adjacent Ground part."""
    from circuitsim.canvas.component_item import ComponentItem
    from circuitsim.canvas.symbol_renderer import SymbolLibrary
    from circuitsim.components import DCVoltageSource, Ground

    lib = SymbolLibrary()

    vs = ComponentItem(DCVoltageSource("V1", "a", "b", voltage=12.0), lib)
    vs.setPos(100.0, 100.0)
    vs.set_rotation_deg(90)

    gnd = ComponentItem(Ground("GND2"), lib)
    gnd.setPos(100.0, 160.0)

    vs_sel_box_scene = vs.selection_outline_rect_local().translated(vs.pos())
    gnd_lbl_rect_scene = gnd._upright_label_and_value_rects()[0].translated(gnd.pos())

    assert not vs_sel_box_scene.intersects(gnd_lbl_rect_scene), (
        f"Collision: VS selection box {vs_sel_box_scene} intersects GND2 label {gnd_lbl_rect_scene}"
    )

    clearance_y = gnd_lbl_rect_scene.top() - vs_sel_box_scene.bottom()
    assert clearance_y >= 15.0, f"Insufficient clearance: {clearance_y:.1f} px"

    vs_h = ComponentItem(DCVoltageSource("V1", "a", "b", voltage=12.0), lib)
    vs_h.setPos(100.0, 100.0)
    vs_h.set_rotation_deg(0)

    gnd_h = ComponentItem(Ground("GND2"), lib)
    gnd_h.setPos(140.0, 120.0)

    vs_h_sel_box = vs_h.selection_outline_rect_local().translated(vs_h.pos())
    gnd_h_lbl_rect = gnd_h._upright_label_and_value_rects()[0].translated(gnd_h.pos())

    assert not vs_h_sel_box.intersects(gnd_h_lbl_rect), (
        f"Collision: Horizontal VS selection box {vs_h_sel_box} intersects GND2 label {gnd_h_lbl_rect}"
    )
    clearance_h_y = gnd_h_lbl_rect.top() - vs_h_sel_box.bottom()
    assert clearance_h_y >= 5.0, f"Insufficient clearance: {clearance_h_y:.1f} px"
