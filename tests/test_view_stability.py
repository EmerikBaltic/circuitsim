"""Tests ensuring canvas view and dock stability during component selection and mouse clicks."""

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


def test_clicking_and_selecting_parts_does_not_shift_view_or_move_part() -> None:
    """Item 2: Viewport, scrollbars, dock size, sceneRect, and part view positions

    must not change when selecting different parts, deselecting, or selecting
    multiple parts. A mouse press and release at the same point (or within drag threshold)
    must move the part by 0 px.
    """
    script = """
import sys
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.resize(1024, 768)
win.show()
app.processEvents()

scene = win.circuit_scene
view = win.circuit_view
vp = view.viewport()

# Place several different parts
r = scene.place_new_component("resistor", QPointF(-100.0, 0.0))
c = scene.place_new_component("capacitor", QPointF(100.0, 0.0))
b = scene.place_new_component("lightbulb", QPointF(0.0, 100.0))
app.processEvents()

# Steps: select R, select C, select B, deselect, select R+C, deselect
steps = [
    ("Select R", [r]),
    ("Select C", [c]),
    ("Select B", [b]),
    ("Deselect", []),
    ("Select R+C", [r, c]),
    ("Deselect again", []),
]

snapshots = []
for label, items in steps:
    scene.clearSelection()
    for it in items:
        it.setSelected(True)
    app.processEvents()

    snapshot = {
        "label": label,
        "dock_w": win.info_dock.width(),
        "dock_h": win.info_dock.height(),
        "palette_w": win.palette_dock.width(),
        "palette_h": win.palette_dock.height(),
        "sb_height": win.statusBar().height(),
        "vp_w": vp.width(),
        "vp_h": vp.height(),
        "scroll_h": view.horizontalScrollBar().value(),
        "scroll_v": view.verticalScrollBar().value(),
        "scene_rect": (
            scene.sceneRect().x(),
            scene.sceneRect().y(),
            scene.sceneRect().width(),
            scene.sceneRect().height(),
        ),
        "r_vpos": (view.mapFromScene(r.pos()).x(), view.mapFromScene(r.pos()).y()),
        "c_vpos": (view.mapFromScene(c.pos()).x(), view.mapFromScene(c.pos()).y()),
        "b_vpos": (view.mapFromScene(b.pos()).x(), view.mapFromScene(b.pos()).y()),
    }
    snapshots.append(snapshot)

# Assert that NONE of these changed across any selection change
baseline = snapshots[0]
for snap in snapshots[1:]:
    for key, val in baseline.items():
        if key == "label":
            continue
        assert snap[key] == val, (
            f"Layout shifted during '{snap['label']}': {key} changed from {val} to {snap[key]}"
        )

# Assert that a mouse press and release at the same point on a part moves it by 0 px
r_vpos = view.mapFromScene(r.pos())
r_orig_scene_pos = (r.pos().x(), r.pos().y())

QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r_vpos)
app.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r_vpos)
app.processEvents()

assert (r.pos().x(), r.pos().y()) == r_orig_scene_pos, (
    f"Part moved on click: {r_orig_scene_pos} -> {(r.pos().x(), r.pos().y())}"
)

# Also assert small mouse jitter (< 4 px drag threshold) does not move part
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r_vpos)
app.processEvents()
QTest.mouseMove(vp, r_vpos + QPoint(2, 1))
app.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r_vpos + QPoint(2, 1))
app.processEvents()

assert (r.pos().x(), r.pos().y()) == r_orig_scene_pos, (
    f"Part moved on jitter within drag threshold: {r_orig_scene_pos} -> {(r.pos().x(), r.pos().y())}"
)

# And assert genuine drag (> threshold) does move part
r_target_vpos = r_vpos + QPoint(40, 40)
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r_vpos)
app.processEvents()
QTest.mouseMove(vp, r_target_vpos)
app.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r_target_vpos)
app.processEvents()

assert (r.pos().x(), r.pos().y()) != r_orig_scene_pos, (
    "Part failed to move when dragged beyond threshold"
)

# Clean up cleanly without unsaved changes dialog
scene.undo_stack.setClean()
win.close()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Qt subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
