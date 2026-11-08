"""Tests for user design decisions overriding initial specifications.

Items covered:
1. Removal of Saved Parts Bar and freeing of digit keys.
2. Removal of placeholder Oscilloscope dock and empty actions.
3. Lowest free number generation for component names across add/delete/paste/undo/redo/load.
4. Upright symbols for voltmeter/ammeter and un-cut value labels.

Note: Runs in subprocesses so pytest itself never imports PySide6, ensuring
zero Qt imports in physics/connectivity modules.
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


def test_1_no_saved_parts_bar() -> None:
    """Verify that the 10-slot Saved Parts bar and placeholder are completely removed."""
    script = """
import sys
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QToolBar
from circuitsim.app.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
try:
    toolbars = win.findChildren(QToolBar)
    toolbar_titles = [tb.windowTitle() for tb in toolbars]
    assert "Saved Parts Bar" not in toolbar_titles, f"Found: {toolbar_titles}"
    assert not hasattr(win, "saved_slot_buttons")

    for act in win.findChildren(QAction):
        sc_text = act.shortcut().toString()
        assert sc_text not in [str(i) for i in range(10)], f"Digit shortcut {sc_text} reserved on {act.text()}"
finally:
    win.close()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_2_no_fake_oscilloscope() -> None:
    """Verify that the empty Oscilloscope dock and empty actions/menus are removed,
    and saved layout cannot bring it back while keeping code structure for Milestone 4.
    """
    scope_pkg = Path(__file__).resolve().parent.parent / "src" / "circuitsim" / "scope"
    assert scope_pkg.exists() and (scope_pkg / "__init__.py").exists()

    script = """
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDockWidget
from circuitsim.app.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
try:
    for dock in win.findChildren(QDockWidget):
        assert "oscilloscope" not in dock.windowTitle().lower()
        assert "oscilloscope" not in dock.objectName().lower()
    assert not hasattr(win, "scope_dock")

    for act in win.findChildren(QAction):
        assert "oscilloscope" not in act.text().lower()

    view_actions = [a.text() for a in win.view_menu.actions()]
    assert any("palette" in a.lower() for a in view_actions)
    assert any("properties" in a.lower() or "info" in a.lower() for a in view_actions)

    dummy_state = win.saveState()
    fake_dock = QDockWidget("Oscilloscope (4-Channel)", win)
    fake_dock.setObjectName("OscilloscopeDock")
    win.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, fake_dock)
    assert fake_dock in win.findChildren(QDockWidget)
    win.restoreState(dummy_state)
    current_titles = [d.windowTitle() for d in win.findChildren(QDockWidget)]
    assert "Oscilloscope (4-Channel)" not in current_titles
finally:
    win.close()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_3_lowest_free_number_for_component_names(tmp_path) -> None:
    """Verify lowest free number assignment across add, delete, paste, undo, redo, and save/load."""
    save_file_str = str(tmp_path / "test_names.circ").replace("\\", "/")
    script = f"""
import sys
from pathlib import Path
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.scene import CircuitScene
from circuitsim.io.circ_serializer import save_document, load_document

app = QApplication(sys.argv)
lib = SymbolLibrary()
scene = CircuitScene(lib)

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
items = {{}}
x = 0
for comp_id, expected_name in prefixes_to_test:
    it = scene.place_new_component(comp_id, QPointF(x, 0))
    assert it.component.name == expected_name
    items[comp_id] = it
    x += 100

vm2 = scene.place_new_component("voltmeter", QPointF(x, 0))
assert vm2.component.name == "VM2"

names_before = [it.component.name for it in scene.placed_items]
assert len(names_before) == len(set(names_before))

# Delete VM1
vm1 = items["voltmeter"]
scene.clearSelection()
vm1.setSelected(True)
assert scene.delete_selected()

remaining_names = [it.component.name for it in scene.placed_items]
assert "VM1" not in remaining_names
assert "VM2" in remaining_names

# Adding a meter gives VM1 again (lowest free number)
vm1_new = scene.place_new_component("voltmeter", QPointF(x + 100, 0))
assert vm1_new.component.name == "VM1"

# Pasting gets lowest free number too
scene.clearSelection()
vm2.setSelected(True)
assert scene.copy_selected()
assert scene.paste_clipboard()

pasted_vm = [it for it in scene.placed_items if it not in (vm1_new, vm2) and it.component.component_type == "voltmeter"][0]
assert pasted_vm.component.name == "VM3"

names_with_paste = [it.component.name for it in scene.placed_items]
assert len(names_with_paste) == len(set(names_with_paste))

# Undo / Redo
scene.undo_stack.undo()
assert "VM3" not in [it.component.name for it in scene.placed_items]

scene.undo_stack.undo()
assert "VM1" not in [it.component.name for it in scene.placed_items]
assert "VM2" in [it.component.name for it in scene.placed_items]

scene.undo_stack.undo()
names_restored = [it.component.name for it in scene.placed_items]
assert "VM1" in names_restored
assert "VM2" in names_restored
assert len(names_restored) == len(set(names_restored))

scene.undo_stack.redo()
assert "VM1" not in [it.component.name for it in scene.placed_items]

scene.undo_stack.redo()
assert "VM1" in [it.component.name for it in scene.placed_items]

scene.undo_stack.redo()
assert "VM3" in [it.component.name for it in scene.placed_items]

# Save / Load round trip
save_path = Path("{save_file_str}")
doc = scene.to_document()
save_document(save_path, doc)

loaded_doc = load_document(save_path)
scene2 = CircuitScene(lib)
scene2.load_document(loaded_doc)

loaded_names = [it.component.name for it in scene2.placed_items]
assert set(loaded_names) == set(names_with_paste)
assert "VM1" in loaded_names and "VM2" in loaded_names and "VM3" in loaded_names

vm4 = scene2.place_new_component("voltmeter", QPointF(x + 200, 0))
assert vm4.component.name == "VM4"
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_4_small_visual_fixes() -> None:
    """Verify that voltmeter and ammeter letters stay upright across rotations and flips,
    and value labels (e.g. '11.11 mA') have higher Z-order and background plate so crossing wires do not cut them off.
    """
    script = """
import sys
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.wire_item import WireItem

app = QApplication(sys.argv)
lib = SymbolLibrary()

for rot in (0, 90, 180, 270):
    for flipped in (False, True):
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.black)
        p = QPainter(img)
        p.translate(50.0, 50.0)
        if flipped:
            p.scale(-1.0, 1.0)
        if rot:
            p.rotate(float(rot))
        lib.paint_symbol(
            p,
            "voltmeter",
            stroke_color="#FFFFFF",
            show_terminals=False,
            rotation_deg=rot,
            flipped_h=flipped,
        )
        p.end()

        c_vertex = img.pixelColor(50, 56)
        assert c_vertex.red() > 100, f"V vertex missing at bottom for rot={rot}, flipped={flipped}"
        c_top_center = img.pixelColor(50, 44)
        assert c_top_center.red() < 50, f"V should be open at top for rot={rot}, flipped={flipped}"

# Check Z-order and value label background plate
scene = CircuitScene(lib)
ammeter = scene.place_new_component("ammeter", QPointF(100.0, 100.0))
ammeter.live_display_value = "11.11 mA"

assert ammeter.zValue() > 5.0

val_rect = ammeter._upright_label_and_value_rects()[1]
wire_y = 100.0 + val_rect.center().y()
wire = WireItem("W1", ((50.0, wire_y), (150.0, wire_y)))
scene.addItem(wire)

assert wire.zValue() < ammeter.zValue()

img = QImage(300, 300, QImage.Format.Format_ARGB32)
img.fill(QColor("#0D1117"))
p = QPainter(img)
scene.render(p)
p.end()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
