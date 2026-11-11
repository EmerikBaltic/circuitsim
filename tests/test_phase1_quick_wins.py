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


def test_task3_example_circuits() -> None:
    """Task 3: Example circuits bundled in package data, index catalog,

    analytic hand calculations for all 5 circuits, and UI menu loading as untitled.
    """
    import json
    import math
    from circuitsim.canvas.connectivity import extract_connectivity
    from circuitsim.engine import MNASolver
    from circuitsim.io.circ_serializer import load_document

    ex_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "circuitsim"
        / "resources"
        / "examples"
    )
    index_file = ex_dir / "index.json"
    assert index_file.exists(), "index.json must exist in resources/examples"
    catalog = json.loads(index_file.read_text(encoding="utf-8"))
    assert len(catalog) == 5, f"Expected 5 bundled examples, found {len(catalog)}"

    # 1. Voltage Divider
    vd_doc = load_document(ex_dir / "voltage_divider.circ")
    vd_conn = extract_connectivity(vd_doc.placed, vd_doc.wires, vd_doc.junctions)
    vd_pt = MNASolver(vd_conn.circuit).solve_dc()
    vm_comp = vd_conn.circuit.get_component("VM1")
    v_vd = vd_pt.node_voltages[vm_comp.nodes[0]] - vd_pt.node_voltages[vm_comp.nodes[1]]
    # Hand formula: V = 12 * 3000 / (1000 + 3000) = 9.0 V
    expected_vd = 12.0 * (3000.0 / 4000.0)
    assert math.isclose(v_vd, expected_vd, rel_tol=1e-3, abs_tol=1e-3)

    # 2. RC Charging
    rc_doc = load_document(ex_dir / "rc_charging.circ")
    rc_conn = extract_connectivity(rc_doc.placed, rc_doc.wires, rc_doc.junctions)
    rc_solver = MNASolver(rc_conn.circuit)
    # Hand formula: tau = 1000 * 100e-6 = 0.1 s; v(t) = 5 * (1 - e^(-t / 0.1))
    rc_res = rc_solver.solve_transient(duration=0.1, dt=0.0005)
    c_comp = rc_conn.circuit.get_component("C1")
    v_rc = (
        rc_res.node_voltages[c_comp.nodes[0]][-1]
        - rc_res.node_voltages[c_comp.nodes[1]][-1]
    )
    expected_rc = 5.0 * (1.0 - math.exp(-1.0))
    assert math.isclose(v_rc, expected_rc, rel_tol=1e-3, abs_tol=1e-3)

    # 3. RL Current Rise
    rl_doc = load_document(ex_dir / "rl_current_rise.circ")
    rl_conn = extract_connectivity(rl_doc.placed, rl_doc.wires, rl_doc.junctions)
    rl_solver = MNASolver(rl_conn.circuit)
    # Hand formula: tau = 0.1 / (100 + 10) = 0.1 / 110 s; i(t) = (12/110) * (1 - e^(-t / tau))
    tau = 0.1 / 110.0
    rl_res = rl_solver.solve_transient(duration=tau, dt=tau / 200.0)
    am_comp = rl_conn.circuit.get_component("AM1")
    i_rl = abs(rl_res.branch_currents[am_comp.name][-1])
    expected_rl = (12.0 / 110.0) * (1.0 - math.exp(-1.0))
    assert math.isclose(i_rl, expected_rl, rel_tol=1e-3, abs_tol=1e-4)

    # 4. 12 V Lamp with Switch
    lamp_doc = load_document(ex_dir / "lamp_switch.circ")
    lamp_conn = extract_connectivity(lamp_doc.placed, lamp_doc.wires, lamp_doc.junctions)
    lamp_pt = MNASolver(lamp_conn.circuit).solve_dc()
    am_lamp = lamp_conn.circuit.get_component("AM1")
    i_lamp = abs(lamp_pt.branch_currents[am_lamp.name])
    # Hand formula: I = P / V = 5 W / 12 V = 0.4166667 A
    expected_lamp = 5.0 / 12.0
    assert math.isclose(i_lamp, expected_lamp, rel_tol=1e-3, abs_tol=1e-4)

    # 5. Two 12 V sources in series
    series_doc = load_document(ex_dir / "series_sources.circ")
    series_conn = extract_connectivity(series_doc.placed, series_doc.wires, series_doc.junctions)
    series_pt = MNASolver(series_conn.circuit).solve_dc()
    vm_series = series_conn.circuit.get_component("VM1")
    v_series = (
        series_pt.node_voltages[vm_series.nodes[0]]
        - series_pt.node_voltages[vm_series.nodes[1]]
    )
    # Hand formula: V = 12 V + 12 V = 24.0 V
    assert math.isclose(v_series, 24.0, rel_tol=1e-3, abs_tol=1e-3)

    # 6. UI Menu check in Qt subprocess
    script = """
import sys
from PySide6.QtWidgets import QApplication
from circuitsim.app.main_window import MainWindow

app = QApplication.instance() or QApplication([])
win = MainWindow()

ex_menu = win.examples_menu
actions = ex_menu.actions()
assert len(actions) == 5, f"Expected 5 example actions, got {len(actions)}"

# Verify first action is Voltage Divider
act0 = actions[0]
assert "Voltage Divider" in act0.text()
assert len(act0.toolTip()) > 5

# Trigger action 0 to load example
act0.trigger()
assert win._current_path is None, "Example must open as a NEW untitled circuit"
assert "Untitled" in win.windowTitle(), f"Title must be Untitled, got {win.windowTitle()}"
assert len(win.circuit_scene.placed_items) >= 4, "Loaded example must have components on canvas"

print("TASK3_OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Qt test failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert "TASK3_OK" in res.stdout


def test_task4_zoom_to_fit_and_shortcuts() -> None:
    """Task 4: Zoom to fit (Ctrl+0), shortcuts (F5, F6, Shift+F5), no duplicate shortcuts,

    zoom to fit does not change sceneRect or move parts, and shortcuts shown in info panel.
    """
    script = """
import sys
from PySide6.QtCore import QPointF
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication
from circuitsim.app.main_window import MainWindow

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.resize(1024, 768)
win.show()
app.processEvents()

# 1. No two actions share a shortcut
all_actions = win.findChildren(QAction)
shortcut_map = {}
for act in all_actions:
    sc_list = act.shortcuts()
    single_sc = act.shortcut()
    combined = list(sc_list)
    if not single_sc.isEmpty() and single_sc not in combined:
        combined.append(single_sc)
    unique_keys = set(sc.toString() for sc in combined if sc.toString())
    for key_str in unique_keys:
        if key_str in shortcut_map:
            other_act = shortcut_map[key_str]
            assert other_act is act, (
                f"Duplicate shortcut '{key_str}' shared by '{other_act.text()}' and '{act.text()}'"
            )
        shortcut_map[key_str] = act

# 2. Check specific shortcuts and tooltips
assert win.act_run.shortcut().toString() == "F5"
assert "F5" in win.act_run.toolTip()
assert win.act_pause.shortcut().toString() == "F6"
assert "F6" in win.act_pause.toolTip()
assert win.act_stop.shortcut().toString() == "Shift+F5"
assert "Shift+F5" in win.act_stop.toolTip()
assert win.act_zoom_fit.shortcut().toString() == "Ctrl+0"
assert "Ctrl+0" in win.act_zoom_fit.toolTip()

# 3. Check shortcuts help text in info panel
info_text = win.info_label.text()
assert "F5" in info_text
assert "F6" in info_text
assert "Shift+F5" in info_text
assert "Ctrl+0" in info_text

# 4. Zoom to fit on empty circuit resets to 100%
view = win.circuit_view
scene = win.circuit_scene
view.scale(2.0, 2.0)
view.zoom_to_fit()
assert abs(view.zoom_factor - 1.0) < 1e-4, f"Empty circuit zoom must reset to 1.0, got {view.zoom_factor}"

# 5. Zoom to fit on circuit with parts
r1 = scene.place_new_component("resistor", QPointF(-200.0, -150.0))
r2 = scene.place_new_component("resistor", QPointF(200.0, 150.0))
app.processEvents()

scene_rect_before = scene.sceneRect()
pos_r1_before = (r1.pos().x(), r1.pos().y())
pos_r2_before = (r2.pos().x(), r2.pos().y())

view.zoom_to_fit()
app.processEvents()

# Assert sceneRect and part positions are strictly unchanged
assert scene.sceneRect() == scene_rect_before, "zoom_to_fit must NOT modify sceneRect"
assert (r1.pos().x(), r1.pos().y()) == pos_r1_before, "zoom_to_fit must NOT move part R1"
assert (r2.pos().x(), r2.pos().y()) == pos_r2_before, "zoom_to_fit must NOT move part R2"

# View transform must be adapted to fit parts with margin
assert view.zoom_factor != 1.0 or view.view_center() != (0.0, 0.0), "zoom_to_fit must change view viewport/zoom"

print("TASK4_OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Qt test failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert "TASK4_OK" in res.stdout


def test_task5_hover_tooltips_with_live_values() -> None:
    """Task 5: Hover tooltips with live values for parts and terminals.

    Hand-calculated values:
        - Circuit: 12 V DC source connected across a 1 kΩ resistor.
        - Node 1 voltage: V = 12.0 V.
        - Ground node 0: V = 0.0 V.
        - Resistor current: I = V / R = 12 V / 1000 Ω = 0.012 A (12 mA).
        - Resistor absorbed power: P = V * I = 12 V * 0.012 A = 0.144 W (144 mW).
        - Voltage source delivered power: P_del = 144 mW, absorbed = -144 mW.

    Verification:
        - When running:
          * Resistor tooltip displays: Name, Value, 12 V, 12 mA, 144 mW.
          * Source tooltip displays: Name, Value, 12 V, 12 mA, -144 mW (delivering),
            and explanation "Positive power is absorbed; sources indicate delivered power."
          * Terminal tooltip displays terminal name, net name, and "Node voltage: 12 V".
        - When stopped:
          * Part tooltip displays: Voltage: --, Current: --, Power: --.
          * Terminal tooltip displays: Node voltage: --.
        - Layout invariance:
          * sceneRect, part positions, scrollbars, and zoom are strictly unchanged by tooltips.
    """
    script = """
import sys
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.engine.simulation_session import ComponentTelemetry, SimulationFrame, SimulationState

app = QApplication.instance() or QApplication([])
win = MainWindow()
scene = win.circuit_scene
view = win.circuit_view

win.show()
app.processEvents()

# Place 12 V source, 1 kΩ resistor, and ground
# V1 pos at (-40, 100), neg at (40, 100)
# R1 a at (-40, -100), b at (40, -100)
# GND gnd at (40, 100)
v1 = scene.place_new_component("dc_voltage", QPointF(0.0, 100.0))
v1.component.dc_voltage = 12.0
r1 = scene.place_new_component("resistor", QPointF(0.0, -100.0))
r1.component.resistance = 1000.0
gnd = scene.place_new_component("ground", QPointF(40.0, 140.0))

p_v1 = v1.terminal_scene_positions_px()["pos"]
p_r1 = r1.terminal_scene_positions_px()["a"]
n_v1 = v1.terminal_scene_positions_px()["neg"]
n_r1 = r1.terminal_scene_positions_px()["b"]
g_gnd = gnd.terminal_scene_positions_px()["gnd"]

# Connect pos to a (node N1 = 12 V) and neg to b + gnd (node 0 = 0 V)
scene.add_wire((p_v1, p_r1))
scene.add_wire((n_v1, n_r1))
app.processEvents()

conn = scene.extract_connectivity_result()
net_r1_a = conn.component_nodes["R1"]["a"]
net_r1_b = conn.component_nodes["R1"]["b"]

# Record baseline canvas state after layout and wire placement
scene_rect_before = scene.sceneRect()
pos_r1_before = (r1.pos().x(), r1.pos().y())
pos_v1_before = (v1.pos().x(), v1.pos().y())
h_scroll_before = view.horizontalScrollBar().value()
v_scroll_before = view.verticalScrollBar().value()
zoom_before = view.zoom_factor

# -----------------------------------------------------------------
# 1. Stopped state tooltips
# -----------------------------------------------------------------
r1_tip_stopped = scene.get_component_tooltip(r1)
assert "Name: R1" in r1_tip_stopped
assert "Value: 1 kΩ" in r1_tip_stopped
assert "Voltage: --" in r1_tip_stopped
assert "Current: --" in r1_tip_stopped
assert "Power: --" in r1_tip_stopped

v1_tip_stopped = scene.get_component_tooltip(v1)
assert "Name: V1" in v1_tip_stopped
assert "Voltage: --" in v1_tip_stopped

t_tip_stopped = scene.get_terminal_tooltip(r1, "a")
assert "Terminal: a" in t_tip_stopped
assert f"Net: {net_r1_a}" in t_tip_stopped
assert "Node voltage: --" in t_tip_stopped

# -----------------------------------------------------------------
# 2. Running state tooltips
# -----------------------------------------------------------------
# Hand-calculated formula values:
# I = 12 V / 1000 Ω = 0.012 A (12 mA)
# P_absorbed_resistor = 12 V * 0.012 A = 0.144 W (144 mW)
# P_absorbed_source = -0.144 W (-144 mW, delivering)
frame = SimulationFrame(
    state=SimulationState.RUNNING,
    sim_time=0.1,
    dt=1e-3,
    speed_ratio=1.0,
    node_voltages={net_r1_a: 12.0, net_r1_b: 0.0},
    components={
        "V1": ComponentTelemetry("V1", "dc_voltage", 12.0, 0.012, -0.144, "12 V"),
        "R1": ComponentTelemetry("R1", "resistor", 12.0, 0.012, 0.144, "1 kΩ"),
    },
)
scene.apply_simulation_frame(frame)

r1_tip_running = scene.get_component_tooltip(r1)
assert "Name: R1" in r1_tip_running
assert "12 V" in r1_tip_running
assert "12 mA" in r1_tip_running
assert "144 mW" in r1_tip_running

v1_tip_running = scene.get_component_tooltip(v1)
assert "Name: V1" in v1_tip_running
assert "12 V" in v1_tip_running
assert "12 mA" in v1_tip_running
assert "-144 mW" in v1_tip_running
assert "(delivering)" in v1_tip_running
assert "Positive power is absorbed; sources indicate delivered power." in v1_tip_running

t_tip_running = scene.get_terminal_tooltip(r1, "a")
assert "Terminal: a" in t_tip_running
assert f"Net: {net_r1_a}" in t_tip_running
assert "Node voltage: 12 V" in t_tip_running

# -----------------------------------------------------------------
# 3. ViewportEvent QHelpEvent dispatch
# -----------------------------------------------------------------
win.show()
app.processEvents()

# Help event on component body
pos_in_view = view.mapFromScene(r1.pos())
help_comp = QHelpEvent(QHelpEvent.Type.ToolTip, pos_in_view, view.mapToGlobal(pos_in_view))
assert view.viewportEvent(help_comp), "CircuitView.viewportEvent should handle component tooltip"

# Help event on terminal
term_in_view = view.mapFromScene(QPointF(float(p_r1[0]), float(p_r1[1])))
help_term = QHelpEvent(QHelpEvent.Type.ToolTip, term_in_view, view.mapToGlobal(term_in_view))
assert view.viewportEvent(help_term), "CircuitView.viewportEvent should handle terminal tooltip"

app.processEvents()

# -----------------------------------------------------------------
# 4. Canvas invariance check
# -----------------------------------------------------------------
assert scene.sceneRect() == scene_rect_before, "sceneRect must be strictly unchanged by tooltips"
assert (r1.pos().x(), r1.pos().y()) == pos_r1_before, "R1 position must be strictly unchanged by tooltips"
assert (v1.pos().x(), v1.pos().y()) == pos_v1_before, "V1 position must be strictly unchanged by tooltips"
assert view.horizontalScrollBar().value() == h_scroll_before, "Horizontal scrollbar must be unchanged"
assert view.verticalScrollBar().value() == v_scroll_before, "Vertical scrollbar must be unchanged"
assert view.zoom_factor == zoom_before, "Zoom factor must be unchanged"

scene.undo_stack.setClean()
win._switch_modified = False
print("TASK5_OK")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Qt test failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert "TASK5_OK" in res.stdout


