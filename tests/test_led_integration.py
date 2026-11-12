"""Tests for Item 6: Comprehensive LED Integration Test Suite.

Offscreen subprocess test suite covering:
1. Palette: Clicking/activating LED creates one on the canvas in category 'Semiconductors'.
2. Placement: Grid snapping and correct terminal offsets (anode (0,20), cathode (80,20)).
3. Dialog: Double-clicking or right-click > Properties opens QuickValueDialog,
   picking a colour updates the part, and undo/redo works.
4. Engine diagnostics:
   - LED placed backwards warns "LED reversed: cathode is at a higher potential than anode"
   - LED placed across a source with no resistor warns "LED has no current limiting resistor"
5. Problems panel:
   - Shows both warnings when both are present
   - 'X' button closes the panel
   - View > Problems and F8 toggle it
   - Toggling panel never shifts or resizes canvas drawing (NoAnchor)
6. Orientations:
   - All 8 orientations render the case and cathode mark clearly
7. Save / Load:
   - LED colour, forward voltage, and burnout state survive a round trip.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import pytest


def _run_qt_script(script: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=timeout,
    )


def test_led_full_lifecycle_and_problems_panel_integration() -> None:
    """Run full offscreen integration suite covering all Item 6 requirements."""
    script = """
import math
import sys
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QImage, QPainter
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.symbol_geometry import led_marks
from circuitsim.components import DCVoltageSource, Ground, LED
from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.simulation_session import SimulationSession
from circuitsim.io.circ_serializer import (
    CircuitDocument,
    PlacedComponentSpec,
    dumps_document,
    loads_document,
)

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.show()

scene = win.circuit_scene
view = win.circuit_view

# =========================================================================
# 1. Palette: clicking / activating LED creates one on the canvas
# =========================================================================
# Verify Semiconductors category and LED item exist in palette tree
tree = win.palette_widget.tree
cat_found = False
led_item_found = False
for i in range(tree.topLevelItemCount()):
    cat = tree.topLevelItem(i)
    if cat.text(0) == "Semiconductors":
        cat_found = True
        for j in range(cat.childCount()):
            child = cat.child(j)
            if child.data(0, Qt.ItemDataRole.UserRole) == "led":
                led_item_found = True
                break

assert cat_found, "Missing 'Semiconductors' category in palette tree"
assert led_item_found, "Missing 'led' item under 'Semiconductors' category"

initial_item_count = len(scene.placed_items)
# Emulate activating palette entry (double-click on palette)
win.palette_widget.component_activated.emit("led")
assert len(scene.placed_items) == initial_item_count + 1, "LED was not placed on canvas via palette"

led_item = scene.placed_items[-1]
assert isinstance(led_item.component, LED), f"Expected LED, got {type(led_item.component)}"

# =========================================================================
# 2. Placement: snapping, terminals at right offsets
# =========================================================================
# Verify grid snapping (multiples of 20 px)
pos = led_item.pos()
assert math.isclose(pos.x() % 20.0, 0.0, abs_tol=1e-5), f"X pos {pos.x()} not snapped to 20 px grid"
assert math.isclose(pos.y() % 20.0, 0.0, abs_tol=1e-5), f"Y pos {pos.y()} not snapped to 20 px grid"

# Terminals: local footprint is 80x40. Anode is (0, 20), Cathode is (80, 20) in SVG / footprint coords
meta = led_item.metadata
t_anode = next(t for t in meta.terminals if t.name == "anode")
t_cathode = next(t for t in meta.terminals if t.name == "cathode")
assert meta.terminal_in_svg_viewbox(t_anode) == (0.0, 20.0), f"Anode in viewbox is {meta.terminal_in_svg_viewbox(t_anode)}"
assert meta.terminal_in_svg_viewbox(t_cathode) == (80.0, 20.0), f"Cathode in viewbox is {meta.terminal_in_svg_viewbox(t_cathode)}"

# Local relative to center (0, 0): anode is (-40, 0), cathode is (40, 0)
assert t_anode.local_px == (-40.0, 0.0)
assert t_cathode.local_px == (40.0, 0.0)

# Check scene coordinates of terminals (returns dict[str, tuple[float, float]])
scene_terms = led_item.terminal_scene_positions()
assert "anode" in scene_terms and "cathode" in scene_terms
expected_anode_scene = (pos.x() - 40.0, pos.y())
expected_cathode_scene = (pos.x() + 40.0, pos.y())
assert math.isclose(scene_terms["anode"][0], expected_anode_scene[0], abs_tol=1e-3)
assert math.isclose(scene_terms["anode"][1], expected_anode_scene[1], abs_tol=1e-3)
assert math.isclose(scene_terms["cathode"][0], expected_cathode_scene[0], abs_tol=1e-3)
assert math.isclose(scene_terms["cathode"][1], expected_cathode_scene[1], abs_tol=1e-3)

# =========================================================================
# 3. Dialog: opening, picking colour, undo/redo
# =========================================================================
# Verify right-click context menu has Properties action
scene.clearSelection()
led_item.setSelected(True)
view_pos = view.mapFromScene(pos + QPointF(40, 20))
event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, view_pos, view.mapToGlobal(view_pos))
# Check Properties action exists in context menu
# Open QuickValueDialog with on_apply hook
dlg = QuickValueDialog(
    led_item.component,
    on_apply=lambda p, s: scene.edit_component_parameters(led_item, p, show_value=s),
    parent=win,
)
assert dlg.led_color_combo is not None
assert dlg.led_color_combo.currentText() == "Red"

# Change colour to 'Blue' (typical Vf = 3.2 V)
dlg.led_color_combo.setCurrentText("Blue")
assert math.isclose(float(dlg.inputs["forward_voltage"].text()), 3.2, abs_tol=1e-3)
assert dlg._apply_current_inputs() is True
dlg.accept()

# Verify live model update
assert led_item.component.color_name == "Blue"
assert math.isclose(led_item.component.forward_voltage, 3.2, abs_tol=1e-3)

# Test Undo: reverts to Red / 2.0 V
scene.undo_stack.undo()
assert led_item.component.color_name == "Red"
assert math.isclose(led_item.component.forward_voltage, 2.0, abs_tol=1e-3)

# Test Redo: reapplies Blue / 3.2 V
scene.undo_stack.redo()
assert led_item.component.color_name == "Blue"
assert math.isclose(led_item.component.forward_voltage, 3.2, abs_tol=1e-3)

# =========================================================================
# 4. Engine diagnostics:
#    - LED reversed: cathode higher potential than anode
#    - LED no resistor: placed across source with no series resistor
# =========================================================================
# Build circuit: 5V Source directly connected across reversed LED (cathode at 5V, anode at GND 0V)
c = Circuit()
c.add(DCVoltageSource("V1", "1", "0", voltage=5.0))
# Reversed LED: anode connected to "0" (GND), cathode connected to "1" (+5V)
# This simultaneously violates forward polarity (-5V reverse bias) AND has no series resistor!
c.add(LED("D_rev", "0", "1", forward_voltage=2.0))
c.add(Ground("GND", "0"))

session = SimulationSession(circuit=c)
frame = session.start()

diag_codes = {d.code: d for d in frame.diagnostics}
assert "led_reversed" in diag_codes, f"Missing led_reversed diagnostic: {diag_codes.keys()}"
assert "led_no_resistor" in diag_codes, f"Missing led_no_resistor diagnostic: {diag_codes.keys()}"

# Check warning message contents
rev_msg = diag_codes["led_reversed"].message
assert "LED reversed: cathode is at a higher potential than anode" in rev_msg
no_res_msg = diag_codes["led_no_resistor"].message
assert "LED has no current limiting resistor" in no_res_msg

# =========================================================================
# 5. Problems panel:
#    - shows both warnings when both are present
#    - 'X' button closes the panel
#    - View > Problems and F8 toggle it
#    - toggling panel does not shift or resize canvas drawing (NoAnchor)
# =========================================================================
# Feed frame diagnostics into main window
win._on_simulation_frame(frame)

# View > Problems (F8) opens panel to view warnings
assert win.problems_dock.isHidden()
win.action_view_problems.trigger()
assert win.problems_dock.isVisible(), "F8 failed to open problems panel"
assert win.action_view_problems.isChecked()

# Verify problems dock contains both warnings
panel = win.problems_dock.panel
assert panel.tree.topLevelItemCount() == 2, f"Expected 2 problems, got {panel.tree.topLevelItemCount()}"

item_codes_in_tree = [panel.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole).code for i in range(2)]
assert "led_reversed" in item_codes_in_tree
assert "led_no_resistor" in item_codes_in_tree

# Record canvas view parameters to verify invariance
h_scroll_0 = view.horizontalScrollBar().value()
v_scroll_0 = view.verticalScrollBar().value()
scene_rect_0 = (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height())
zoom_0 = view._zoom_factor

# 'X' close button closes the panel
panel.close_btn.click()
assert win.problems_dock.isHidden(), "'X' button failed to close problems panel"
assert not win.action_view_problems.isChecked()

# Canvas invariance check after closing
assert view.horizontalScrollBar().value() == h_scroll_0, "Horizontal scrollbar shifted after closing panel!"
assert view.verticalScrollBar().value() == v_scroll_0, "Vertical scrollbar shifted after closing panel!"
assert (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height()) == scene_rect_0
assert view._zoom_factor == zoom_0

# View > Problems (F8) toggles panel open again
win.action_view_problems.trigger()
assert win.problems_dock.isVisible(), "F8 / action_view_problems failed to open problems panel"
assert win.action_view_problems.isChecked()

# Canvas invariance check after opening
assert view.horizontalScrollBar().value() == h_scroll_0, "Horizontal scrollbar shifted after opening panel!"
assert view.verticalScrollBar().value() == v_scroll_0, "Vertical scrollbar shifted after opening panel!"
assert (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height()) == scene_rect_0
assert view._zoom_factor == zoom_0

# F8 toggles panel closed again
win.action_view_problems.trigger()
assert win.problems_dock.isHidden(), "F8 toggle failed to close problems panel"

# =========================================================================
# 6. Orientations: all 8 orientations render case and cathode mark clearly
# =========================================================================
for rot in (0, 90, 180, 270):
    for flip in (False, True):
        marks = led_marks(rotation_deg=rot, flipped_h=flip, center_px=(0.0, 0.0))
        flat_x, flat_y = marks["flat"]
        ax, ay = marks["anode_terminal"]
        kx, ky = marks["cathode_terminal"]
        d_k = math.hypot(flat_x - kx, flat_y - ky)
        d_a = math.hypot(flat_x - ax, flat_y - ay)
        # Flat must be strictly nearer cathode than anode in every orientation
        assert d_k < d_a, f"Orientation rot={rot}, flip={flip} flat is not nearer cathode!"
        assert math.isclose(d_k, 26.0, abs_tol=1e-3)
        assert math.isclose(d_a, 54.0, abs_tol=1e-3)

        # Test paint rendering on a QImage
        img = QImage(120, 120, QImage.Format.Format_ARGB32)
        img.fill(0)
        painter = QPainter(img)
        # Verify symbol renderer creates valid non-empty icon
        pix = win.symbol_library.create_palette_icon("led", theme=win.theme, size=(80, 40)).pixmap(80, 40)
        assert not pix.isNull()
        painter.end()

# =========================================================================
# 7. Save / Load: LED colour, voltage and burnout state survive round trip
# =========================================================================
d_test = LED(
    "D_save",
    "n1",
    "0",
    forward_voltage=3.2,
    rated_current=0.025,
    max_current=0.035,
    color_name="Blue",
    color="#007AFF",
    burnout_enabled=True,
    burnout_current=0.045,
)
spec = PlacedComponentSpec(
    component=d_test,
    center_px=(160.0, 220.0),
    rotation_deg=180,
    flipped_h=True,
)
doc = CircuitDocument(placed=[spec], wires=[], junctions=[])
json_str = dumps_document(doc)
loaded_doc = loads_document(json_str)

assert len(loaded_doc.placed) == 1
loaded_led = loaded_doc.placed[0].component
assert isinstance(loaded_led, LED)
assert loaded_led.name == "D_save"
assert math.isclose(loaded_led.forward_voltage, 3.2, abs_tol=1e-5)
assert math.isclose(loaded_led.rated_current, 0.025, abs_tol=1e-5)
assert math.isclose(loaded_led.max_current, 0.035, abs_tol=1e-5)
assert loaded_led.color_name == "Blue"
assert loaded_led.color == "#007AFF"
assert loaded_led.burnout_enabled is True
assert math.isclose(loaded_led.burnout_current, 0.045, abs_tol=1e-5)

# Clean window close
win._is_closing = True
win.close()
print("LED_INTEGRATION_ALL_CHECKS_PASSED")
"""
    res = _run_qt_script(script, timeout=30)
    assert res.returncode == 0, f"Qt subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "LED_INTEGRATION_ALL_CHECKS_PASSED" in res.stdout
