"""Step 2C tests: Pure-Python SimulationSession, live meters, switch toggle, live value editing,
lightbulb brightness/overload, isolated junction dot handling, problem diagnostics, upright
rotated/flipped labels, toolbar speed dropdown visibility, and non-freezing background QThread worker.

Note: In compliance with `test_no_qt_imports_in_engine_or_components`, this test module
does NOT import `PySide6` in the main pytest process. All Qt widget/scene/thread checks run
inside an isolated Python subprocess.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    WireSpec,
    extract_connectivity,
)
from circuitsim.components import (
    Ammeter,
    DCVoltageSource,
    Ground,
    Inductor,
    Lightbulb,
    Resistor,
    Switch,
    Voltmeter,
)
from circuitsim.engine import (
    Circuit,
    SimulationSession,
    SimulationState,
    compute_transport_controls_state,
)


def test_simulation_session_has_zero_qt_imports() -> None:
    """Verify `circuitsim.engine.simulation_session` imports zero PySide6 modules."""
    qt_mods = [m for m in sys.modules if m.startswith("PySide6")]
    assert qt_mods == []


def test_transport_controls_state_mapping_and_transitions() -> None:
    """Item 3: Pure-Python mapping from SimulationState to Run/Pause/Stop button states."""
    # 1. STOPPED: Run enabled; Pause and Stop greyed out; indicator '■ Stopped'
    s_stopped = compute_transport_controls_state(SimulationState.STOPPED)
    assert s_stopped.run_enabled is True
    assert s_stopped.pause_enabled is False
    assert s_stopped.stop_enabled is False
    assert s_stopped.run_visual_role == "normal"
    assert s_stopped.status_indicator_text == "■ Stopped"
    assert "F5" in s_stopped.run_tooltip
    assert "F6" in s_stopped.pause_tooltip
    assert "F7" in s_stopped.stop_tooltip

    # 2. RUNNING: Run shown as active (green); Pause and Stop enabled; indicator '● Running'
    s_running = compute_transport_controls_state(SimulationState.RUNNING)
    assert s_running.run_enabled is True
    assert s_running.pause_enabled is True
    assert s_running.stop_enabled is True
    assert s_running.run_visual_role == "active_green"
    assert s_running.pause_visual_role == "normal"
    assert s_running.status_indicator_text == "● Running"

    # 3. PAUSED: Pause shown as active (amber); Run enabled and labelled 'Resume'; Stop enabled; indicator '❚❚ Paused'
    s_paused = compute_transport_controls_state(SimulationState.PAUSED)
    assert s_paused.run_enabled is True
    assert "Resume" in s_paused.run_label
    assert "Resume" in s_paused.run_icon_text
    assert s_paused.pause_enabled is True
    assert s_paused.pause_visual_role == "active_amber"
    assert s_paused.stop_enabled is True
    assert s_paused.status_indicator_text == "❚❚ Paused"

    # 4. ERROR: Run shows red outline; Pause and Stop disabled; indicator '■ Stopped'
    s_error = compute_transport_controls_state(
        SimulationState.ERROR, error_reason="No ground connected"
    )
    assert s_error.run_enabled is True
    assert s_error.run_visual_role == "error_red"
    assert s_error.pause_enabled is False
    assert s_error.stop_enabled is False
    assert s_error.status_indicator_text == "■ Stopped"
    assert s_error.status_indicator_role == "error"
    assert "No ground connected" in s_error.run_tooltip


def test_meters_show_dash_before_simulation_and_after_stop() -> None:
    """Addition #2: Meters show '-- V' or '-- A' until simulation produces a reading, never a fake 0."""
    vm = Voltmeter("VM1", "n1", "0")
    am = Ammeter("A1", "n1", "n2")

    assert vm.has_reading is False
    assert am.has_reading is False
    assert vm.format_reading() == "-- V"
    assert am.format_reading() == "-- A"

    # Build a circuit in SimulationSession and inspect before start()
    ckt = Circuit()
    ckt.add(DCVoltageSource("V1", "n_src", "0", voltage=12.0))
    ckt.add(Ammeter("A1", "n_src", "n_load"))
    ckt.add(Resistor("R1", "n_load", "0", resistance=1000.0))
    ckt.add(Voltmeter("VM1", "n_load", "0"))
    ckt.add(Ground("GND1", "0"))

    session = SimulationSession(circuit=ckt)
    initial_frame = session.build_frame()
    assert session.state == SimulationState.STOPPED
    assert session.get_meter_reading_str("VM1") == "-- V"
    assert session.get_meter_reading_str("A1") == "-- A"
    assert session.get_meter_reading_value("VM1") is None
    assert session.get_meter_reading_value("A1") is None
    assert initial_frame.components["VM1"].display_value == "-- V"
    assert initial_frame.components["A1"].display_value == "-- A"

    # Start simulation -> real readings appear
    run_frame = session.start()
    assert run_frame.state == SimulationState.RUNNING
    assert session.get_meter_reading_str("VM1") == "12 V"
    assert session.get_meter_reading_str("A1") == "12 mA"
    r_parallel = (1000.0 * 1e7) / (1000.0 + 1e7)
    i_expected = 12.0 / (0.001 + r_parallel)
    v_expected = i_expected * r_parallel
    assert session.get_meter_reading_value("VM1") == pytest.approx(v_expected, rel=1e-6)
    assert session.get_meter_reading_value("A1") == pytest.approx(i_expected, rel=1e-6)

    # Stop simulation -> resets back to '-- V' and '-- A'
    stop_frame = session.stop()
    assert stop_frame.state == SimulationState.STOPPED
    assert session.get_meter_reading_str("VM1") == "-- V"
    assert session.get_meter_reading_str("A1") == "-- A"
    assert session.get_meter_reading_value("VM1") is None
    assert session.get_meter_reading_value("A1") is None
    assert stop_frame.components["VM1"].display_value == "-- V"
    assert stop_frame.components["A1"].display_value == "-- A"


def _build_12v_1k_switch_meters_session() -> SimulationSession:
    """Helper to construct the 12 V / 1 kOhm / Switch / Ammeter / Voltmeter schematic session."""
    placed = [
        PlacedComponentSpec(
            DCVoltageSource("V1", "a", "b", voltage=12.0),
            center_px=(0, 0),
            rotation_deg=90,  # pos at (0, -40), neg at (0, 40)
        ),
        PlacedComponentSpec(
            Switch("SW1", "a", "b", closed=True),
            center_px=(60, -40),  # a at (20, -40), b at (100, -40)
        ),
        PlacedComponentSpec(
            Ammeter("A1", "a", "b"),
            center_px=(160, -40),  # pos at (120, -40), neg at (200, -40)
        ),
        PlacedComponentSpec(
            Resistor("R1", "a", "b", resistance=1000.0),
            center_px=(220, 0),
            rotation_deg=90,  # a at (220, -40), b at (220, 40)
        ),
        PlacedComponentSpec(
            Voltmeter("VM1", "a", "b"),
            center_px=(300, 0),
            rotation_deg=90,  # pos at (300, -40), neg at (300, 40)
        ),
        PlacedComponentSpec(
            Ground("GND1", "0"),
            center_px=(0, 60),  # gnd at (0, 40)
        ),
    ]
    wires = [
        WireSpec("w_top_1", ((0, -40), (20, -40))),
        WireSpec("w_top_2", ((100, -40), (120, -40))),
        WireSpec("w_top_3", ((200, -40), (220, -40))),
        WireSpec("w_top_vm", ((220, -40), (300, -40))),
        WireSpec("w_bot_1", ((0, 40), (220, 40))),
        WireSpec("w_bot_vm", ((220, 40), (300, 40))),
    ]
    return SimulationSession.from_schematic(placed, wires)


def test_6a_voltmeter_across_1k_resistor_reads_12v() -> None:
    """Item 6a (1/5): Voltmeter across 1 kOhm resistor with 12 V source reads 12 V."""
    session = _build_12v_1k_switch_meters_session()
    assert session.get_meter_reading_str("VM1") == "-- V"

    frame = session.start()
    assert frame.state == SimulationState.RUNNING
    assert frame.diagnostics == ()

    r_load_1k = (1000.0 * 1e7) / (1000.0 + 1e7)
    r_total_1k = r_load_1k + 0.001 + 0.001
    v_resistor_1k = (12.0 / r_total_1k) * r_load_1k
    assert session.get_meter_reading_value("VM1") == pytest.approx(v_resistor_1k, rel=1e-6)
    assert session.get_meter_reading_str("VM1") == "12 V"


def test_6a_series_ammeter_with_12v_1k_reads_12ma() -> None:
    """Item 6a (2/5): Series ammeter with 12 V source and 1 kOhm resistor reads 12 mA."""
    session = _build_12v_1k_switch_meters_session()
    assert session.get_meter_reading_str("A1") == "-- A"

    session.start()
    r_load_1k = (1000.0 * 1e7) / (1000.0 + 1e7)
    r_total_1k = r_load_1k + 0.001 + 0.001
    i_analytic_1k = 12.0 / r_total_1k
    assert session.get_meter_reading_value("A1") == pytest.approx(i_analytic_1k, rel=1e-6)
    assert session.get_meter_reading_str("A1") == "12 mA"


def test_6a_toggling_switch_changes_meter_readings() -> None:
    """Item 6a (3/5): Toggling a switch changes voltmeter and ammeter readings as expected."""
    session = _build_12v_1k_switch_meters_session()
    session.start()

    r_load_1k = (1000.0 * 1e7) / (1000.0 + 1e7)
    r_total_1k = r_load_1k + 0.002
    i_analytic_1k = 12.0 / r_total_1k
    v_resistor_1k = i_analytic_1k * r_load_1k

    frame_open = session.toggle_switch("SW1")
    assert frame_open.components["SW1"].switch_closed is False
    assert frame_open.components["SW1"].display_value == "OFF"
    assert abs(session.get_meter_reading_value("A1") or 0.0) < 1e-7
    assert abs(session.get_meter_reading_value("VM1") or 0.0) < 1e-4

    frame_closed = session.toggle_switch("SW1")
    assert frame_closed.components["SW1"].switch_closed is True
    assert frame_closed.components["SW1"].display_value == "ON"
    assert session.get_meter_reading_value("VM1") == pytest.approx(v_resistor_1k, rel=1e-6)
    assert session.get_meter_reading_value("A1") == pytest.approx(i_analytic_1k, rel=1e-6)


def test_6a_live_resistor_change_to_500_ohm_gives_24ma() -> None:
    """Item 6a (4/5): Changing R1 live from 1 kOhm to 500 Ohm updates current to 24 mA."""
    session = _build_12v_1k_switch_meters_session()
    session.start()

    frame_500 = session.update_component_parameter("R1", "resistance", "500")
    assert frame_500.components["R1"].display_value == "500 Ω"
    r_load_500 = (500.0 * 1e7) / (500.0 + 1e7)
    i_analytic_500 = 12.0 / (r_load_500 + 0.002)
    assert session.get_meter_reading_value("A1") == pytest.approx(i_analytic_500, rel=1e-6)
    assert session.get_meter_reading_str("A1") == "24 mA"
    assert session.get_meter_reading_str("VM1") == "12 V"


def test_6a_live_source_change_to_6v_gives_12ma() -> None:
    """Item 6a (5/5): Changing V1 live to 6 V (with R1 = 500 Ohm) gives 12 mA and 6 V."""
    session = _build_12v_1k_switch_meters_session()
    session.start()
    session.update_component_parameter("R1", "resistance", "500")

    r_load_500 = (500.0 * 1e7) / (500.0 + 1e7)
    frame_6v = session.update_component_parameter("V1", "dc_voltage", "6")
    assert frame_6v.components["V1"].display_value == "6 V"
    assert session.get_meter_reading_value("VM1") == pytest.approx(6.0, rel=1e-5)
    assert session.get_meter_reading_value("A1") == pytest.approx(6.0 / (r_load_500 + 0.002), rel=1e-6)
    assert session.get_meter_reading_str("A1") == "12 mA"


def test_component_editable_parameters_validation() -> None:
    """Addition #1: Every component exposes editable parameters validated by the engineering parser."""
    r = Resistor("R1", "a", "b", resistance=1000.0)
    params = r.get_editable_parameters()
    assert len(params) == 1
    assert params[0].key == "resistance"
    assert r.format_parameter_value("resistance") == "1 k"

    r.set_parameter_value("resistance", "4.7k")
    assert r.resistance == pytest.approx(4700.0)

    with pytest.raises(ValueError, match="Couldn't read"):
        r.set_parameter_value("resistance", "not_a_number")
    with pytest.raises(ValueError, match="must be > 0"):
        r.set_parameter_value("resistance", "-10")

    # Lightbulb has rated_power and rated_voltage
    bulb = Lightbulb("B1", "a", "b", rated_power=60.0, rated_voltage=120.0)
    bulb_keys = [p.key for p in bulb.get_editable_parameters()]
    assert bulb_keys == ["rated_power", "rated_voltage"]
    bulb.set_parameter_value("rated_power", "100")
    bulb.set_parameter_value("rated_voltage", "240")
    assert bulb.rated_power == pytest.approx(100.0)
    assert bulb.rated_voltage == pytest.approx(240.0)

    # Inductor has inductance and dcr
    ind = Inductor("L1", "a", "b", inductance=10e-3, dcr=0.5)
    ind_keys = [p.key for p in ind.get_editable_parameters()]
    assert ind_keys == ["inductance", "dcr"]
    ind.set_parameter_value("inductance", "47m")
    ind.set_parameter_value("dcr", "1.2")
    assert ind.inductance == pytest.approx(47e-3)
    assert ind.dcr == pytest.approx(1.2)


def test_lightbulb_glow_and_over_bright_warning() -> None:
    """Step 2C: Lightbulb glow follows real dissipated power (P / P_rated),
    with an over-bright warning above 100%."""
    ckt = Circuit()
    ckt.add(DCVoltageSource("V1", "n1", "0", voltage=120.0))
    ckt.add(Lightbulb("B1", "n1", "0", rated_power=60.0, rated_voltage=120.0))
    ckt.add(Ground("GND1", "0"))

    session = SimulationSession(circuit=ckt)
    frame = session.start()
    b_tel = frame.components["B1"]
    assert b_tel.brightness == pytest.approx(1.0, rel=1e-4)
    assert b_tel.is_over_bright is False
    assert not any(d.code == "over_bright" for d in frame.diagnostics)

    # Increase voltage to 180 V -> P = V^2 / R_hot = (180/120)^2 * 60 W = 2.25 * 60 W = 135 W (225%)
    frame_high = session.update_component_parameter("V1", "dc_voltage", "180")
    b_tel_high = frame_high.components["B1"]
    assert b_tel_high.brightness == pytest.approx(2.25, rel=1e-4)
    assert b_tel_high.is_over_bright is True
    over_diags = [d for d in frame_high.diagnostics if d.code == "over_bright"]
    assert len(over_diags) == 1
    assert "B1" in over_diags[0].component_names


def test_isolated_junction_dot_not_on_any_wire_creates_no_net_or_warning() -> None:
    """Addition #4: A junction dot that is not on any wire must never create a net,
    a phantom connection, or a false warning."""
    placed = [
        PlacedComponentSpec(
            DCVoltageSource("V1", "a", "b", voltage=10.0),
            center_px=(0, 0),
            rotation_deg=90,
        ),
        PlacedComponentSpec(
            Resistor("R1", "a", "b", resistance=1000.0),
            center_px=(100, 0),
            rotation_deg=90,
        ),
        PlacedComponentSpec(
            Ground("GND1", "0"),
            center_px=(0, 60),
        ),
    ]
    wires = [
        WireSpec("w_top", ((0, -40), (100, -40))),
        WireSpec("w_bot", ((0, 40), (100, 40))),
    ]
    # Add stray junction dots in empty space (300, 300) and (-200, -200) not touching any wire
    conn = extract_connectivity(
        placed,
        wires,
        explicit_junctions=[(300, 300), (-200, -200)],
    )

    assert (300, 300) not in conn.point_to_node
    assert (-200, -200) not in conn.point_to_node
    assert (300, 300) not in conn.junction_dots
    assert (-200, -200) not in conn.junction_dots

    session = SimulationSession(circuit=conn.circuit, connectivity=conn)
    frame = session.start()
    assert frame.state == SimulationState.RUNNING
    assert frame.diagnostics == ()


def test_unconnected_part_ignored_with_warning_vs_connected_floating_island_error() -> None:
    """Item 4:
    - A component with no wires at all (e.g. an unconnected lightbulb B1) is ignored
      so the rest of the circuit runs, with an amber warning 'B1 is not connected and is ignored'.
    - A group of connected parts that really have no path to ground raises a floating-node error.
    """
    base_placed = [
        PlacedComponentSpec(
            DCVoltageSource("V1", "a", "b", voltage=12.0),
            center_px=(0, 0),
            rotation_deg=90,
        ),
        PlacedComponentSpec(
            Resistor("R1", "a", "b", resistance=1000.0),
            center_px=(100, 0),
            rotation_deg=90,
        ),
        PlacedComponentSpec(
            Ground("GND1", "0"),
            center_px=(0, 60),
        ),
        # Unconnected lightbulb placed off to the side with no wires
        PlacedComponentSpec(
            Lightbulb("B1", "a", "b", rated_power=60.0, rated_voltage=120.0),
            center_px=(400, 200),
        ),
    ]
    base_wires = [
        WireSpec("w_top", ((0, -40), (100, -40))),
        WireSpec("w_bot", ((0, 40), (100, 40))),
    ]

    session = SimulationSession.from_schematic(base_placed, base_wires)
    frame = session.start()
    assert frame.state == SimulationState.RUNNING
    unconn_diags = [d for d in frame.diagnostics if d.code == "unconnected_component"]
    assert len(unconn_diags) == 1
    assert unconn_diags[0].severity == "warning"
    assert unconn_diags[0].message == "B1 is not connected and is ignored"
    assert unconn_diags[0].component_names == ("B1",)

    # Now add a group of connected parts (R_isl1 and R_isl2 wired together) with no path to ground
    island_placed = base_placed + [
        PlacedComponentSpec(
            Resistor("R_isl1", "a", "b", resistance=220.0),
            center_px=(500, 0),
            rotation_deg=90,
        ),
        PlacedComponentSpec(
            Resistor("R_isl2", "a", "b", resistance=330.0),
            center_px=(600, 0),
            rotation_deg=90,
        ),
    ]
    island_wires = base_wires + [
        WireSpec("w_isl_top", ((500, -40), (600, -40))),
        WireSpec("w_isl_bot", ((500, 40), (600, 40))),
    ]
    session_island = SimulationSession.from_schematic(island_placed, island_wires)
    frame_island = session_island.start()
    assert frame_island.state == SimulationState.ERROR
    assert any(d.code == "floating_node" for d in frame_island.diagnostics)


def test_problem_diagnostics_for_errors_and_warnings() -> None:
    """Step 2C & Item 4: Problem highlighting diagnostics for no ground, floating node,
    voltage-source loop, parallel ammeter, and inductive kickback."""
    # 1. No ground (includes actionable hint)
    ckt_no_gnd = Circuit()
    ckt_no_gnd.add(DCVoltageSource("V1", "n1", "n2", voltage=5.0))
    ckt_no_gnd.add(Resistor("R1", "n1", "n2", resistance=100.0))
    s1 = SimulationSession(circuit=ckt_no_gnd)
    f1 = s1.start()
    assert f1.state == SimulationState.ERROR
    assert len(f1.diagnostics) == 1
    assert f1.diagnostics[0].code == "no_ground"
    assert "No ground connected" in f1.diagnostics[0].message
    assert "Add a Ground part and wire it to the circuit" in f1.diagnostics[0].message
    assert set(f1.diagnostics[0].component_names) == {"V1", "R1"}

    # 2. Floating node (disconnected island)
    ckt_float2 = Circuit()
    ckt_float2.add(DCVoltageSource("V1", "n1", "0", voltage=5.0))
    ckt_float2.add(Resistor("R1", "n1", "0", resistance=100.0))
    ckt_float2.add(Resistor("R_island", "n_a", "n_b", resistance=220.0))
    ckt_float2.add(Ground("GND1", "0"))
    s2 = SimulationSession(circuit=ckt_float2)
    f2 = s2.start()
    assert f2.state == SimulationState.ERROR
    assert f2.diagnostics[0].code == "floating_node"
    assert "R_island" in f2.diagnostics[0].component_names

    # 3. Voltage source loop
    ckt_vloop = Circuit()
    ckt_vloop.add(DCVoltageSource("V1", "n1", "0", voltage=12.0))
    ckt_vloop.add(DCVoltageSource("V2", "n1", "0", voltage=5.0))
    ckt_vloop.add(Ground("GND1", "0"))
    s3 = SimulationSession(circuit=ckt_vloop)
    f3 = s3.start()
    assert f3.state == SimulationState.ERROR
    assert f3.diagnostics[0].code == "voltage_source_loop"
    assert set(f3.diagnostics[0].component_names) == {"V1", "V2"}

    # 4. Ammeter in parallel with voltage source
    ckt_am = Circuit()
    ckt_am.add(DCVoltageSource("V1", "n1", "0", voltage=5.0))
    ckt_am.add(Ammeter("A1", "n1", "0"))
    ckt_am.add(Ground("GND1", "0"))
    s4 = SimulationSession(circuit=ckt_am)
    f4 = s4.start()
    assert f4.state == SimulationState.RUNNING
    assert any(d.code == "ammeter_in_parallel" and "A1" in d.component_names for d in f4.diagnostics)

    # 5. Inductive kickback when switch opens inductor current
    ckt_kick = Circuit()
    ckt_kick.add(DCVoltageSource("V1", "n_src", "0", voltage=12.0))
    ckt_kick.add(Resistor("R1", "n_src", "n_sw", resistance=10.0))
    ckt_kick.add(Switch("SW1", "n_sw", "n_ind", closed=True))
    ckt_kick.add(Inductor("L1", "n_ind", "0", inductance=0.1, dcr=1.0))
    ckt_kick.add(Ground("GND1", "0"))
    s5 = SimulationSession(circuit=ckt_kick, default_dt=1e-6)
    s5.start()
    f_kick = s5.toggle_switch("SW1")
    assert any(d.code == "inductive_kickback" for d in f_kick.diagnostics)


def test_qt_step2c_ui_responsiveness_upright_labels_speed_dropdown_and_quick_edit() -> None:
    """Run Qt verification in a dedicated subprocess so the main pytest runner never imports PySide6.
    Verifies:
    1. Addition #3: Labels and values stay upright (0 deg effective world rotation, no mirror flip)
       when rotated (0, 90, 180, 270) or flipped horizontally.
    2. Addition #5: Toolbar Speed dropdown (`speed_combo`) is visible without overflowing at 1024x768.
    3. Addition #1: QuickValueDialog validates engineering notation and shows a readable error on invalid input.
    4. Addition #7: Background QThread worker (`SimulationWorkerController`) runs live simulation chunks
       while the main GUI event loop processes timer heartbeats without freezing or stalling.
    """
    script = """
import sys
import time
from PySide6.QtCore import QEventLoop, QPointF, QTimer
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.components.resistor import Resistor
from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog

app = QApplication(sys.argv)
lib = SymbolLibrary()

# 1. Verify upright labels and values under all rotations & flips (Addition #3 & Item 5)
comp_item = ComponentItem(Resistor("R1", "a", "b", resistance=1000.0), lib)
for rot in (0, 90, 180, 270):
    for flip in (False, True):
        comp_item.set_rotation_deg(rot)
        comp_item.set_flipped_h(flip)
        assert comp_item.transform().isIdentity(), f"Expected identity QGraphicsItem transform for rot={rot}, flip={flip}"
        assert comp_item.effective_text_angle_deg() == 0.0, f"Text angle not upright for rot={rot}, flip={flip}"
        sel_rect = comp_item.selection_outline_rect_local()
        lbl_rect, val_rect, _ = comp_item._upright_label_and_value_rects()
        assert not sel_rect.intersects(lbl_rect), f"Selection box {sel_rect} overlaps label {lbl_rect} at rot={rot}"
        assert not sel_rect.intersects(val_rect), f"Selection box {sel_rect} overlaps value {val_rect} at rot={rot}"

# 2. Verify MainWindow toolbar Speed dropdown is visible at 1024x768 (Addition #5)
win = MainWindow()
win.resize(1024, 768)
win.show()
app.processEvents()
assert win.speed_combo.isVisible(), "Speed dropdown must be visible on toolbar without overflowing"

# 2b. Verify real toolbar actions and status bar state indicator match pure-Python mapping (Item 3)
from circuitsim.engine.simulation_session import SimulationState, compute_transport_controls_state
for state in (SimulationState.STOPPED, SimulationState.RUNNING, SimulationState.PAUSED, SimulationState.ERROR):
    expected_ui = compute_transport_controls_state(state, error_reason="No ground connected")
    win._sim_state = state
    win._apply_transport_controls_ui(state, error_reason="No ground connected")
    assert win.act_run.isEnabled() == expected_ui.run_enabled
    assert win.act_pause.isEnabled() == expected_ui.pause_enabled
    assert win.act_stop.isEnabled() == expected_ui.stop_enabled
    assert win.act_run.iconText() == expected_ui.run_icon_text
    assert win.status_state_indicator.text() == expected_ui.status_indicator_text
    # Also verify theme switching keeps the state indicator and button styles intact
    win.toggle_theme()
    assert win.status_state_indicator.text() == expected_ui.status_indicator_text
    win.toggle_theme()
win._sim_state = SimulationState.STOPPED
win._apply_transport_controls_ui(SimulationState.STOPPED)

# 3. Verify QuickValueDialog validation, live preview, and readable error message (Addition #1 & Item 2)
res = Resistor("R1", "a", "b", resistance=1000.0)
dlg = QuickValueDialog(res)
assert dlg.live_edit_note_label.text() == "Changes apply immediately while the simulation is running."
dlg.inputs["resistance"].setText("invalid_xyz")
assert dlg._apply_current_inputs() is False
assert dlg.error_label.isHidden() is False
assert "Couldn't read" in dlg.error_label.text()

dlg.inputs["resistance"].setText("5,65 G")
assert dlg.preview_labels["resistance"].text() == "= 5.65 GΩ"
assert dlg._apply_current_inputs() is True
assert dlg.applied_values["resistance"] == 5.65e9

dlg.inputs["resistance"].setText("4.7k")
assert dlg.preview_labels["resistance"].text() == "= 4.7 kΩ"
assert dlg._apply_current_inputs() is True
assert dlg.applied_values["resistance"] == 4700.0
assert res.resistance == 4700.0

# 4. Build a live circuit on the scene and verify non-freezing QThread simulation (Addition #7)
scene = win.circuit_scene
v1 = scene.place_new_component("dc_voltage", QPointF(0, 0), rotation_deg=90)   # pos at (0, -40), neg at (0, 40)
r1 = scene.place_new_component("resistor", QPointF(120, 0), rotation_deg=90)   # a at (120, -40), b at (120, 40)
vm1 = scene.place_new_component("voltmeter", QPointF(220, 0), rotation_deg=90) # pos at (220, -40), neg at (220, 40)
gnd = scene.place_new_component("ground", QPointF(0, 60))                      # gnd at (0, 40)

scene.add_wire([(0, -40), (120, -40)])
scene.add_wire([(120, -40), (220, -40)])
scene.add_wire([(0, 40), (120, 40)])
scene.add_wire([(120, 40), (220, 40)])

# Before running, voltmeter item on canvas shows '-- V'
assert vm1.component.format_reading() == "-- V"

# Measure main-thread responsiveness while simulation runs in background QThread for 240 ms
ui_heartbeats = 0
max_gap_ms = 0.0
last_tick = time.perf_counter()

def on_heartbeat():
    global ui_heartbeats, max_gap_ms, last_tick
    now = time.perf_counter()
    gap_ms = (now - last_tick) * 1000.0
    if ui_heartbeats > 0 and gap_ms > max_gap_ms:
        max_gap_ms = gap_ms
    last_tick = now
    ui_heartbeats += 1

heartbeat_timer = QTimer()
heartbeat_timer.setInterval(10)
heartbeat_timer.timeout.connect(on_heartbeat)
heartbeat_timer.start()

win.start_simulation()

loop = QEventLoop()
QTimer.singleShot(240, loop.quit)
loop.exec()
heartbeat_timer.stop()

# Verify main thread processed regular 10 ms heartbeats without stalling
assert ui_heartbeats >= 10, f"Expected >= 10 UI heartbeats during 240 ms run, got {ui_heartbeats}"
assert max_gap_ms < 120.0, f"Main UI thread stalled for {max_gap_ms:.1f} ms"

# Verify live voltmeter on canvas updated to '12 V'
assert vm1.live_display_value == "12 V", f"Expected live voltmeter readout '12 V', got {vm1.live_display_value!r}"

# Stop simulation and verify meter resets to '-- V'
win.stop_simulation()
stop_loop = QEventLoop()
QTimer.singleShot(60, stop_loop.quit)
stop_loop.exec()
assert vm1.component.format_reading() == "-- V", f"Expected '-- V' after Stop, got {vm1.component.format_reading()!r}"

win.circuit_scene.undo_stack.setClean()  # no 'unsaved changes' prompt in tests
win.close()
"""
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    print(res.stdout.strip())
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_6b_value_edit_undo_and_redo_while_stopped_and_running() -> None:
    """Item 6b: Editing a resistor value and pressing Ctrl+Z restores the old value in
    the component model, the canvas label, and the live simulation result; Ctrl+Y reapplies
    it. Tested both while stopped and while running.
    """
    script = """
import sys
from PySide6.QtCore import QEventLoop, QPointF, QTimer
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.canvas.component_item import format_component_value_summary

app = QApplication(sys.argv)
win = MainWindow()
scene = win.circuit_scene

v1 = scene.place_new_component("dc_voltage", QPointF(0, 0), rotation_deg=90)   # pos (0,-40), neg (0,40)
a1 = scene.place_new_component("ammeter", QPointF(80, -40))                    # pos (40,-40), neg (120,-40)
r1 = scene.place_new_component("resistor", QPointF(160, 0), rotation_deg=90)   # a (160,-40), b (160,40)
gnd = scene.place_new_component("ground", QPointF(0, 60))                      # gnd (0,40)

scene.add_wire([(0, -40), (40, -40)])
scene.add_wire([(120, -40), (160, -40)])
scene.add_wire([(0, 40), (160, 40)])

def wait_ms(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()

# 1. Test value edit + Undo (Ctrl+Z) + Redo (Ctrl+Y) while STOPPED
assert r1.component.resistance == 1000.0
assert format_component_value_summary(r1.component) == "1 kΩ"

assert scene.edit_component_parameters(r1, {"resistance": "2k"}) is True
assert r1.component.resistance == 2000.0
assert format_component_value_summary(r1.component) == "2 kΩ"

scene.undo_stack.undo()
assert r1.component.resistance == 1000.0
assert format_component_value_summary(r1.component) == "1 kΩ"

scene.undo_stack.redo()
assert r1.component.resistance == 2000.0
assert format_component_value_summary(r1.component) == "2 kΩ"

# Undo back to 1 kOhm before starting simulation
scene.undo_stack.undo()
assert r1.component.resistance == 1000.0

# 2. Test value edit + Undo (Ctrl+Z) + Redo (Ctrl+Y) while RUNNING
win.start_simulation()
wait_ms(80)
assert a1.live_display_value == "12 mA", f"Expected 12 mA initially, got {a1.live_display_value!r}"
assert r1.live_display_value == "1 kΩ"

# Edit R1 from 1 kOhm to 500 Ohm while running -> current becomes 24 mA
assert scene.edit_component_parameters(r1, {"resistance": "500"}) is True
wait_ms(80)
assert r1.component.resistance == 500.0
assert r1.live_display_value == "500 Ω"
assert a1.live_display_value == "24 mA", f"Expected 24 mA after live edit, got {a1.live_display_value!r}"

# Undo (Ctrl+Z) while running -> restores 1 kOhm and 12 mA live
scene.undo_stack.undo()
wait_ms(80)
assert r1.component.resistance == 1000.0
assert r1.live_display_value == "1 kΩ"
assert a1.live_display_value == "12 mA", f"Expected 12 mA after Undo while running, got {a1.live_display_value!r}"

# Redo (Ctrl+Y) while running -> reapplies 500 Ohm and 24 mA live
scene.undo_stack.redo()
wait_ms(80)
assert r1.component.resistance == 500.0
assert r1.live_display_value == "500 Ω"
assert a1.live_display_value == "24 mA", f"Expected 24 mA after Redo while running, got {a1.live_display_value!r}"

win.circuit_scene.undo_stack.setClean()  # no 'unsaved changes' prompt in tests
win.close()
"""
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    print(res.stdout.strip())
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_6c_close_main_window_while_running_stops_worker_thread_cleanly() -> None:
    """Item 6c: Closing MainWindow while a simulation is running stops the QThread cleanly."""
    script = """
import sys
from PySide6.QtCore import QEventLoop, QPointF, QTimer
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
win.show()
scene = win.circuit_scene

scene.place_new_component("dc_voltage", QPointF(0, 0), rotation_deg=90)
scene.place_new_component("resistor", QPointF(100, 0), rotation_deg=90)
scene.place_new_component("ground", QPointF(0, 60))
scene.add_wire([(0, -40), (100, -40)])
scene.add_wire([(0, 40), (100, 40)])

win.start_simulation()
loop = QEventLoop()
QTimer.singleShot(80, loop.quit)
loop.exec()

assert win.sim_controller._thread.isRunning() is True, "Worker QThread should be running during simulation"
win.circuit_scene.undo_stack.setClean()  # no 'unsaved changes' prompt in tests
win.close()
app.processEvents()
assert win.sim_controller._thread.isRunning() is False, "Worker QThread must stop cleanly when MainWindow closes"
"""
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    print(res.stdout.strip())
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_6d_canvas_item_and_wire_highlight_colors_and_status_bar_text() -> None:
    """Item 6d: Real canvas item and wire colour state:
    - 'no_ground' highlights items and wires in red ('#FF5252'),
    - 'ammeter_in_parallel' highlights in amber ('#FFA726'),
    - fixing the circuit clears the highlight (None),
    - and status_warnings.text() matches the diagnostic.
    """
    script = """
import sys
from PySide6.QtCore import QEventLoop, QPointF, QTimer
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
scene = win.circuit_scene

def wait_ms(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()

# 1. 'no_ground' -> red highlight ('#FF5252') on components and wires
v1 = scene.place_new_component("dc_voltage", QPointF(0, 0), rotation_deg=90)
r1 = scene.place_new_component("resistor", QPointF(100, 0), rotation_deg=90)
w_top = scene.add_wire([(0, -40), (100, -40)])
w_bot = scene.add_wire([(0, 40), (100, 40)])

win.start_simulation()
wait_ms(80)

assert v1.effective_highlight_color() == "#FF5252"
assert r1.effective_highlight_color() == "#FF5252"
assert w_top.effective_highlight_color() == "#FF5252"
assert w_bot.effective_highlight_color() == "#FF5252"
assert "No ground connected" in win.status_warnings.text()

# 2. Add Ground + Ammeter in parallel with V1 -> amber highlight ('#FFA726') on ammeter and wires
gnd = scene.place_new_component("ground", QPointF(0, 60))
a1 = scene.place_new_component("ammeter", QPointF(200, 0), rotation_deg=90)
w_am_top = scene.add_wire([(100, -40), (200, -40)])
w_am_bot = scene.add_wire([(100, 40), (200, 40)])

win.start_simulation()
wait_ms(80)

assert a1.effective_highlight_color() == "#FFA726"
assert w_am_top.effective_highlight_color() == "#FFA726"
assert w_am_bot.effective_highlight_color() == "#FFA726"
assert "Ammeter A1" in win.status_warnings.text()

# 3. Fix circuit by deleting the parallel ammeter -> highlights clear to None and status_warnings == 'Simulation Running (OK)'
scene.clearSelection()
a1.setSelected(True)
scene.delete_selected()
wait_ms(80)

assert v1.effective_highlight_color() is None
assert r1.effective_highlight_color() is None
assert w_top.effective_highlight_color() is None
assert w_bot.effective_highlight_color() is None
assert win.status_warnings.text() == "Simulation Running (OK)"

win.circuit_scene.undo_stack.setClean()  # no 'unsaved changes' prompt in tests
win.close()
"""
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    print(res.stdout.strip())
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_6e_ui_responsiveness_on_30_resistor_ladder_plus_rc_load() -> None:
    """Item 6e: Run the UI-responsiveness benchmark on a 30-resistor ladder plus an RC load.
    Reads max-gap threshold from CIRCUITSIM_MAX_UI_GAP_MS (default 180.0 ms).
    """
    script = """
import os
import sys
import time
from PySide6.QtCore import QEventLoop, QPointF, QTimer
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
scene = win.circuit_scene

# Build an AC source + 15-stage (30-resistor) ladder + RC load
# Stage k (k = 0..14):
# - series resistor from x = k*80 to x = (k+1)*80 along y = -40 (center at (k*80 + 40, -40))
# - shunt resistor at x = (k+1)*80 from y = -40 to y = 40 (center at ((k+1)*80, 0), rot=90)
scene.place_new_component("ac_voltage", QPointF(0, 0), rotation_deg=90)  # (0, -40) to (0, 40)
scene.place_new_component("ground", QPointF(0, 60))                      # (0, 40)

for k in range(15):
    x_left = k * 80
    x_right = (k + 1) * 80
    # Series resistor (80 px wide, terminals at x_left+0 and x_right+0 when centered at x_left+40)
    scene.place_new_component("resistor", QPointF(x_left + 40, -40), rotation_deg=0)
    # Shunt resistor (80 px tall, terminals at (x_right, -40) and (x_right, 40))
    scene.place_new_component("resistor", QPointF(x_right, 0), rotation_deg=90)
    # Bottom return wire segment
    scene.add_wire([(x_left, 40), (x_right, 40)])

# Add RC load at the end of the 30-resistor ladder (x = 1200 to x = 1280)
scene.place_new_component("resistor", QPointF(1240, -40), rotation_deg=0)
scene.place_new_component("capacitor", QPointF(1280, 0), rotation_deg=90)
scene.add_wire([(1200, 40), (1280, 40)])

threshold_ms = float(os.environ.get("CIRCUITSIM_MAX_UI_GAP_MS", "180.0"))
ui_heartbeats = 0
max_gap_ms = 0.0
gaps = []
last_tick = time.perf_counter()

def on_heartbeat():
    global ui_heartbeats, max_gap_ms, last_tick
    now = time.perf_counter()
    gap_ms = (now - last_tick) * 1000.0
    if ui_heartbeats > 0:
        gaps.append(gap_ms)
        if gap_ms > max_gap_ms:
            max_gap_ms = gap_ms
    last_tick = now
    ui_heartbeats += 1

heartbeat_timer = QTimer()
heartbeat_timer.setInterval(10)
heartbeat_timer.timeout.connect(on_heartbeat)
heartbeat_timer.start()

win.start_simulation()
loop = QEventLoop()
QTimer.singleShot(300, loop.quit)
loop.exec()
heartbeat_timer.stop()

avg_gap_ms = sum(gaps) / len(gaps) if gaps else 0.0
print(f"BENCHMARK_6E: heartbeats={ui_heartbeats}, avg_gap_ms={avg_gap_ms:.2f}, max_gap_ms={max_gap_ms:.2f}, threshold_ms={threshold_ms:.1f}")

assert win._sim_state.value == "running", f"Expected running state, got {win._sim_state}"
assert ui_heartbeats >= 12, f"Expected >= 12 UI heartbeats during 300 ms ladder run, got {ui_heartbeats}"
assert max_gap_ms < threshold_ms, f"Main UI thread stalled for {max_gap_ms:.2f} ms (threshold {threshold_ms:.1f} ms)"

win.circuit_scene.undo_stack.setClean()  # no 'unsaved changes' prompt in tests
win.close()
"""
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    print(res.stdout.strip())
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
