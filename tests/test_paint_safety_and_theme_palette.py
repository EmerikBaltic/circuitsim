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
