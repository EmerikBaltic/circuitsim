"""Unit tests for Milestone 1 Step A: DC MNA solver, components, conditioning, and errors."""

from __future__ import annotations

import math
import sys
import pytest

from circuitsim.components import (
    Ammeter,
    DCCurrentSource,
    DCVoltageSource,
    Ground,
    Lightbulb,
    MeterMode,
    Resistor,
    Switch,
    Voltmeter,
)
from circuitsim.engine import (
    Circuit,
    FloatingNodeError,
    MNASolver,
    NoGroundError,
    VoltageSourceLoopError,
)


def test_no_qt_imports_in_engine_or_components() -> None:
    """Verify the physics engine and component models do not import PySide6."""
    qt_modules = [m for m in sys.modules if m.startswith("PySide6")]
    assert qt_modules == []


def test_voltage_divider_analytical() -> None:
    """Check a 2-resistor voltage divider against V_out = Vs * R2 / (R1 + R2)."""
    vs = 12.0
    r1 = 1000.0
    r2 = 3000.0

    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "in", "0", voltage=vs))
    circuit.add(Resistor("R1", "in", "out", resistance=r1))
    circuit.add(Resistor("R2", "out", "0", resistance=r2))
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)
    res = solver.solve_dc()

    expected_v_out = vs * (r2 / (r1 + r2))  # 12 * 3000 / 4000 = 9.0 V
    expected_current = vs / (r1 + r2)  # 12 / 4000 = 3 mA

    # With GMIN = 1e-12 S in parallel with R2 = 3 kOhm, the GMIN branch draws
    # 9 V * 1e-12 S = 9 pA (a 2.25e-9 relative shift on the 3 mA current).
    assert math.isclose(res.node_voltages["in"], vs, rel_tol=1e-12)
    assert math.isclose(res.node_voltages["out"], expected_v_out, rel_tol=1e-9)
    assert math.isclose(res.branch_currents["R1"], expected_current, rel_tol=1e-8)
    assert math.isclose(res.branch_currents["R2"], expected_current, rel_tol=1e-8)

    # Exact KCL check at node 'out' including GMIN (to machine precision 1e-14):
    i_gmin = res.node_voltages["out"] * solver.gmin
    assert math.isclose(
        res.branch_currents["R1"],
        res.branch_currents["R2"] + i_gmin,
        rel_tol=1e-14,
    )


def test_series_parallel_and_wheatstone_bridge_analytical() -> None:
    """Check an unbalanced Wheatstone bridge against exact analytical nodal formulas."""
    vs = 10.0
    r1, r2 = 1000.0, 2000.0
    r3, r4 = 3000.0, 1500.0

    circuit = Circuit()
    circuit.add(DCVoltageSource("Vs", "top", "0", voltage=vs))
    circuit.add(Resistor("R1", "top", "left", resistance=r1))
    circuit.add(Resistor("R2", "left", "0", resistance=r2))
    circuit.add(Resistor("R3", "top", "right", resistance=r3))
    circuit.add(Resistor("R4", "right", "0", resistance=r4))
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)
    res = solver.solve_dc()

    expected_v_left = vs * r2 / (r1 + r2)
    expected_v_right = vs * r4 / (r3 + r4)
    expected_i_total = vs / (r1 + r2) + vs / (r3 + r4)

    # Note: GMIN = 1e-12 S across R3 || R4 (1 kOhm) shifts V_right by 1e-9 relative.
    assert math.isclose(res.node_voltages["left"], expected_v_left, rel_tol=1e-8)
    assert math.isclose(res.node_voltages["right"], expected_v_right, rel_tol=1e-8)
    vs_comp = circuit.get_component("Vs")
    assert isinstance(vs_comp, DCVoltageSource)
    assert math.isclose(vs_comp.delivered_current, expected_i_total, rel_tol=1e-8)


def test_current_source_parallel_resistors() -> None:
    """Verify DCCurrentSource feeding three parallel resistors."""
    i_src = 0.06  # 60 mA
    r1, r2, r3 = 100.0, 200.0, 300.0
    g_eq = (1.0 / r1) + (1.0 / r2) + (1.0 / r3)
    r_eq = 1.0 / g_eq
    expected_v = i_src * r_eq

    circuit = Circuit()
    circuit.add(DCCurrentSource("I1", "n1", "0", current=i_src))
    circuit.add(Resistor("R1", "n1", "0", resistance=r1))
    circuit.add(Resistor("R2", "n1", "0", resistance=r2))
    circuit.add(Resistor("R3", "n1", "0", resistance=r3))
    circuit.add(Ground("GND", "0"))

    res = MNASolver(circuit).solve_dc()
    assert math.isclose(res.node_voltages["n1"], expected_v, rel_tol=1e-9)
    assert math.isclose(res.branch_currents["R1"], expected_v / r1, rel_tol=1e-9)
    assert math.isclose(res.branch_currents["R2"], expected_v / r2, rel_tol=1e-9)
    assert math.isclose(res.branch_currents["R3"], expected_v / r3, rel_tol=1e-9)


def test_lightbulb_60w_120v_specification() -> None:
    """Section 11 requirement: 60 W at 120 V must read 240 ohm hot, 0.5 A, 100% brightness."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "line", "0", voltage=120.0))
    bulb = Lightbulb("B1", "line", "0", rated_power=60.0, rated_voltage=120.0)
    circuit.add(bulb)
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)
    solver.solve_dc()

    # Analytical checks: R_hot = 120^2 / 60 = 240 Ohm, I = 120 / 240 = 0.5 A, P = 60 W
    assert math.isclose(bulb.r_hot, 240.0, rel_tol=1e-12)
    assert math.isclose(bulb.effective_resistance(), 240.0, rel_tol=1e-12)
    assert math.isclose(bulb.current, 0.5, rel_tol=1e-9)
    assert math.isclose(bulb.power, 60.0, rel_tol=1e-9)
    assert math.isclose(bulb.brightness, 1.0, rel_tol=1e-9)
    assert math.isclose(bulb.brightness_percent, 100.0, rel_tol=1e-9)
    assert not bulb.is_over_bright


def test_lightbulb_optional_filament_model_inrush_and_warmup() -> None:
    """Verify optional filament model draws 10x cold inrush current at t=0 and warms up."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "line", "0", voltage=120.0))
    bulb = Lightbulb(
        "B1",
        "line",
        "0",
        rated_power=60.0,
        rated_voltage=120.0,
        use_filament_model=True,
        cold_resistance_ratio=0.1,
        thermal_time_constant=0.04,
    )
    circuit.add(bulb)
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)

    # At t = 0, filament is cold (R_cold = 24 Ohm -> I_inrush = 120 / 24 = 5.0 A)
    solver.solve_dc()
    assert math.isclose(bulb.effective_resistance(), 24.0, rel_tol=1e-9)
    assert math.isclose(bulb.current, 5.0, rel_tol=1e-9)

    # Step thermal state forward by 10 ms; filament heats up and resistance rises
    changed = bulb.advance_thermal_state(dt=0.01)
    assert changed
    assert bulb.temperature > 0.0
    assert bulb.effective_resistance() > 24.0


def test_switch_open_closed_and_lu_cache_reuse() -> None:
    """Verify switch ON/OFF states and that LU factorization is cached until switch toggles."""
    circuit = Circuit()
    vs = DCVoltageSource("V1", "in", "0", voltage=10.0)
    sw = Switch("SW1", "in", "load", closed=False, toggle_time=0.005)
    r_load = Resistor("R1", "load", "0", resistance=100.0)
    circuit.add(vs)
    circuit.add(sw)
    circuit.add(r_load)
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)

    # 1. First solve with switch OPEN (1 GOhm in series with 100 Ohm):
    res1 = solver.solve_dc()
    assert res1.rebuilt_matrix is True
    expected_v_open = 10.0 * (100.0 / (1e9 + 100.0))
    assert math.isclose(res1.node_voltages["load"], expected_v_open, rel_tol=1e-4)

    # 2. Change DC source voltage only -> matrix A does NOT change, LU cache reused!
    vs.dc_voltage = 20.0
    res2 = solver.solve_dc()
    assert res2.rebuilt_matrix is False
    assert math.isclose(res2.node_voltages["load"], 2.0 * expected_v_open, rel_tol=1e-4)

    # 3. Trigger timed switch event at t = 5 ms -> switch closes (1 mOhm) -> matrix rebuilt!
    toggled = sw.check_timed_event(0.005)
    assert toggled is True
    assert sw.closed is True
    res3 = solver.solve_dc()
    assert res3.rebuilt_matrix is True
    expected_v_closed = 20.0 * (100.0 / (100.0 + 1e-3))
    assert math.isclose(res3.node_voltages["load"], expected_v_closed, rel_tol=1e-9)


def test_voltmeter_and_ammeter_readings_and_polarity() -> None:
    """Verify voltmeter (10 MOhm) and ammeter (1 mOhm) give accurate polarity-aware readings."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "src", "0", voltage=10.0))
    # Connect ammeter in series from 'src' to 'load'
    ammeter = Ammeter("A1", "src", "load", r_internal=1e-3)
    # Connect a second ammeter backwards in series from 'load' to 'ret' to check negative polarity
    ammeter_rev = Ammeter("A_rev", "0", "ret", r_internal=1e-3)
    r_load = Resistor("R_load", "load", "ret", resistance=1000.0)
    # Connect voltmeter across R_load with reversed probes (red on 'ret', black on 'load')
    voltmeter_rev = Voltmeter("VM_rev", "ret", "load", r_internal=10e6)
    voltmeter_fwd = Voltmeter("VM_fwd", "load", "ret", r_internal=10e6)

    circuit.add(ammeter)
    circuit.add(r_load)
    circuit.add(ammeter_rev)
    circuit.add(voltmeter_fwd)
    circuit.add(voltmeter_rev)
    circuit.add(Ground("GND", "0"))

    MNASolver(circuit).solve_dc()

    # Parallel combination of 1000 Ohm and two 10 MOhm voltmeters:
    r_parallel = 1.0 / (1.0 / 1000.0 + 2.0 / 10e6)
    r_total = r_parallel + 2.0 * 1e-3
    expected_i = 10.0 / r_total
    expected_v_load = expected_i * r_parallel

    assert math.isclose(ammeter.reading, expected_i, rel_tol=1e-9)
    assert math.isclose(ammeter_rev.reading, -expected_i, rel_tol=1e-9)
    assert math.isclose(voltmeter_fwd.reading, expected_v_load, rel_tol=1e-9)
    assert math.isclose(voltmeter_rev.reading, -expected_v_load, rel_tol=1e-9)
    assert ammeter.format_reading() == "10 mA"
    assert voltmeter_rev.format_reading() == "-10 V"


def test_matrix_conditioning_with_extreme_values() -> None:
    """Measure condition number and accuracy when 1 mOhm, 1 GOhm, and GMIN=1e-12 coexist."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "n_src", "0", voltage=10.0))
    # 1 mOhm ammeter in series with a 1 mOhm closed switch
    circuit.add(Ammeter("A1", "n_src", "n_after_amm", r_internal=1e-3))
    circuit.add(Switch("SW_closed", "n_after_amm", "n_main", closed=True, r_on=1e-3))
    circuit.add(Resistor("R_load", "n_main", "0", resistance=100.0))
    # 1 GOhm open switch connected to an isolated node that only has GMIN (1e-12 S) to ground
    circuit.add(Switch("SW_open", "n_main", "n_isolated", closed=False, r_off=1e9))
    circuit.add(Resistor("R_high", "n_isolated", "0", resistance=1e9))
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit, gmin=1e-12)
    res = solver.solve_dc(compute_cond=True)

    assert res.condition_number is not None
    # Verify that despite spanning 1e3 S down to 1e-9 S (+ 1e-12 S GMIN),
    # the solved voltages match exact analytical nodal equations to high precision.
    g_branch_isolated = 1.0 / (1e9 + 1.0 / (1e-9 + 1e-12))
    g_main_to_gnd = (1.0 / 100.0) + g_branch_isolated + 1e-12
    r_series = 1e-3 + 1e-3
    # Node 'n_main' voltage via exact voltage divider:
    r_main = 1.0 / g_main_to_gnd
    expected_v_main = 10.0 * r_main / (r_series + r_main)
    expected_v_isolated = expected_v_main * (1e-9 / (1e-9 + 1e-9 + 1e-12))

    assert math.isclose(res.node_voltages["n_main"], expected_v_main, rel_tol=1e-7)
    assert math.isclose(res.node_voltages["n_isolated"], expected_v_isolated, rel_tol=1e-6)


def test_error_no_ground() -> None:
    """Verify missing Ground raises NoGroundError with plain-language message."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "a", "b", voltage=5.0))
    circuit.add(Resistor("R1", "a", "b", resistance=100.0))

    with pytest.raises(NoGroundError, match="No ground connected"):
        MNASolver(circuit).solve_dc()


def test_error_floating_node_disconnected_and_dangling() -> None:
    """Verify both a dangling terminal and a disconnected island raise FloatingNodeError."""
    # Case 1: Dangling single-terminal node
    c1 = Circuit()
    c1.add(DCVoltageSource("V1", "in", "0", voltage=5.0))
    c1.add(Resistor("R1", "in", "0", resistance=100.0))
    c1.add(Resistor("R_dangling", "in", "floating_tip", resistance=100.0))
    c1.add(Ground("GND", "0"))

    with pytest.raises(FloatingNodeError, match="Node floating_tip is floating"):
        MNASolver(c1).solve_dc()

    # Case 2: Disconnected island loop with no path to ground
    c2 = Circuit()
    c2.add(DCVoltageSource("V1", "in", "0", voltage=5.0))
    c2.add(Resistor("R1", "in", "0", resistance=100.0))
    c2.add(Resistor("R_isl1", "isl_a", "isl_b", resistance=100.0))
    c2.add(Resistor("R_isl2", "isl_b", "isl_a", resistance=200.0))
    c2.add(Ground("GND", "0"))

    with pytest.raises(FloatingNodeError, match="Node isl_a is floating"):
        MNASolver(c2).solve_dc()


def test_error_voltage_source_loop() -> None:
    """Verify ideal voltage sources in parallel or a loop raise VoltageSourceLoopError."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "a", "0", voltage=5.0))
    circuit.add(DCVoltageSource("V2", "a", "0", voltage=5.0))
    circuit.add(Resistor("R1", "a", "0", resistance=100.0))
    circuit.add(Ground("GND", "0"))

    with pytest.raises(VoltageSourceLoopError, match="Voltage sources in a loop"):
        MNASolver(circuit).solve_dc()


def test_warning_ammeter_in_parallel_with_voltage_source() -> None:
    """Verify connecting an ammeter directly across a voltage source raises a warning."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "pos", "0", voltage=5.0))
    circuit.add(Ammeter("A_bad", "pos", "0", r_internal=1e-3))
    circuit.add(Ground("GND", "0"))

    res = MNASolver(circuit).solve_dc()
    assert len(res.warnings) == 1
    assert res.warnings[0].code == "ammeter_in_parallel"
    assert "A_bad" in res.warnings[0].message
    # Near-short draws 5 V / 1 mOhm = 5000 A
    ammeter = circuit.get_component("A_bad")
    assert isinstance(ammeter, Ammeter)
    assert math.isclose(ammeter.reading, 5000.0, rel_tol=1e-9)
