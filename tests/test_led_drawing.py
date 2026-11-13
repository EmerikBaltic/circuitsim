"""Tests for Item 3: LED Perceptual Glow, Badges, Burnout Drawing, and Tooltips."""

from __future__ import annotations

import math
import subprocess
import sys
import os
import pytest

from circuitsim.components import DCVoltageSource, Ground, LED, Resistor
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.simulation_session import SimulationSession
from circuitsim.engine.solver import MNASolver


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


def test_led_perceptual_glow_mapping_and_cutoffs() -> None:
    """Verify perceptual square root mapping (I_vis = sqrt(I / I_rated)) and 10 uA cutoff."""
    # Rated current = 20 mA (0.02 A)
    # Hand calculations:
    # 1. Below 10 uA cutoff:
    #    I = 5 uA = 5e-6 A < 1e-5 A -> brightness = 0.0
    # 2. At 5 mA (0.005 A):
    #    I_vis = sqrt(0.005 / 0.020) = sqrt(0.25) = 0.50
    # 3. At rated 20 mA (0.020 A):
    #    I_vis = sqrt(0.020 / 0.020) = sqrt(1.0) = 1.00
    # 4. At 35 mA (0.035 A) with max_current = 30 mA:
    #    I_vis = sqrt(0.035 / 0.020) = sqrt(1.75) ≈ 1.322876 -> is_over_current = True
    c = Circuit()
    # 5 V source, 150 ohm resistor, Red LED (Vf = 2.0 V, r_on = 1e-3 ohm)
    # I_expected = (5.0 - 2.0) / 150.0 = 3.0 / 150.0 = 0.020 A = 20 mA
    vs = DCVoltageSource("V1", "1", "0", voltage=5.0)
    r1 = Resistor("R1", "1", "2", resistance=150.0)
    led = LED("D1", "2", "0", forward_voltage=2.0, rated_current=0.02, max_current=0.03)
    c.add(vs)
    c.add(r1)
    c.add(led)
    c.add(Ground("GND", "0"))

    solver = MNASolver(c)
    res = solver.solve_dc()

    assert math.isclose(led.current, 0.020, rel_tol=1e-3)
    assert math.isclose(led.voltage, 2.0, abs_tol=1e-2)
    # sqrt(0.02 / 0.02) = 1.0
    assert math.isclose(led.brightness, 1.0, rel_tol=1e-3)
    assert not led.is_over_current
    assert not led.burned_out

    # Test quarter current (5 mA): R = (5.0 - 2.0) / 0.005 = 600 ohm
    r1.resistance = 600.0
    solver.solve_dc()
    assert math.isclose(led.current, 0.005, rel_tol=1e-3)
    # sqrt(0.005 / 0.02) = 0.5
    assert math.isclose(led.brightness, 0.5, rel_tol=1e-3)

    # Test below 10 uA cutoff: R = 1 MOhm -> I = 3.0 / 1e6 = 3 uA < 10 uA
    r1.resistance = 1e6
    solver.solve_dc()
    assert led.current < 1e-5
    assert led.brightness == 0.0


def test_led_over_current_and_burnout() -> None:
    """Verify amber over-current detection and burnout open-circuit behavior."""
    c = Circuit()
    # 5 V source directly into LED with no resistor (or tiny series resistance)
    vs = DCVoltageSource("V1", "1", "0", voltage=5.0)
    r1 = Resistor("R1", "1", "2", resistance=80.0)  # I = (5-2)/80 = 37.5 mA > 30 mA max
    led = LED(
        "D1",
        "2",
        "0",
        forward_voltage=2.0,
        rated_current=0.02,
        max_current=0.03,
        burnout_enabled=False,
    )
    c.add(vs)
    c.add(r1)
    c.add(led)
    c.add(Ground("GND", "0"))

    solver = MNASolver(c)
    solver.solve_dc()
    # 37.5 mA > 30 mA -> is_over_current is True
    assert math.isclose(led.current, 0.0375, rel_tol=1e-3)
    assert led.is_over_current is True
    assert led.burned_out is False

    # Now enable burnout with threshold = 35 mA
    led.burnout_enabled = True
    led.burnout_current = 0.035
    solver.solve_dc()
    # Current exceeded 35 mA -> burns out!
    assert led.burned_out is True
    assert led.is_conducting is False
    assert led.brightness == 0.0
    assert led.is_over_current is False


def test_led_live_tooltip(qapp) -> None:
    """Verify LED tooltip formatting with colour, voltage, current, and state."""
    from circuitsim.canvas.component_item import ComponentItem
    from circuitsim.canvas.symbol_renderer import SymbolLibrary

    led = LED("D1", "n1", "0", forward_voltage=2.0, color_name="Pure green", color="#00E676")
    item = ComponentItem(led, SymbolLibrary())

    tt_stopped = item.get_live_tooltip(is_running=False)
    assert "Name: D1" in tt_stopped
    assert "Colour: Pure green" in tt_stopped
    assert "Voltage: --" in tt_stopped
    assert "Current: --" in tt_stopped
    assert "State: Off" in tt_stopped

    led.voltage = 2.05
    led.current = 0.020
    led.brightness = 1.0
    tt_running = item.get_live_tooltip(is_running=True)
    assert "Voltage: 2.05 V" in tt_running
    assert "Current: 20 mA" in tt_running
    assert "State: On" in tt_running

    led.is_over_current = True
    tt_over = item.get_live_tooltip(is_running=True)
    assert "State: Over-current" in tt_over

    led.burned_out = True
    tt_burned = item.get_live_tooltip(is_running=True)
    assert "State: Burned out" in tt_burned

    led.burned_out = False
    led.is_over_current = False
    led.voltage = -3.5
    led.current = 0.0
    led.brightness = 0.0
    tt_rev = item.get_live_tooltip(is_running=True)
    assert "State: Reverse-biased" in tt_rev


def test_offscreen_led_drawing_glow_and_burned_out_cross(qapp) -> None:
    """Offscreen Qt test: verify LED rendering, glow painting, burned-out dark body with cross, and diagnostic outlines."""
    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from circuitsim.canvas.component_item import ComponentItem
    from circuitsim.canvas.symbol_renderer import SymbolLibrary

    library = SymbolLibrary()

    led = LED("D1", "n1", "0", forward_voltage=2.0, color_name="Red", color="#FF3B30")
    led.voltage = 2.0
    led.current = 0.020
    led.brightness = 1.0
    item = ComponentItem(led, library)

    img_lit = QImage(120, 80, QImage.Format.Format_ARGB32_Premultiplied)
    img_lit.fill(Qt.GlobalColor.black)
    p = QPainter(img_lit)
    p.translate(60.0, 40.0)
    item.paint(p, None, None)
    p.end()

    arr_lit = np.frombuffer(img_lit.constBits(), dtype=np.uint8).reshape((80, img_lit.bytesPerLine() // 4, 4))
    roi_lit = arr_lit[20:60, 30:90, :]
    lit_pixels = int(np.count_nonzero((roi_lit[:, :, 2] > 80) & (roi_lit[:, :, 1] < 60) & (roi_lit[:, :, 0] < 60)))
    assert lit_pixels > 50, f"Expected red glow pixels, found {lit_pixels}"

    led_burned = LED("D2", "n1", "0", forward_voltage=2.0, burnout_enabled=True)
    led_burned.burned_out = True
    item_burned = ComponentItem(led_burned, library)
    assert item_burned.symbol_state == "burned_out"

    img_burned = QImage(120, 80, QImage.Format.Format_ARGB32_Premultiplied)
    img_burned.fill(Qt.GlobalColor.white)
    p2 = QPainter(img_burned)
    p2.translate(60.0, 40.0)
    item_burned.paint(p2, None, None)
    p2.end()

    arr_b = np.frombuffer(img_burned.constBits(), dtype=np.uint8).reshape((80, img_burned.bytesPerLine() // 4, 4))
    roi_b = arr_b[30:50, 50:70, :]
    dark_pixels = int(np.count_nonzero((roi_b[:, :, 2] < 60) & (roi_b[:, :, 1] < 60) & (roi_b[:, :, 0] < 60)))
    assert dark_pixels > 30, f"Expected dark body pixels in burned out LED, found {dark_pixels}"

    item.set_diagnostic("error", "Error test")
    assert item.diagnostic_severity == "error"

    item.set_diagnostic("warning", "Warning test")
    assert item.diagnostic_severity == "warning"
