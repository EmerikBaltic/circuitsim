"""Tests for Phase 1 Quick Wins (Tasks 1 to 10)."""

from __future__ import annotations

from pathlib import Path
import sys


def test_task1_housekeeping_gitignore() -> None:
    """Task 1a: .gitignore contains *.circ.bak and *.corrupt."""
    gitignore_path = Path(__file__).resolve().parent.parent / ".gitignore"
    assert gitignore_path.exists(), ".gitignore file must exist"
    content = gitignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines()]
    assert "*.circ.bak" in lines, "*.circ.bak must be in .gitignore"
    assert "*.corrupt" in lines, "*.corrupt must be in .gitignore"


def test_task1_switch_breakdown_hint_and_label_collisions(qapp) -> None:
    """Task 1b and 1c:

    1b: Switch breakdown voltage field has contact arc hint label.
    1c: Label placement avoids overlaps (meters near neighbouring parts),
        deterministic candidate picking (below, above, right, left),
        fallback to default if no free position, and stability.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QLabel

    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.canvas.symbol_renderer import SymbolLibrary
    from circuitsim.components import Switch
    from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog

    # Task 1b: Switch double-click dialog breakdown voltage hint
    sw = Switch("SW1", "1", "2", v_breakdown=350.0)
    dlg = QuickValueDialog(sw)
    labels = dlg.findChildren(QLabel)
    expected_hint = (
        "Contact arc is a simplified model: a switch with more than this voltage across it can arc. "
        "Set to 0 for an ideal contact."
    )
    assert any(expected_hint in lbl.text() for lbl in labels), (
        f"Expected arc hint not found in QuickValueDialog for switch. Labels: {[l.text() for l in labels]}"
    )

    # Task 1c: Label collision avoidance with screenshot layout
    sym_lib = SymbolLibrary()
    scene = CircuitScene(sym_lib)

    vm1 = scene.place_new_component("voltmeter", QPointF(100.0, 100.0))
    r1 = scene.place_new_component("resistor", QPointF(100.0, 160.0))
    vm2 = scene.place_new_component("voltmeter", QPointF(300.0, 100.0))
    b1 = scene.place_new_component("lightbulb", QPointF(300.0, 160.0))

    vm1.live_display_value = "201.4 V"
    vm2.live_display_value = "48.35 V"

    default_vm1_val = vm1.candidate_label_rects_scene("default")[1]
    default_r1_name = r1.candidate_label_rects_scene("default")[0]
    assert default_vm1_val.intersects(default_r1_name), "Setup check: default VM1 and R1 must collide"

    default_vm2_val = vm2.candidate_label_rects_scene("default")[1]
    default_b1_name = b1.candidate_label_rects_scene("default")[0]
    assert default_vm2_val.intersects(default_b1_name), "Setup check: default VM2 and B1 must collide"

    scene.update_label_positions()

    items = [vm1, r1, vm2, b1]
    all_label_rects = []
    for it in items:
        for r in it.candidate_label_rects_scene():
            all_label_rects.append((it, r))

    for i in range(len(all_label_rects)):
        it_a, rect_a = all_label_rects[i]
        for j in range(i + 1, len(all_label_rects)):
            it_b, rect_b = all_label_rects[j]
            if it_a is not it_b:
                assert not rect_a.intersects(rect_b), (
                    f"Collision between label of {it_a.component.name} ({rect_a}) "
                    f"and {it_b.component.name} ({rect_b})"
                )

    for it, rect in all_label_rects:
        for other in items:
            if other is not it:
                body = other.scene_body_rect()
                assert not rect.intersects(body), (
                    f"Label of {it.component.name} ({rect}) overlaps body of {other.component.name} ({body})"
                )

    isolated = scene.place_new_component("resistor", QPointF(600.0, 600.0))
    scene.update_label_positions()
    assert isolated.label_position == "default", "Unobstructed item should pick default position"


def test_task2_recent_files(tmp_path: Path, qapp) -> None:
    """Task 2: Recent files ordering, limit of 8, duplicate to top, persistence,

    missing file removal, and UI interaction (tooltips, clear list, unsaved prompt).
    """
    from circuitsim.app.main_window import MainWindow
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

    # 4. In-process UI test
    win = MainWindow(settings=settings2)

    recent_menu = win.recent_menu
    actions = [a for a in recent_menu.actions() if not a.isSeparator()]
    assert len(actions) == 9, f"Expected 8 files + 1 Clear list, got {len(actions)}"

    file_act_0 = actions[0]
    assert file_act_0.text() == "circuit_5.circ"
    assert Path(file_act_0.toolTip()).name == "circuit_5.circ"

    missing_path = tmp_path / "deleted_circuit.circ"
    settings2.add_recent_file(missing_path)
    win._update_recent_files_menu()

    error_shown: list[tuple[str, str]] = []
    win._show_error = lambda title, msg: error_shown.append((title, msg))

    win._on_open_recent_file(str(missing_path))
    assert len(error_shown) == 1, "Expected error popup for missing file"
    assert "File Not Found" in error_shown[0][0]
    assert str(missing_path) not in settings2.get_recent_files(), "Missing file must be removed from settings"

    clear_act = [a for a in recent_menu.actions() if a.text().lower() == "clear list"][0]
    clear_act.trigger()
    assert len(settings2.get_recent_files()) == 0, "Clear list must empty settings"
    rem_actions = [a for a in recent_menu.actions() if a.isEnabled()]
    assert len(rem_actions) == 0, "No active actions should remain after clear list"


def test_task3_example_circuits(qapp) -> None:
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

    # 6. UI Menu check
    from circuitsim.app.main_window import MainWindow

    win = MainWindow()
    ex_menu = win.examples_menu
    actions = ex_menu.actions()
    assert len(actions) == 5, f"Expected 5 example actions, got {len(actions)}"

    act0 = actions[0]
    assert "Voltage Divider" in act0.text()
    assert len(act0.toolTip()) > 5

    act0.trigger()
    assert win._current_path is None, "Example must open as a NEW untitled circuit"
    assert "Untitled" in win.windowTitle(), f"Title must be Untitled, got {win.windowTitle()}"
    assert len(win.circuit_scene.placed_items) >= 4, "Loaded example must have components on canvas"


def test_task4_zoom_to_fit_and_shortcuts(qapp) -> None:
    """Task 4: Zoom to fit (Ctrl+0), shortcuts (F5, F6, Shift+F5), no duplicate shortcuts,

    zoom to fit does not change sceneRect or move parts, and shortcuts shown in info panel.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QAction
    from circuitsim.app.main_window import MainWindow

    win = MainWindow()
    win.resize(1024, 768)
    win.show()
    qapp.processEvents()

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
    qapp.processEvents()

    scene_rect_before = scene.sceneRect()
    pos_r1_before = (r1.pos().x(), r1.pos().y())
    pos_r2_before = (r2.pos().x(), r2.pos().y())

    view.zoom_to_fit()
    qapp.processEvents()

    assert scene.sceneRect() == scene_rect_before, "zoom_to_fit must NOT modify sceneRect"
    assert (r1.pos().x(), r1.pos().y()) == pos_r1_before, "zoom_to_fit must NOT move part R1"
    assert (r2.pos().x(), r2.pos().y()) == pos_r2_before, "zoom_to_fit must NOT move part R2"
    assert view.zoom_factor != 1.0 or view.view_center() != (0.0, 0.0), "zoom_to_fit must change view viewport/zoom"


def test_task5_hover_tooltips_with_live_values(qapp) -> None:
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
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QHelpEvent

    from circuitsim.app.main_window import MainWindow
    from circuitsim.engine.simulation_session import ComponentTelemetry, SimulationFrame, SimulationState

    win = MainWindow()
    scene = win.circuit_scene
    view = win.circuit_view

    win.show()
    qapp.processEvents()

    v1 = scene.place_new_component("dc_voltage", QPointF(0.0, 100.0))
    v1.component.dc_voltage = 12.0
    r1 = scene.place_new_component("resistor", QPointF(0.0, -100.0))
    r1.component.resistance = 1000.0
    scene.place_new_component("ground", QPointF(40.0, 140.0))

    p_v1 = v1.terminal_scene_positions_px()["pos"]
    p_r1 = r1.terminal_scene_positions_px()["a"]
    n_v1 = v1.terminal_scene_positions_px()["neg"]
    n_r1 = r1.terminal_scene_positions_px()["b"]

    scene.add_wire((p_v1, p_r1))
    scene.add_wire((n_v1, n_r1))
    qapp.processEvents()

    conn = scene.extract_connectivity_result()
    net_r1_a = conn.component_nodes["R1"]["a"]
    net_r1_b = conn.component_nodes["R1"]["b"]

    scene_rect_before = scene.sceneRect()
    pos_r1_before = (r1.pos().x(), r1.pos().y())
    pos_v1_before = (v1.pos().x(), v1.pos().y())
    h_scroll_before = view.horizontalScrollBar().value()
    v_scroll_before = view.verticalScrollBar().value()
    zoom_before = view.zoom_factor

    # 1. Stopped state tooltips
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

    # 2. Running state tooltips
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

    # 3. ViewportEvent QHelpEvent dispatch
    win.show()
    qapp.processEvents()

    pos_in_view = view.mapFromScene(r1.pos())
    help_comp = QHelpEvent(QHelpEvent.Type.ToolTip, pos_in_view, view.mapToGlobal(pos_in_view))
    assert view.viewportEvent(help_comp), "CircuitView.viewportEvent should handle component tooltip"

    term_in_view = view.mapFromScene(QPointF(float(p_r1[0]), float(p_r1[1])))
    help_term = QHelpEvent(QHelpEvent.Type.ToolTip, term_in_view, view.mapToGlobal(term_in_view))
    assert view.viewportEvent(help_term), "CircuitView.viewportEvent should handle terminal tooltip"

    qapp.processEvents()

    # 4. Canvas invariance check
    assert scene.sceneRect() == scene_rect_before, "sceneRect must be strictly unchanged by tooltips"
    assert (r1.pos().x(), r1.pos().y()) == pos_r1_before, "R1 position must be strictly unchanged by tooltips"
    assert (v1.pos().x(), v1.pos().y()) == pos_v1_before, "V1 position must be strictly unchanged by tooltips"
    assert view.horizontalScrollBar().value() == h_scroll_before, "Horizontal scrollbar must be unchanged"
    assert view.verticalScrollBar().value() == v_scroll_before, "Vertical scrollbar must be unchanged"
    assert view.zoom_factor == zoom_before, "Zoom factor must be unchanged"

    scene.undo_stack.setClean()
    win._switch_modified = False


def test_task6_export_schematic(tmp_path: Path, qapp) -> None:
    """Task 6: Export schematic as PNG and SVG.

    Verifications:
        - PNG dimensions = content bounds + 2 * margin (20 px margin on each side = +40 px).
        - SVG is valid XML parsable by ElementTree, containing component names ("R1", "B1").
        - Selection outlines, hover highlights, and ghost previews are excluded from render,
          and previous canvas selection/hover state is restored after export.
        - Export options dialog switches between ThemeMode.LIGHT and current theme.
        - Empty schematic export gracefully returns None / False.
    """
    import xml.etree.ElementTree as ET
    from PySide6.QtCore import QPointF, QRectF

    from circuitsim.app.main_window import MainWindow
    from circuitsim.app.themes import ThemeMode
    from circuitsim.canvas.export import (
        ExportOptionsDialog,
        compute_schematic_bounds,
        export_schematic_to_image,
        export_schematic_to_svg,
    )

    win = MainWindow()
    scene = win.circuit_scene

    # 1. Empty circuit check
    assert compute_schematic_bounds(scene) is None
    assert export_schematic_to_image(scene) is None
    empty_svg_path = tmp_path / "empty.svg"
    assert export_schematic_to_svg(scene, str(empty_svg_path)) is False

    # 2. Place components and wire
    r1 = scene.place_new_component("resistor", QPointF(-100.0, 0.0))
    b1 = scene.place_new_component("lightbulb", QPointF(100.0, 0.0))

    r1_term_b = r1.terminal_scene_positions_px()["b"]
    b1_term_a = b1.terminal_scene_positions_px()["a"]
    scene.add_wire((r1_term_b, b1_term_a))

    content_rect = QRectF()
    for it in scene.placed_items:
        content_rect = content_rect.united(it.sceneBoundingRect())
    for w in scene.placed_wires:
        content_rect = content_rect.united(w.sceneBoundingRect())

    margin = 20.0
    expected_w = int(round(content_rect.width() + 2 * margin))
    expected_h = int(round(content_rect.height() + 2 * margin))

    r1.setSelected(True)
    assert r1.isSelected()
    scene.update_hover_highlight(QPointF(float(r1_term_b[0]), float(r1_term_b[1])))
    assert scene._hovered_terminal_pt is not None
    scene.show_ghost_preview("voltmeter", QPointF(0.0, 50.0))
    assert scene._ghost_item is not None

    # 3. Export to PNG
    img_white = export_schematic_to_image(scene, margin_px=margin, theme_mode=ThemeMode.LIGHT)
    assert img_white is not None
    assert img_white.width() == expected_w, f"Expected PNG width {expected_w}, got {img_white.width()}"
    assert img_white.height() == expected_h, f"Expected PNG height {expected_h}, got {img_white.height()}"

    assert r1.isSelected(), "Selection must be restored after export"
    assert scene._hovered_terminal_pt is not None, "Hover highlight must be restored after export"
    assert scene._ghost_item is not None and scene._ghost_item.isVisible(), "Ghost item visibility must be restored"

    # 4. Export to SVG
    svg_path = tmp_path / "export.svg"
    ok = export_schematic_to_svg(scene, str(svg_path), margin_px=margin, theme_mode=ThemeMode.LIGHT)
    assert ok is True

    svg_text = svg_path.read_text(encoding="utf-8")
    tree = ET.fromstring(svg_text)
    assert tree.tag.endswith("svg"), f"Root tag must be SVG, got {tree.tag}"
    assert "R1" in svg_text, "SVG must contain component label 'R1'"
    assert "B1" in svg_text, "SVG must contain component label 'B1'"

    # 5. Export options dialog
    dlg = ExportOptionsDialog(ThemeMode.DARK)
    assert dlg.selected_theme_mode() == ThemeMode.LIGHT
    dlg.radio_current.setChecked(True)
    assert dlg.selected_theme_mode() == ThemeMode.DARK
    dlg.radio_white.setChecked(True)
    assert dlg.selected_theme_mode() == ThemeMode.LIGHT

    # 6. Verify menu actions exist in MainWindow
    assert win.act_export_png is not None
    assert win.act_export_svg is not None
    assert "PNG" in win.act_export_png.text()
    assert "SVG" in win.act_export_svg.text()

    scene.undo_stack.setClean()
    win._switch_modified = False


def test_task7_about_feedback_and_crash_log(tmp_path: Path, qapp) -> None:
    """Task 7: About dialog, feedback link, and global crash logging.

    Verifications:
        - Version dynamically retrieved from package metadata (0.1.0).
        - Repo URL constant and issue tracker URL constants match project specification.
        - Crash log exception hook formats traceback, Python version, PySide6 version,
          OS platform, and writes to crash.log in data_dir without raising.
        - Help menu contains 'Report a problem / suggest a feature' and 'About CircuitSim'.
    """
    from circuitsim.app.crash_handler import (
        ISSUES_URL,
        REPO_URL,
        get_app_version,
        install_global_exception_hook,
        write_crash_log,
    )
    from circuitsim.app.main_window import MainWindow

    version = get_app_version()
    assert version == "0.1.0", f"Expected version '0.1.0', got '{version}'"
    assert REPO_URL == "https://github.com/EmerikBaltic/circuitsim"
    assert ISSUES_URL == "https://github.com/EmerikBaltic/circuitsim/issues"

    # 2. Crash log writing
    log_dir1 = tmp_path / "log1"
    log_dir1.mkdir()
    try:
        raise ValueError("Simulated unexpected test error in circuit simulation")
    except ValueError as exc:
        log_path = write_crash_log(type(exc), exc, exc.__traceback__, log_dir=log_dir1)

    assert log_path.exists(), "crash.log must be written"
    content = log_path.read_text(encoding="utf-8")
    assert "CircuitSim Crash Report:" in content
    assert "Version:        0.1.0" in content
    assert "Python:" in content
    assert "PySide6:" in content
    assert "Platform:" in content
    assert "Simulated unexpected test error" in content
    assert "ValueError" in content
    assert REPO_URL in content
    assert ISSUES_URL in content

    # 3. Global exception hook installation & safety
    log_dir2 = tmp_path / "log2"
    log_dir2.mkdir()
    prev_hook = sys.excepthook
    try:
        install_global_exception_hook(log_dir=log_dir2)
        try:
            raise RuntimeError("Hook verification exception")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)

        hook_log = log_dir2 / "crash.log"
        assert hook_log.exists(), "crash.log must exist after sys.excepthook invocation"
        hook_content = hook_log.read_text(encoding="utf-8")
        assert "Hook verification exception" in hook_content
    finally:
        sys.excepthook = prev_hook

    # 4. MainWindow Help menu actions
    win = MainWindow()
    assert win.act_report_issue is not None
    assert "Report a problem" in win.act_report_issue.text()
    assert win.act_about is not None
    assert "About CircuitSim" in win.act_about.text()

    scene = win.circuit_scene
    scene.undo_stack.setClean()
    win._switch_modified = False


def test_task8_bulb_burnout_option(qapp) -> None:
    """Task 8: Lightbulb filament burn-out option."""
    from PySide6.QtWidgets import QLabel

    from circuitsim.components import DCVoltageSource, Ground, Lightbulb
    from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog
    from circuitsim.engine import Circuit
    from circuitsim.engine.simulation_session import SimulationSession

    # 1. Dialog checks: off by default, hint present, values apply
    b_test = Lightbulb("B_dlg", "1", "0", rated_power=60.0, rated_voltage=120.0)
    dlg = QuickValueDialog(b_test)
    assert dlg.bulb_burnout_cb is not None
    assert dlg.bulb_burnout_cb.isChecked() is False, "burnout_enabled must be off by default"
    assert dlg.burnout_ratio_edit is not None
    assert dlg.burnout_time_edit is not None

    labels = dlg.findChildren(QLabel)
    assert any("burn-out" in lbl.text().lower() or "filament" in lbl.text().lower() for lbl in labels)

    dlg.bulb_burnout_cb.setChecked(True)
    dlg.burnout_ratio_edit.setText("1.2")
    dlg.burnout_time_edit.setText("0.5s")
    assert dlg._apply_current_inputs()
    assert b_test.burnout_enabled is True
    assert b_test.burnout_power_ratio == 1.2
    assert b_test.burnout_time == 0.5

    # 2. Hand-calculated 180 V overload with burnout enabled
    c_overload = Circuit()
    c_overload.add(DCVoltageSource("V1", "1", "0", voltage=180.0))
    bulb_overload = Lightbulb(
        "B1", "1", "0",
        rated_power=60.0,
        rated_voltage=120.0,
        burnout_enabled=True,
        burnout_power_ratio=1.2,
        burnout_time=0.5,
    )
    c_overload.add(bulb_overload)
    c_overload.add(Ground("GND", "0"))

    sess = SimulationSession(c_overload, default_dt=0.05)
    sess.start()

    for _ in range(8):
        frame = sess.step_chunk(steps=1, dt=0.05)
    assert bulb_overload.burned_out is False
    assert abs(bulb_overload.current - 0.75) < 1e-3

    for _ in range(4):
        frame = sess.step_chunk(steps=1, dt=0.05)

    assert bulb_overload.burned_out is True
    assert abs(bulb_overload.current) < 1e-6, f"Current must drop to ~0 A, got {bulb_overload.current}"

    burn_diags = [d for d in frame.diagnostics if d.code == "bulb_burned_out"]
    assert len(burn_diags) == 1
    assert burn_diags[0].severity == "warning"
    assert burn_diags[0].message == "B1 burned out"

    sess.stop()
    assert bulb_overload.burned_out is False

    # 3. Hand-calculated check at rated 120 V
    c_rated = Circuit()
    c_rated.add(DCVoltageSource("V1", "1", "0", voltage=120.0))
    bulb_rated = Lightbulb(
        "B2", "1", "0",
        rated_power=60.0,
        rated_voltage=120.0,
        burnout_enabled=True,
        burnout_power_ratio=1.2,
        burnout_time=0.5,
    )
    c_rated.add(bulb_rated)
    c_rated.add(Ground("GND", "0"))
    sess_rated = SimulationSession(c_rated, default_dt=0.05)
    sess_rated.start()
    for _ in range(20):
        sess_rated.step_chunk(steps=1, dt=0.05)
    assert bulb_rated.burned_out is False
    assert abs(bulb_rated.current - 0.5) < 1e-3

    # 4. Hand-calculated check at 180 V with burnout disabled
    c_dis = Circuit()
    c_dis.add(DCVoltageSource("V1", "1", "0", voltage=180.0))
    bulb_dis = Lightbulb(
        "B3", "1", "0",
        rated_power=60.0,
        rated_voltage=120.0,
        burnout_enabled=False,
        burnout_power_ratio=1.2,
        burnout_time=0.5,
    )
    c_dis.add(bulb_dis)
    c_dis.add(Ground("GND", "0"))
    sess_dis = SimulationSession(c_dis, default_dt=0.05)
    sess_dis.start()
    for _ in range(20):
        sess_dis.step_chunk(steps=1, dt=0.05)
    assert bulb_dis.burned_out is False
    assert abs(bulb_dis.current - 0.75) < 1e-3


def test_task9_number_format_setting(tmp_path: Path, qapp) -> None:
    """Task 9: Number format preferences (Auto / Dot / Comma)."""
    from circuitsim.app.main_window import MainWindow
    from circuitsim.app.settings import AppSettings
    from circuitsim.dialogs.preferences_dialog import PreferencesDialog
    from circuitsim.dialogs.value_parser import (
        format_engineering_value,
        get_global_number_format,
        parse_engineering_value,
        set_global_number_format,
    )

    prev_fmt = get_global_number_format()
    try:
        # 1. Format test: Dot mode
        set_global_number_format("dot")
        assert format_engineering_value(4700.0, "Ω") == "4.7 kΩ"
        assert format_engineering_value(0.0047, "Ω") == "4.7 mΩ"
        assert format_engineering_value(5.65e9, "Hz") == "5.65 GHz"
        assert format_engineering_value(-12.5, "V") == "-12.5 V"

        # 2. Format test: Comma mode
        set_global_number_format("comma")
        assert format_engineering_value(4700.0, "Ω") == "4,7 kΩ"
        assert format_engineering_value(0.0047, "Ω") == "4,7 mΩ"
        assert format_engineering_value(5.65e9, "Hz") == "5,65 GHz"
        assert format_engineering_value(-12.5, "V") == "-12,5 V"

        # 3. Round-trip input parser verification
        test_cases = [
            (4700.0, "Ω"),
            (0.0047, "Ω"),
            (5.65e9, "Hz"),
            (-12.5, "V"),
        ]
        for val, unit in test_cases:
            dot_str = format_engineering_value(val, unit, decimal_separator=".")
            comma_str = format_engineering_value(val, unit, decimal_separator=",")
            assert parse_engineering_value(dot_str) == val, f"Failed parsing dot string {dot_str}"
            assert parse_engineering_value(comma_str) == val, f"Failed parsing comma string {comma_str}"

        # 4. Preferences dialog and atomic persistence
        s = AppSettings(tmp_path)
        dlg = PreferencesDialog(s)
        assert dlg.combo_number_format.count() >= 3

        idx_comma = dlg.combo_number_format.findData("comma")
        dlg.combo_number_format.setCurrentIndex(idx_comma)
        dlg._on_accept()
        assert s.get_number_format() == "comma"
        assert get_global_number_format() == "comma"

        s_reloaded = AppSettings(tmp_path)
        assert s_reloaded.get_number_format() == "comma"

        # 5. Verify MainWindow action
        win = MainWindow()
        assert win.act_preferences is not None
        assert "Preferences" in win.act_preferences.text()

        scene = win.circuit_scene
        scene.undo_stack.setClean()
        win._switch_modified = False
    finally:
        set_global_number_format(prev_fmt)


def test_task10_continuous_integration() -> None:
    """Task 10: GitHub Actions CI workflow and README status badge.

    Verifications:
        - .github/workflows/ci.yml exists with Windows runner, Python 3.12,
          QT_QPA_PLATFORM=offscreen environment variable, and pytest invocation.
        - README.md contains the GitHub Actions workflow status badge link.
    """
    repo_root = Path(__file__).resolve().parent.parent
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    assert ci_file.exists(), ".github/workflows/ci.yml must exist"

    ci_content = ci_file.read_text(encoding="utf-8")
    assert "windows-latest" in ci_content, "CI must run on windows-latest"
    assert "3.12" in ci_content, "CI must use Python 3.12"
    assert "QT_QPA_PLATFORM" in ci_content, "CI must set QT_QPA_PLATFORM=offscreen"
    assert "offscreen" in ci_content
    assert "pytest" in ci_content, "CI must invoke pytest"
    assert "push" in ci_content
    assert "pull_request" in ci_content

    readme_file = repo_root / "README.md"
    assert readme_file.exists()
    readme_content = readme_file.read_text(encoding="utf-8")
    assert "badge.svg" in readme_content, "README.md must contain CI status badge"
    assert "workflows/ci.yml" in readme_content







