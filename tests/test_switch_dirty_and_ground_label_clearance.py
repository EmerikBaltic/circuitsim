"""Unit tests for Item 4:
a) Clicking a switch marks file modified (title asterisk) but is NOT undoable.
b) Selection box of voltage source does not touch GND2 label (geometry clearance).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_qt(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_switch_toggle_marks_file_modified_without_undo() -> None:
    """Toggling a switch adds asterisk to title and sets has_unsaved_changes, but does not push to QUndoStack."""
    script = """
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from circuitsim.app.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
scene = win.circuit_scene

# Place a switch
sw_item = scene.place_new_component("switch", QPointF(100.0, 100.0))
# Clear undo stack and modification flag to establish clean baseline
scene.undo_stack.clear()
scene.undo_stack.setClean()
win._switch_modified = False
win._update_window_title()

assert not win.has_unsaved_changes()
assert "*" not in win.windowTitle()
assert not scene.undo_stack.canUndo()
initial_undo_count = scene.undo_stack.count()

# Toggle switch
scene.toggle_switch_item(sw_item)

# 1. Title must show asterisk
assert "*" in win.windowTitle(), f"Title lacks asterisk: {win.windowTitle()}"
# 2. Document is marked modified
assert win.has_unsaved_changes()
# 3. Must NOT be undoable
assert scene.undo_stack.count() == initial_undo_count, "Undo stack count changed on switch toggle"
assert not scene.undo_stack.canUndo(), "Switch toggle was pushed to QUndoStack"

# 4. Saving clears modification
with tempfile.TemporaryDirectory() as tmpdir:
    save_path = Path(tmpdir) / "test.circ"
    saved = win.save_to_path(save_path)
    assert saved
    assert not win.has_unsaved_changes()
    assert "*" not in win.windowTitle()

print("OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "OK" in res.stdout


def test_voltage_source_selection_box_does_not_touch_ground_label() -> None:
    """Selection box of voltage source does not touch the label of an adjacent Ground part."""
    script = """
import sys
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication
from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.components import DCVoltageSource, Ground

app = QApplication(sys.argv)
lib = SymbolLibrary()

# --- Case A: Vertical Voltage Source V1 with Ground GND2 connected to bottom terminal ---
# V1 center at (100, 100), rotation 90 deg:
# negative terminal is at (100, 140)
vs = ComponentItem(DCVoltageSource("V1", "a", "b", voltage=12.0), lib)
vs.setPos(100.0, 100.0)
vs.set_rotation_deg(90)

# GND2 placed directly below V1 so its terminal (0, -20) connects to (100, 140) -> center is (100, 160)
gnd = ComponentItem(Ground("GND2"), lib)
gnd.setPos(100.0, 160.0)

vs_sel_box_scene = vs.selection_outline_rect_local().translated(vs.pos())
gnd_lbl_rect_scene = gnd._upright_label_and_value_rects()[0].translated(gnd.pos())

# Must NOT intersect
assert not vs_sel_box_scene.intersects(gnd_lbl_rect_scene), (
    f"Collision: VS selection box {vs_sel_box_scene} intersects GND2 label {gnd_lbl_rect_scene}"
)

# Minimum vertical clearance must be positive (at least 15 px)
clearance_y = gnd_lbl_rect_scene.top() - vs_sel_box_scene.bottom()
assert clearance_y >= 15.0, f"Insufficient clearance: {clearance_y:.1f} px"

# --- Case B: Horizontal Voltage Source V1 with Ground GND2 at negative terminal (140, 100) ---
vs_h = ComponentItem(DCVoltageSource("V1", "a", "b", voltage=12.0), lib)
vs_h.setPos(100.0, 100.0)
vs_h.set_rotation_deg(0)

# Ground connected at (140, 100) -> center at (140, 120)
gnd_h = ComponentItem(Ground("GND2"), lib)
gnd_h.setPos(140.0, 120.0)

vs_h_sel_box = vs_h.selection_outline_rect_local().translated(vs_h.pos())
gnd_h_lbl_rect = gnd_h._upright_label_and_value_rects()[0].translated(gnd_h.pos())

assert not vs_h_sel_box.intersects(gnd_h_lbl_rect), (
    f"Collision: Horizontal VS selection box {vs_h_sel_box} intersects GND2 label {gnd_h_lbl_rect}"
)
clearance_h_y = gnd_h_lbl_rect.top() - vs_h_sel_box.bottom()
assert clearance_h_y >= 5.0, f"Insufficient clearance: {clearance_h_y:.1f} px"

print("OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "OK" in res.stdout
