"""Item 0: quick checks from the last report.

0a. Drawing (terminal dots), hit areas, snapping, terminal positions and the netlist
    all take terminal positions from `transform_terminal_position`. Compared for all
    11 part types and all 8 orientations.
0b. A deliberate 40 px drag moves a part by exactly two grid cells; a 3 px jitter
    moves it by 0 px.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _run_qt(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_0a_all_terminal_consumers_share_transform_terminal_position() -> None:
    """Drawn terminal dots, shape(), snapping, item positions and netlist specs agree."""
    script = """
import sys
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from circuitsim.app.themes import get_theme_palette
from circuitsim.canvas.connectivity import extract_connectivity
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    load_all_iec_metadata,
    transform_terminal_position,
)
from circuitsim.canvas.symbol_renderer import SymbolLibrary

app = QApplication(sys.argv)
lib = SymbolLibrary()
catalog = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
CENTER = (200.0, 200.0)

def dot_centroid(img, rgb):
    xs, ys, n = 0.0, 0.0, 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if (abs(c.red() - rgb[0]) <= 8 and abs(c.green() - rgb[1]) <= 8
                    and abs(c.blue() - rgb[2]) <= 8):
                xs += x + 0.5
                ys += y + 0.5
                n += 1
    return (xs / n, ys / n, n) if n else None

checked = 0
for ptype, meta in catalog.items():
    for rot in (0, 90, 180, 270):
        for flip in (False, True):
            scene = CircuitScene(lib)
            item = scene.place_new_component(
                ptype, QPointF(*CENTER), rotation_deg=rot, flipped_h=flip
            )
            tag = f"{ptype} rot={rot} flip={flip}"
            # Reference: the ONE function, called directly with the metadata
            expected = {
                t.name: transform_terminal_position(
                    t.grid_pos, CENTER, rotation_deg=rot, flipped_h=flip
                )
                for t in meta.terminals
            }

            # 1. Item terminal positions
            assert item.terminal_scene_positions() == expected, tag

            # 2. Netlist: the spec handed to the extractor resolves to the same points
            spec = item.to_placed_spec()
            resolved = spec.resolve_terminals_px(catalog)
            for name, (ex, ey) in expected.items():
                assert resolved[name] == (int(round(ex)), int(round(ey))), tag
            # ... and when no terminals_px are given, the extractor's own path agrees
            from circuitsim.canvas.connectivity import PlacedComponentSpec
            bare = PlacedComponentSpec(
                component=item.component, center_px=CENTER,
                rotation_deg=rot, flipped_h=flip,
            )
            assert bare.resolve_terminals_px(catalog) == resolved, tag

            # 3. Hit area: shape() contains every terminal (local coords)
            shape = item.shape()
            for name, (ex, ey) in expected.items():
                assert shape.contains(item.mapFromScene(QPointF(ex, ey))), (tag, name)

            # 4. Snapping: find_terminal_near returns exactly that terminal
            for name, (ex, ey) in expected.items():
                hit = scene.find_terminal_near(QPointF(ex + 9.0, ey))
                assert hit is not None and hit[0] is item and hit[1] == name, (tag, name)
                assert hit[2] == (int(round(ex)), int(round(ey))), (tag, name)

            # 5. Drawing: render the real item.paint() and find the terminal dots
            pal = get_theme_palette(item.theme)
            col = pal.terminal_dot.lstrip("#")
            rgb = (int(col[0:2], 16), int(col[2:4], 16), int(col[4:6], 16))
            for name, (ex, ey) in expected.items():
                # One terminal at a time is not possible, so isolate by cropping
                # a window of +-10 px around the expected position.
                img = QImage(240, 240, QImage.Format.Format_ARGB32)
                img.fill(Qt.GlobalColor.black)
                p = QPainter(img)
                p.translate(120.0, 120.0)
                item.paint(p, QStyleOptionGraphicsItem(), None)
                p.end()
                lx, ly = ex - CENTER[0] + 120.0, ey - CENTER[1] + 120.0
                crop = img.copy(int(lx) - 10, int(ly) - 10, 20, 20)
                res = dot_centroid(crop, rgb)
                assert res is not None, (tag, name, "no drawn terminal dot found")
                cx, cy, n = res
                cx += int(lx) - 10
                cy += int(ly) - 10
                assert abs(cx - lx) <= 1.0 and abs(cy - ly) <= 1.0, (
                    tag, name, "drawn dot", (cx, cy), "expected", (lx, ly)
                )
            checked += 1

assert checked == 11 * 8, checked
print("ALL_TERMINAL_SOURCES_AGREE", checked)
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "ALL_TERMINAL_SOURCES_AGREE 88" in res.stdout


def test_0b_deliberate_drag_moves_two_cells_and_jitter_moves_nothing() -> None:
    """40 px drag = +2 grid cells (one undo command); 3 px jitter = 0 px (no command)."""
    script = """
import sys
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.resize(1100, 800)
win.show()
app.processEvents()

scene, view = win.circuit_scene, win.circuit_view
vp = view.viewport()
assert abs(view.transform().m11() - 1.0) < 1e-9
r = scene.place_new_component("resistor", QPointF(-100.0, 0.0))
app.processEvents()
start = (r.pos().x(), r.pos().y())
stack = scene.undo_stack
base_count = stack.count()

def press_move_release(delta):
    p0 = view.mapFromScene(r.pos())
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0)
    app.processEvents()
    QTest.mouseMove(vp, p0 + QPoint(*delta))
    app.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0 + QPoint(*delta))
    app.processEvents()

# 3 px jitter in several directions: 0 px movement, no undo command
for delta in [(3, 0), (-3, 0), (0, 3), (0, -3), (2, 1)]:
    press_move_release(delta)
    assert (r.pos().x(), r.pos().y()) == start, ("jitter moved the part", delta, r.pos())
    assert stack.count() == base_count, ("jitter pushed an undo command", delta)

# Deliberate 40 px drag to the right: exactly two grid cells (20 px each)
press_move_release((40, 0))
assert (r.pos().x(), r.pos().y()) == (start[0] + 40.0, start[1]), r.pos()
assert stack.count() == base_count + 1

# Deliberate 40 px drag down: two more cells
press_move_release((0, 40))
assert (r.pos().x(), r.pos().y()) == (start[0] + 40.0, start[1] + 40.0), r.pos()
assert stack.count() == base_count + 2

stack.setClean()
win.close()
print("DRAG_OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "DRAG_OK" in res.stdout
