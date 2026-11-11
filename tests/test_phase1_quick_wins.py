"""Tests for Phase 1 Quick Wins (Tasks 1 to 10)."""

from __future__ import annotations

import os
from pathlib import Path
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


def test_task1_housekeeping_gitignore() -> None:
    """Task 1a: .gitignore contains *.circ.bak and *.corrupt."""
    gitignore_path = Path(__file__).resolve().parent.parent / ".gitignore"
    assert gitignore_path.exists(), ".gitignore file must exist"
    content = gitignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines()]
    assert "*.circ.bak" in lines, "*.circ.bak must be in .gitignore"
    assert "*.corrupt" in lines, "*.corrupt must be in .gitignore"


def test_task1_switch_breakdown_hint_and_label_collisions() -> None:
    """Task 1b and 1c in a single Qt subprocess run:

    1b: Switch breakdown voltage field has contact arc hint label.
    1c: Label placement avoids overlaps (meters near neighbouring parts),
        deterministic candidate picking (below, above, right, left),
        fallback to default if no free position, and stability.
    """
    script = """
import sys
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication, QLabel

from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.components import Lightbulb, Resistor, Switch, Voltmeter
from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog

app = QApplication.instance() or QApplication([])

# -------------------------------------------------------------
# Task 1b: Switch double-click dialog breakdown voltage hint
# -------------------------------------------------------------
sw = Switch("SW1", "1", "2", v_breakdown=350.0)
dlg = QuickValueDialog(sw)
labels = dlg.findChildren(QLabel)
hint_found = False
expected_hint = (
    "Contact arc is a simplified model: a switch with more than this voltage across it can arc. "
    "Set to 0 for an ideal contact."
)
for lbl in labels:
    if expected_hint in lbl.text():
        hint_found = True
        break
assert hint_found, f"Expected arc hint not found in QuickValueDialog for switch. Labels: {[l.text() for l in labels]}"

# -------------------------------------------------------------
# Task 1c: Label collision avoidance with screenshot layout
# -------------------------------------------------------------
sym_lib = SymbolLibrary()
scene = CircuitScene(sym_lib)

# Screenshot layout:
# VM1 at (100, 100) right above R1 at (100, 160)
# VM2 at (300, 100) right above B1 at (300, 160)
vm1 = scene.place_new_component("voltmeter", QPointF(100.0, 100.0))
r1 = scene.place_new_component("resistor", QPointF(100.0, 160.0))
vm2 = scene.place_new_component("voltmeter", QPointF(300.0, 100.0))
b1 = scene.place_new_component("lightbulb", QPointF(300.0, 160.0))

vm1.live_display_value = "201.4 V"
vm2.live_display_value = "48.35 V"

# Under default positions, VM1 value collides with R1 name, and VM2 value collides with B1 name
default_vm1_val = vm1.candidate_label_rects_scene("default")[1]
default_r1_name = r1.candidate_label_rects_scene("default")[0]
assert default_vm1_val.intersects(default_r1_name), "Setup check: default VM1 and R1 must collide"

default_vm2_val = vm2.candidate_label_rects_scene("default")[1]
default_b1_name = b1.candidate_label_rects_scene("default")[0]
assert default_vm2_val.intersects(default_b1_name), "Setup check: default VM2 and B1 must collide"

# Now run collision avoidance
scene.update_label_positions()

# Verify that VM1 and VM2 resolved their collisions
items = [vm1, r1, vm2, b1]
all_label_rects = []
for it in items:
    rects = it.candidate_label_rects_scene()
    for r in rects:
        all_label_rects.append((it, r))

# 1. No two label rectangles overlap
for i in range(len(all_label_rects)):
    it_a, rect_a = all_label_rects[i]
    for j in range(i + 1, len(all_label_rects)):
        it_b, rect_b = all_label_rects[j]
        if it_a is not it_b:
            assert not rect_a.intersects(rect_b), (
                f"Collision between label of {it_a.component.name} ({rect_a}) "
                f"and {it_b.component.name} ({rect_b})"
            )

# 2. No label overlaps any component body
for it, rect in all_label_rects:
    for other in items:
        if other is not it:
            body = other.scene_body_rect()
            assert not rect.intersects(body), (
                f"Label of {it.component.name} ({rect}) overlaps body of {other.component.name} ({body})"
            )

# 3. Fallback to default when no free position exists
isolated = scene.place_new_component("resistor", QPointF(600.0, 600.0))
scene.update_label_positions()
assert isolated.label_position == "default", "Unobstructed item should pick default position"

print("TASK1_OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Qt test failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert "TASK1_OK" in res.stdout


def test_task2_recent_files(tmp_path: Path) -> None:
    """Task 2: Recent files ordering, limit of 8, duplicate to top, persistence,

    missing file removal, and UI interaction (tooltips, clear list, unsaved prompt).
    """
    from circuitsim.app.settings import AppSettings

    data_dir = tmp_path / "app_data"
    settings = AppSettings(data_dir=data_dir)

    # 1. Ordering and limit of 8
    dummy_files = [tmp_path / f"circuit_{i}.circ" for i in range(1, 11)]
    for f in dummy_files:
        f.write_text("{}", encoding="utf-8")
        settings.add_recent_file(f)

    recents = settings.get_recent_files()
    assert len(recents) == 8, f"Expected 8 recent files, got {len(recents)}"
    # Most recent first: circuit_10 should be at index 0, circuit_3 at index 7
    assert Path(recents[0]).name == "circuit_10.circ"
    assert Path(recents[7]).name == "circuit_3.circ"

    # 2. Duplicate moves to top
    settings.add_recent_file(dummy_files[4])  # circuit_5.circ
    recents = settings.get_recent_files()
    assert len(recents) == 8
    assert Path(recents[0]).name == "circuit_5.circ"

    # 3. Persistence with injected path
    settings2 = AppSettings(data_dir=data_dir)
    assert settings2.get_recent_files() == recents

    # 4. Qt Subprocess UI test
    script = f"""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from circuitsim.app.main_window import MainWindow
from circuitsim.app.settings import AppSettings

app = QApplication.instance() or QApplication([])
data_dir = Path(r"{data_dir}")
settings = AppSettings(data_dir=data_dir)
win = MainWindow(settings=settings)

# Inspect Open Recent menu
recent_menu = win.recent_menu
actions = [a for a in recent_menu.actions() if not a.isSeparator()]
assert len(actions) == 9, f"Expected 8 files + 1 Clear list, got {{len(actions)}}"

# File name is text, full path is tooltip
file_act_0 = actions[0]
assert file_act_0.text() == "circuit_5.circ"
assert Path(file_act_0.toolTip()).name == "circuit_5.circ"

# Test missing file handling
missing_path = Path(r"{tmp_path}") / "deleted_circuit.circ"
settings.add_recent_file(missing_path)
win._update_recent_files_menu()

# Mock error popup
error_shown = []
win._show_error = lambda title, msg: error_shown.append((title, msg))

# Trigger opening missing file
win._on_open_recent_file(str(missing_path))
assert len(error_shown) == 1, "Expected error popup for missing file"
assert "File Not Found" in error_shown[0][0]
assert str(missing_path) not in settings.get_recent_files(), "Missing file must be removed from settings"

# Test Clear list
clear_act = [a for a in recent_menu.actions() if a.text().lower() == "clear list"][0]
clear_act.trigger()
assert len(settings.get_recent_files()) == 0, "Clear list must empty settings"
rem_actions = [a for a in recent_menu.actions() if a.isEnabled()]
assert len(rem_actions) == 0, "No active actions should remain after clear list"

print("TASK2_OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Qt test failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert "TASK2_OK" in res.stdout

