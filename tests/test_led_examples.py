"""Tests for Item 5: LED Example Circuits and Analytical Hand-Calculated Solutions."""

from __future__ import annotations

import math
import os
from pathlib import Path
import subprocess
import sys
import pytest

from circuitsim.canvas.connectivity import extract_connectivity
from circuitsim.components import LED
from circuitsim.engine.solver import MNASolver
from circuitsim.io.circ_serializer import load_document


def test_led_with_resistor_analytical() -> None:
    """Verify 'LED with a resistor' example matches hand calculations.

    Hand calculations:
        Source: V1 = 5.0 V
        Resistor: R1 = 150.0 Ω
        Red LED: Vf = 2.0 V, r_on = 1 mΩ
        Current:
            I = (V_src - V_f) / (R1 + r_on)
              = (5.0 - 2.0) / (150.0 + 0.001)
              = 3.0 / 150.001
              ≈ 0.02000 A (20.0 mA)
        Voltages:
            V_R1 = 150.0 * 0.020 = 3.0 V
            V_D1 = 2.0 V
    """
    ex_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "circuitsim"
        / "resources"
        / "examples"
        / "led_resistor.circ"
    )
    assert ex_path.exists(), f"File missing: {ex_path}"

    doc = load_document(ex_path)
    conn = extract_connectivity(doc.placed, doc.wires, doc.junctions)
    solver = MNASolver(conn.circuit)
    res = solver.solve_dc()

    d1 = conn.circuit.get_component("D1")
    assert isinstance(d1, LED)
    assert d1.color_name == "Red"

    # Hand formula: I = (5.0 - 2.0) / 150.0 = 0.020 A
    expected_i = (5.0 - 2.0) / 150.0
    assert math.isclose(d1.current, expected_i, rel_tol=1e-3, abs_tol=1e-4)
    assert math.isclose(d1.voltage, 2.0, abs_tol=1e-2)
    # Brightness vis = sqrt(I / I_rated) = sqrt(0.02 / 0.02) = 1.0
    assert math.isclose(d1.brightness, 1.0, rel_tol=1e-3)


def test_led_colours_analytical() -> None:
    """Verify 'LED colours' example matches hand calculations across 3 branches.

    Hand calculations:
        Common source: V1 = 5.0 V
        Branch 1 (Red LED):
            Vf_red = 2.0 V, R1 = 150.0 Ω
            I_red = (5.0 - 2.0) / 150.0 = 3.0 / 150.0 = 0.020 A (20.0 mA)
        Branch 2 (Green LED):
            Vf_green = 2.2 V, R2 = 140.0 Ω
            I_green = (5.0 - 2.2) / 140.0 = 2.8 / 140.0 = 0.020 A (20.0 mA)
        Branch 3 (Blue LED):
            Vf_blue = 3.2 V, R3 = 90.0 Ω
            I_blue = (5.0 - 3.2) / 90.0 = 1.8 / 90.0 = 0.020 A (20.0 mA)
        Total supply current:
            I_total = 0.020 + 0.020 + 0.020 = 0.060 A (60.0 mA)
    """
    ex_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "circuitsim"
        / "resources"
        / "examples"
        / "led_colours.circ"
    )
    assert ex_path.exists(), f"File missing: {ex_path}"

    doc = load_document(ex_path)
    conn = extract_connectivity(doc.placed, doc.wires, doc.junctions)
    solver = MNASolver(conn.circuit)
    res = solver.solve_dc()

    d_red = conn.circuit.get_component("D1")
    d_green = conn.circuit.get_component("D2")
    d_blue = conn.circuit.get_component("D3")

    assert isinstance(d_red, LED)
    assert isinstance(d_green, LED)
    assert isinstance(d_blue, LED)

    # Hand formula Branch 1: (5.0 - 2.0) / 150 = 0.020 A
    expected_red = (5.0 - 2.0) / 150.0
    assert math.isclose(d_red.current, expected_red, rel_tol=1e-3, abs_tol=1e-4)
    assert math.isclose(d_red.voltage, 2.0, abs_tol=1e-2)

    # Hand formula Branch 2: (5.0 - 2.2) / 140 = 0.020 A
    expected_green = (5.0 - 2.2) / 140.0
    assert math.isclose(d_green.current, expected_green, rel_tol=1e-3, abs_tol=1e-4)
    assert math.isclose(d_green.voltage, 2.2, abs_tol=1e-2)

    # Hand formula Branch 3: (5.0 - 3.2) / 90 = 0.020 A
    expected_blue = (5.0 - 3.2) / 90.0
    assert math.isclose(d_blue.current, expected_blue, rel_tol=1e-3, abs_tol=1e-4)
    assert math.isclose(d_blue.voltage, 3.2, abs_tol=1e-2)


def _run_qt_script(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=25,
    )


def test_offscreen_led_examples_menu_and_loading() -> None:
    """Offscreen Qt test: verify File > Examples actions load and run cleanly."""
    script = """
import sys
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.show()

# Find the LED example actions in File > Examples
actions = win.examples_menu.actions()
action_titles = [a.text() for a in actions]

assert "LED with a resistor" in action_titles, f"Missing LED with a resistor in {action_titles}"
assert "LED colours" in action_titles, f"Missing LED colours in {action_titles}"

# Trigger "LED with a resistor"
act_res = next(a for a in actions if a.text() == "LED with a resistor")
act_res.trigger()

# Verify components loaded onto scene
comp_names = [item.component.name for item in win.circuit_scene.placed_items]
assert "D1" in comp_names
assert "R1" in comp_names
assert "V1" in comp_names

# Verify circuit solves to 20 mA
import math
from circuitsim.engine.solver import MNASolver

circuit = win.circuit_scene.build_circuit()
solver = MNASolver(circuit)
res = solver.solve_dc()
d1 = circuit.get_component("D1")
assert math.isclose(d1.current, 0.020, rel_tol=1e-3)
win._is_closing = True
win.close()
print("LED_EXAMPLES_MENU_OK")
"""
    res = _run_qt_script(script)
    assert res.returncode == 0, f"Qt subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "LED_EXAMPLES_MENU_OK" in res.stdout
