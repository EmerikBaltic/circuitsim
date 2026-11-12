"""Tests for Item 2: LED Colour Dialog, Live Editing, Undo/Redo, Serialization, and Canvas Invariance."""

from __future__ import annotations

import math
import os
import subprocess
import sys
import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.connectivity import PlacedComponentSpec
from circuitsim.components import LED, LED_COLOUR_PRESETS, Resistor
from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog
from circuitsim.io.circ_serializer import (
    CircuitDocument,
    dumps_document,
    loads_document,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_led_color_presets_and_swatches(qapp: QApplication) -> None:
    """Verify color presets, swatches, datasheet labels, and automatic switch to Custom on manual edit."""
    led = LED("D1", "n1", "0", forward_voltage=2.0, color_name="Red")
    dlg = QuickValueDialog(led)

    assert dlg.led_color_combo is not None
    assert dlg.led_datasheet_lbl is not None
    assert dlg.led_datasheet_hint_lbl is not None

    expected_colors = [
        "Red",
        "Orange",
        "Yellow",
        "Green",
        "Pure green",
        "Blue",
        "White",
        "Custom",
    ]
    actual_colors = [
        dlg.led_color_combo.itemText(i)
        for i in range(dlg.led_color_combo.count())
    ]
    assert actual_colors == expected_colors

    # Each item must have an icon (swatch)
    for i in range(dlg.led_color_combo.count()):
        icon = dlg.led_color_combo.itemIcon(i)
        assert not icon.isNull(), f"Color {actual_colors[i]} missing swatch icon"

    # Default is Red -> 2.0 V
    assert dlg.led_color_combo.currentText() == "Red"
    assert dlg.inputs["forward_voltage"].text() == "2"
    assert "2.0 V" in dlg.led_datasheet_lbl.text()
    assert "1.8–2.4 V" in dlg.led_datasheet_lbl.text()
    assert "typical datasheet values; real LEDs vary by about +-0.3 V" in dlg.led_datasheet_hint_lbl.text()

    # Select Blue -> forward voltage updates to 3.2 V immediately
    dlg.led_color_combo.setCurrentText("Blue")
    assert dlg.inputs["forward_voltage"].text() == "3.2"
    assert "3.2 V" in dlg.led_datasheet_lbl.text()
    assert "3.0–3.6 V" in dlg.led_datasheet_lbl.text()

    # Select Green -> forward voltage updates to 2.2 V immediately
    dlg.led_color_combo.setCurrentText("Green")
    assert dlg.inputs["forward_voltage"].text() == "2.2"
    assert "2.2 V" in dlg.led_datasheet_lbl.text()
    assert "2.0–2.6 V" in dlg.led_datasheet_lbl.text()

    # Edit voltage by hand to 2.8 V -> combo automatically switches to Custom
    dlg.inputs["forward_voltage"].setText("2.8")
    assert dlg.led_color_combo.currentText() == "Custom"
    assert "Custom" in dlg.led_datasheet_lbl.text()


def test_led_dialog_burnout_and_current_validation(qapp: QApplication) -> None:
    """Verify editable rated current, max current, burnout checkbox, and threshold validation."""
    led = LED("D1", "n1", "0", forward_voltage=2.0, rated_current=0.02, max_current=0.03)
    dlg = QuickValueDialog(led)

    assert "rated_current" in dlg.inputs
    assert "max_current" in dlg.inputs
    assert dlg.led_burnout_cb is not None
    assert dlg.led_burnout_current_edit is not None

    assert not dlg.led_burnout_cb.isChecked()
    dlg.led_burnout_cb.setChecked(True)
    dlg.led_burnout_current_edit.setText("45m")

    parsed, err = dlg.validate_inputs()
    assert err is None
    assert parsed is not None
    assert math.isclose(parsed["burnout_current"], 0.045, abs_tol=1e-5)
    assert parsed["burnout_enabled"] is True

    # Invalid negative threshold
    dlg.led_burnout_current_edit.setText("-10m")
    parsed_bad, err_bad = dlg.validate_inputs()
    assert parsed_bad is None
    assert "greater than 0" in (err_bad or "")


def test_led_circ_file_round_trip_serialization() -> None:
    """Verify LED parameters, color name, hex color, and burnout settings survive save/load round-trip."""
    led = LED(
        "D1",
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
        component=led,
        center_px=(100.0, 140.0),
        rotation_deg=90,
        flipped_h=True,
    )
    doc = CircuitDocument(placed=[spec], wires=[], junctions=[])

    json_text = dumps_document(doc)
    loaded_doc = loads_document(json_text)

    assert len(loaded_doc.placed) == 1
    loaded_spec = loaded_doc.placed[0]
    loaded_led = loaded_spec.component

    assert isinstance(loaded_led, LED)
    assert loaded_led.name == "D1"
    assert math.isclose(loaded_led.forward_voltage, 3.2, abs_tol=1e-5)
    assert math.isclose(loaded_led.rated_current, 0.025, abs_tol=1e-5)
    assert math.isclose(loaded_led.max_current, 0.035, abs_tol=1e-5)
    assert loaded_led.color_name == "Blue"
    assert loaded_led.color == "#007AFF"
    assert loaded_led.burnout_enabled is True
    assert math.isclose(loaded_led.burnout_current, 0.045, abs_tol=1e-5)
    assert loaded_spec.center_px == (100.0, 140.0)
    assert loaded_spec.rotation_deg == 90
    assert loaded_spec.flipped_h is True


def _run_qt_script(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=25,
    )


def test_dialog_never_shifts_canvas_view_or_scene_rect() -> None:
    """Offscreen Qt test: verify that double-click edit dialog does not shift canvas view or scene rectangle."""
    script = """
import math
import sys
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.show()

scene = win.circuit_scene
view = win.circuit_view

# Place an LED and a resistor on canvas
led_item = scene.place_new_component("led", QPointF(200.0, 200.0))
res_item = scene.place_new_component("resistor", QPointF(300.0, 200.0))

# Record view scrollbar values and scene rect before opening dialog
h_val_before = view.horizontalScrollBar().value()
v_val_before = view.verticalScrollBar().value()
scene_rect_before = (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height())
zoom_before = view._zoom_factor

# Open QuickValueDialog for LED and apply changes
dlg = QuickValueDialog(led_item.component, on_apply=lambda p, s: scene.edit_component_parameters(led_item, p, show_value=s), parent=win)
dlg.led_color_combo.setCurrentText("Pure green")
applied = dlg._apply_current_inputs()
assert applied is True
dlg.accept()

# Verify live parameter update
assert led_item.component.color_name == "Pure green"
assert math.isclose(led_item.component.forward_voltage, 3.2, abs_tol=1e-4)

# Record view scrollbar values and scene rect after closing dialog
h_val_after = view.horizontalScrollBar().value()
v_val_after = view.verticalScrollBar().value()
scene_rect_after = (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height())
zoom_after = view._zoom_factor

assert h_val_before == h_val_after, f"Horizontal scrollbar shifted! {h_val_before} != {h_val_after}"
assert v_val_before == v_val_after, f"Vertical scrollbar shifted! {v_val_before} != {v_val_after}"
assert scene_rect_before == scene_rect_after, f"Scene rect changed! {scene_rect_before} != {scene_rect_after}"
assert zoom_before == zoom_after, f"Zoom changed! {zoom_before} != {zoom_after}"

# Verify undo/redo
scene.undo_stack.undo()
assert led_item.component.color_name == "Red"
assert math.isclose(led_item.component.forward_voltage, 2.0, abs_tol=1e-4)

scene.undo_stack.redo()
assert led_item.component.color_name == "Pure green"
assert math.isclose(led_item.component.forward_voltage, 3.2, abs_tol=1e-4)

win._is_closing = True
win.close()
"""
    res = _run_qt_script(script)
    assert res.returncode == 0, f"Qt subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
