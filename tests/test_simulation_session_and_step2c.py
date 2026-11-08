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
)


def test_simulation_session_has_zero_qt_imports() -> None:
    """Verify `circuitsim.engine.simulation_session` imports zero PySide6 modules."""
    qt_mods = [m for m in sys.modules if m.startswith("PySide6")]
    assert qt_mods == []


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


def test_schematic_12v_1k_voltmeter_ammeter_switch_and_live_resistor_edit() -> None:
    """Addition #6 (analytic test, independent of code):
    - 12 V source with 1 kOhm resistor and voltmeter across it reads 12 V
    - Ammeter in series reads 12 mA
    - Toggling a switch changes the readings (0 V / 0 A when open, 12 V / 12 mA when closed)
    - Changing resistor value live changes the result as Ohm's law I = V / R predicts.
    """
    # Build via schematic placement + wire extraction (end-to-end headless test):
    # Under 90° CW rotation, local terminal (-2, 0) maps to (cx, cy - 40)
    # and local terminal (+2, 0) maps to (cx, cy + 40).
    # In dc_voltage.json, pos is at [-2, 0] -> (0, -40) and neg is at [2, 0] -> (0, 40).
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

    session = SimulationSession.from_schematic(placed, wires)

    # Before simulation starts, meters must read "-- V" and "-- A"
    assert session.get_meter_reading_str("VM1") == "-- V"
    assert session.get_meter_reading_str("A1") == "-- A"

    # Start simulation
    frame = session.start()
    assert frame.state == SimulationState.RUNNING
    assert frame.diagnostics == ()

    # Analytic Ohm's law check: V = 12 V, R_load = 1000 Ohm || 10 MOhm, R_series = 1 mOhm + 1 mOhm
    v_ideal = 12.0
    r_load_1k = (1000.0 * 1e7) / (1000.0 + 1e7)
    r_total_1k = r_load_1k + 0.001 + 0.001
    i_analytic_1k = v_ideal / r_total_1k
    v_resistor_1k = i_analytic_1k * r_load_1k

    assert session.get_meter_reading_value("VM1") == pytest.approx(v_resistor_1k, rel=1e-6)
    assert session.get_meter_reading_value("A1") == pytest.approx(i_analytic_1k, rel=1e-6)
    assert session.get_meter_reading_str("VM1") == "12 V"
    assert session.get_meter_reading_str("A1") == "12 mA"

    # Toggle switch OPEN while running -> current and resistor voltage drop to ~0
    frame_open = session.toggle_switch("SW1")
    assert frame_open.components["SW1"].switch_closed is False
    assert frame_open.components["SW1"].display_value == "OFF"
    # With 1 GOhm open switch, I = 12 V / 1e9 Ohm = 12 nA, V_R = 12 uV
    assert abs(session.get_meter_reading_value("A1") or 0.0) < 1e-7
    assert abs(session.get_meter_reading_value("VM1") or 0.0) < 1e-4

    # Toggle switch CLOSED again -> restores 12 V and 12 mA
    frame_closed = session.toggle_switch("SW1")
    assert frame_closed.components["SW1"].switch_closed is True
    assert frame_closed.components["SW1"].display_value == "ON"
    assert session.get_meter_reading_value("VM1") == pytest.approx(v_resistor_1k, rel=1e-6)
    assert session.get_meter_reading_value("A1") == pytest.approx(i_analytic_1k, rel=1e-6)

    # Live parameter edit while running: change R1 from 1 kOhm to "500" (500 Ohm)
    # Analytic Ohm's law: I = 12 V / (500 Ohm || 10 MOhm + 2 mOhm) = 24 mA
    frame_500 = session.update_component_parameter("R1", "resistance", "500")
    assert frame_500.components["R1"].display_value == "500 Ω"
    r_load_500 = (500.0 * 1e7) / (500.0 + 1e7)
    i_analytic_500 = 12.0 / (r_load_500 + 0.002)
    assert session.get_meter_reading_value("A1") == pytest.approx(i_analytic_500, rel=1e-6)
    assert session.get_meter_reading_str("A1") == "24 mA"
    assert session.get_meter_reading_str("VM1") == "12 V"

    # Also change DC source voltage live to "6" V -> I = 6 V / 500 Ohm = 12 mA
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


def test_problem_diagnostics_for_errors_and_warnings() -> None:
    """Step 2C: Problem highlighting diagnostics for no ground, floating node,
    voltage-source loop, parallel ammeter, and inductive kickback."""
    # 1. No ground
    ckt_no_gnd = Circuit()
    ckt_no_gnd.add(DCVoltageSource("V1", "n1", "n2", voltage=5.0))
    ckt_no_gnd.add(Resistor("R1", "n1", "n2", resistance=100.0))
    s1 = SimulationSession(circuit=ckt_no_gnd)
    f1 = s1.start()
    assert f1.state == SimulationState.ERROR
    assert len(f1.diagnostics) == 1
    assert f1.diagnostics[0].code == "no_ground"
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

# 1. Verify upright labels and values under all rotations & flips (Addition #3)
comp_item = ComponentItem(Resistor("R1", "a", "b", resistance=1000.0), lib)
for rot in (0, 90, 180, 270):
    for flip in (False, True):
        comp_item.set_rotation_deg(rot)
        comp_item.set_flipped_h(flip)
        assert comp_item.transform().isIdentity(), f"Expected identity QGraphicsItem transform for rot={rot}, flip={flip}"
        assert comp_item.effective_text_angle_deg() == 0.0, f"Text angle not upright for rot={rot}, flip={flip}"

# 2. Verify MainWindow toolbar Speed dropdown is visible at 1024x768 (Addition #5)
win = MainWindow()
win.resize(1024, 768)
win.show()
app.processEvents()
assert win.speed_combo.isVisible(), "Speed dropdown must be visible on toolbar without overflowing"

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

win.close()
"""
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
