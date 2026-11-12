"""Tests for ThemePalette completeness, crash handler loop prevention, and paint safety."""

from __future__ import annotations

import os
import subprocess
import sys


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


def test_reproduce_led_paint_palette_attribute_error() -> None:
    """Item 1: Reproduce ThemePalette attribute error when rendering selected/hovered LED in both themes."""
    script = """
import os
import sys
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.app.themes import ThemeMode

captured = []
def hook(exctype, value, tb):
    captured.append((exctype, value, "".join(traceback.format_exception(exctype, value, tb))))

sys.excepthook = hook

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.show()
scene = win.circuit_scene

# 1. Place an LED
led_item = scene.place_new_component("led", QPointF(200.0, 200.0))

# 2. Select it
led_item.setSelected(True)

# 3. Hover it
led_item._is_hovered = True

# 4. Render dark theme
img_dark = QImage(800, 600, QImage.Format.Format_ARGB32)
p_dark = QPainter(img_dark)
try:
    scene.render(p_dark)
except Exception as e:
    hook(type(e), e, e.__traceback__)
finally:
    p_dark.end()

# 5. Switch to Light theme and render
win.apply_theme(ThemeMode.LIGHT)
img_light = QImage(800, 600, QImage.Format.Format_ARGB32)
p_light = QPainter(img_light)
try:
    scene.render(p_light)
except Exception as e:
    hook(type(e), e, e.__traceback__)
finally:
    p_light.end()

win.circuit_scene.undo_stack.setClean()
win.close()

if captured:
    print(f"CAPTURED_EXCEPTIONS_COUNT:{len(captured)}")
    for exctype, val, tb in captured:
        print("--- TRACEBACK BEGIN ---")
        print(tb.strip())
        print("--- TRACEBACK END ---")

assert len(captured) == 0, f"Expected 0 exceptions, caught {len(captured)}: {[str(v) for _, v, _ in captured]}"
"""
    proc = _run_qt_script(script)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    assert proc.returncode == 0, f"Subprocess failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"


def test_every_palette_attribute_in_code_exists_in_both_themes() -> None:
    """Item 2: Verify that every attribute accessed on palette in the codebase exists in both Dark and Light themes."""
    import ast
    from pathlib import Path
    import dataclasses
    from circuitsim.app.themes import DARK_PALETTE, LIGHT_PALETTE, ThemePalette

    fields = {f.name for f in dataclasses.fields(ThemePalette)}
    assert "symbol_label" in fields, "symbol_label must be a defined field of ThemePalette"

    # Verify both palette instances have all attributes with valid non-empty values
    for palette, name in [(DARK_PALETTE, "DARK_PALETTE"), (LIGHT_PALETTE, "LIGHT_PALETTE")]:
        for field in fields:
            assert hasattr(palette, field), f"{name} is missing field {field}"
            val = getattr(palette, field)
            assert val is not None and str(val).strip() != "", f"{name}.{field} must not be empty"

    # Scan all Python files under src/circuitsim for any attribute accessed on an object named palette
    src_dir = Path(__file__).resolve().parents[1] / "src" / "circuitsim"
    accessed_attrs: dict[str, list[str]] = {}

    for py_file in src_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if "palette" in node.value.id.lower():
                    accessed_attrs.setdefault(node.attr, []).append(f"{py_file.name}:{node.lineno}")

    for attr, locations in accessed_attrs.items():
        assert hasattr(DARK_PALETTE, attr), f"Attribute '{attr}' accessed in {locations} is missing from DARK_PALETTE"
        assert hasattr(LIGHT_PALETTE, attr), f"Attribute '{attr}' accessed in {locations} is missing from LIGHT_PALETTE"


def test_smoke_render_every_palette_entry_all_orientations_states_and_themes() -> None:
    """Item 3: Smoke test rendering every palette entry across 8 orientations, selected/hovered, running/stopped, and both themes."""
    script = """
import os
import sys
import time
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.app.themes import ThemeMode
from circuitsim.components import LED, Lightbulb, Switch

captured = []
def hook(exctype, value, tb):
    captured.append((exctype, value, "".join(traceback.format_exception(exctype, value, tb))))

sys.excepthook = hook

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.show()
scene = win.circuit_scene

ORIENTATIONS = [
    (0, False), (90, False), (180, False), (270, False),
    (0, True), (90, True), (180, True), (270, True)
]

PALETTE_KEYS = [
    "ac_voltage", "ammeter", "capacitor", "dc_current", "dc_voltage",
    "ground", "inductor", "led", "lightbulb", "resistor", "switch", "voltmeter"
]

LED_STATES = {
    "off": {"voltage": 0.0, "current": 0.0, "brightness": 0.0, "is_over_current": False, "burned_out": False},
    "dim": {"voltage": 1.8, "current": 0.002, "brightness": 0.316, "is_over_current": False, "burned_out": False},
    "on": {"voltage": 2.0, "current": 0.020, "brightness": 1.0, "is_over_current": False, "burned_out": False},
    "over": {"voltage": 2.2, "current": 0.035, "brightness": 1.32, "is_over_current": True, "burned_out": False},
    "burned": {"voltage": 0.0, "current": 0.0, "brightness": 0.0, "is_over_current": False, "burned_out": True},
    "reverse": {"voltage": -5.0, "current": 0.0, "brightness": 0.0, "is_over_current": False, "burned_out": False},
}

img = QImage(240, 240, QImage.Format.Format_ARGB32)
p = QPainter(img)

render_count = 0
for theme in [ThemeMode.DARK, ThemeMode.LIGHT]:
    win.apply_theme(theme)
    for comp_key in PALETTE_KEYS:
        scene.clear_schematic()
        item = scene.place_new_component(comp_key, QPointF(200.0, 200.0))
        for rot, flip in ORIENTATIONS:
            item.rotation_deg = rot
            item.flipped_h = flip
            for sel in [False, True]:
                item.setSelected(sel)
                for hov in [False, True]:
                    item._is_hovered = hov
                    if comp_key == "led":
                        for state_name, svals in LED_STATES.items():
                            for k, v in svals.items():
                                setattr(item.component, k, v)
                            scene.render(p, QRectF(0, 0, 240, 240), item.sceneBoundingRect())
                            render_count += 1
                    else:
                        for running in [False, True]:
                            if running:
                                item.live_display_value = "5.0 V"
                                if isinstance(item.component, Lightbulb):
                                    item.component.voltage = 12.0
                                    item.component.current = 1.0
                                elif isinstance(item.component, Switch):
                                    item.component.closed = True
                                    item._lever_angle_deg = 0.0
                            else:
                                item.live_display_value = None
                                if isinstance(item.component, Lightbulb):
                                    item.component.voltage = 0.0
                                    item.component.current = 0.0
                                elif isinstance(item.component, Switch):
                                    item.component.closed = False
                                    item._lever_angle_deg = 30.0
                            scene.render(p, QRectF(0, 0, 240, 240), item.sceneBoundingRect())
                            render_count += 1

p.end()
scene.clear_schematic()
win.close()

if captured:
    print(f"CAPTURED {len(captured)} EXCEPTIONS IN SMOKE TEST:")
    for exc in captured:
        print(exc)

assert len(captured) == 0, f"Expected 0 exceptions, caught {len(captured)}"
"""
    proc = _run_qt_script(script, timeout=30)
    assert proc.returncode == 0, f"Subprocess failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"


def test_crash_handler_deduplication_and_no_dialog_loop() -> None:
    """Item 4: Raising the same exception 1000 times inside paint produces exactly one dialog call and one log entry with count."""
    script = """
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from circuitsim.app.crash_handler import (
    create_crash_dialog,
    get_dialog_call_count,
    install_global_exception_hook,
    reset_crash_state,
    set_dialog_handler,
)
from circuitsim.app.main_window import MainWindow

tmp_dir = Path(tempfile.mkdtemp())
try:
    app = QApplication.instance() or QApplication([])
    reset_crash_state()
    install_global_exception_hook(log_dir=tmp_dir)

    dialog_calls = []
    set_dialog_handler(lambda msg, count, path: dialog_calls.append((msg, count, path)))

    win = MainWindow()
    win.show()
    scene = win.circuit_scene
    item = scene.place_new_component("resistor", QPointF(200.0, 200.0))

    # Simulate raising the same exception 1000 times during paint
    for i in range(1000):
        try:
            raise AttributeError("Test paint error: missing attribute token")
        except Exception as e:
            sys.excepthook(type(e), e, e.__traceback__)

    # Process event loop so QTimer.singleShot(0, ...) fires
    app.processEvents()

    # 1. Exactly one dialog call made
    assert len(dialog_calls) == 1, f"Expected 1 dialog call, got {len(dialog_calls)}"
    msg, count, log_path = dialog_calls[0]
    assert count == 1000, f"Expected count 1000, got {count}"
    assert get_dialog_call_count() == 1

    # 2. Exactly one log entry written to crash.log with count
    log_file = tmp_dir / "crash.log"
    assert log_file.exists(), "crash.log must exist"
    log_text = log_file.read_text(encoding="utf-8")
    report_blocks = log_text.count("=" * 70) // 2
    assert report_blocks == 1, f"Expected exactly 1 log block, got {report_blocks}"
    assert "Occurrences:    1000" in log_text

    # 3. Verify dialog has Quit button and repeat count in text
    box = create_crash_dialog("Test error", count=1000, log_path=log_file)
    btn_texts = [b.text() for b in box.buttons()]
    assert any("Quit" in b for b in btn_texts), f"Quit button missing from {btn_texts}"
    assert any("OK" in b for b in btn_texts), f"OK button missing from {btn_texts}"
    assert "This error occurred 1000 times." in box.text()

    scene.clear_schematic()
    win.close()
    reset_crash_state()
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)
"""
    proc = _run_qt_script(script, timeout=20)
    assert proc.returncode == 0, f"Subprocess failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"


def test_paint_safety_guard_on_component_wire_and_junction() -> None:
    """Item 5: Wrap paint() in guard: if drawing fails, log once per item, draw red dashed rect with '!', and continue without propagating."""
    script = """
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from circuitsim.app.crash_handler import install_global_exception_hook, reset_crash_state
from circuitsim.app.main_window import MainWindow
from circuitsim.canvas.wire_item import JunctionItem, WireItem

tmp_dir = Path(tempfile.mkdtemp())
try:
    app = QApplication.instance() or QApplication([])
    reset_crash_state()
    install_global_exception_hook(log_dir=tmp_dir)

    win = MainWindow()
    win.show()
    scene = win.circuit_scene

    # 1. Place component whose inner paint raises
    comp_item = scene.place_new_component("resistor", QPointF(100.0, 100.0))
    def failing_comp_paint(*args, **kwargs):
        raise RuntimeError("Simulated failure in component paint")
    comp_item._paint_impl = failing_comp_paint

    # 2. Place wire whose inner paint raises
    wire_item = WireItem("w_test", [(50.0, 50.0), (150.0, 50.0)])
    scene.addItem(wire_item)
    def failing_wire_paint(*args, **kwargs):
        raise RuntimeError("Simulated failure in wire paint")
    wire_item._paint_impl = failing_wire_paint

    # 3. Place junction item whose inner paint raises
    junc_item = JunctionItem(QPointF(200.0, 200.0))
    scene.addItem(junc_item)
    def failing_junc_paint(*args, **kwargs):
        raise RuntimeError("Simulated failure in junction paint")
    junc_item._paint_impl = failing_junc_paint

    img = QImage(300, 300, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)

    # Rendering scene must NOT raise any exception (paint safety guard catches and draws fallback)
    scene.render(p, QRectF(0, 0, 300, 300), QRectF(0, 0, 300, 300))
    p.end()

    # Verify each item logged its error once
    assert comp_item._paint_error_logged is True
    assert wire_item._paint_error_logged is True
    assert junc_item._paint_error_logged is True

    # Verify fallback red dashed rectangle and '!' were drawn into the image
    red_count = 0
    for y in range(300):
        for x in range(300):
            c = img.pixelColor(x, y)
            if c.red() > 200 and c.green() < 100 and c.blue() < 100:
                red_count += 1

    assert red_count > 50, f"Expected red fallback pixels, found {red_count}"

    # Render a second time: no exceptions, logged flags remain True, no double logging
    p2 = QPainter(img)
    scene.render(p2, QRectF(0, 0, 300, 300), QRectF(0, 0, 300, 300))
    p2.end()

    # Verify log entries exist in crash.log
    log_file = tmp_dir / "crash.log"
    assert log_file.exists(), "crash.log must exist"
    log_text = log_file.read_text(encoding="utf-8")
    assert "Simulated failure in component paint" in log_text
    assert "Simulated failure in wire paint" in log_text

    scene.clear_schematic()
    win.close()
    reset_crash_state()
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)
"""
    proc = _run_qt_script(script, timeout=20)
    assert proc.returncode == 0, f"Subprocess failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"




