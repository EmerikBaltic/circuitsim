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

