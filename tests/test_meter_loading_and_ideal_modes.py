"""Tests for Meter Loading, Ideal/Realistic modes, dialog presets, preferences, and diagnostics."""

from __future__ import annotations

import math
import subprocess
import sys
import pytest

from circuitsim.components.ground import Ground
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import DCCurrentSource, DCVoltageSource
from circuitsim.engine.errors import CircuitWarning, VoltageSourceLoopError
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.solver import MNASolver
from circuitsim.io.circ_serializer import (
    CircuitDocument,
    PlacedComponentSpec,
    dumps_document,
    loads_document,
)


# ----------------------------------------------------------------------
# Part 3a: Hand-Calculated Solver Tests (Pure Python / No Qt)
# ----------------------------------------------------------------------

def test_3a_circuit_without_voltmeter_gives_300v() -> None:
    """30 mA current source into 10 kohm resistor without voltmeter gives 300 V (rel tol 1e-7)."""
    circuit = Circuit()
    circuit.add(Ground("GND", "0"))
    circuit.add(DCCurrentSource("I1", "1", "0", current=30e-3))
    circuit.add(Resistor("R1", "1", "0", resistance=10e3))

    res = MNASolver(circuit).solve_dc()
    v1 = res.node_voltages["1"]
    # Hand calculation: V = 30 mA * 10 kohm = 300.0 V.
    # GMIN (1e-12 S) shunts node 1 to ground, giving (300 V * 1e-12 S) = 300 pA leakage (~1e-8 relative).
    assert math.isclose(v1, 300.0, rel_tol=1e-7)


def test_3a_circuit_with_realistic_voltmeter_loading_gives_299_70v() -> None:
    """30 mA source into 10 kohm resistor with 10 Mohm voltmeter gives 299.70 V.

    Hand check: 10k || 10M = 9990.00999001 ohm => 30 mA * 9990.01 ohm = 299.7003 V.
    """
    circuit = Circuit()
    circuit.add(Ground("GND", "0"))
    circuit.add(DCCurrentSource("I1", "1", "0", current=30e-3))
    circuit.add(Resistor("R1", "1", "0", resistance=10e3))
    circuit.add(Voltmeter("VM1", "1", "0", r_internal=10e6))

    res = MNASolver(circuit).solve_dc()
    vm = circuit.get_component("VM1")
    assert isinstance(vm, Voltmeter)
    expected_v = 30e-3 * (10000.0 * 10e6 / (10000.0 + 10e6))
    assert math.isclose(vm.reading, expected_v, rel_tol=1e-6)
    assert f"{vm.reading:.2f}" == "299.70"


def test_3a_circuit_with_ideal_voltmeter_gives_unloaded_300v() -> None:
    """Ideal voltmeter (is_ideal=True) does not load the circuit and reads 300.0 V."""
    circuit = Circuit()
    circuit.add(Ground("GND", "0"))
    circuit.add(DCCurrentSource("I1", "1", "0", current=30e-3))
    circuit.add(Resistor("R1", "1", "0", resistance=10e3))
    circuit.add(Voltmeter("VM1", "1", "0", is_ideal=True))

    res = MNASolver(circuit).solve_dc()
    vm = circuit.get_component("VM1")
    assert isinstance(vm, Voltmeter)
    assert math.isclose(vm.reading, 300.0, rel_tol=1e-7)
    assert vm.current == 0.0
    assert vm.power == 0.0


def test_3a_series_ammeter_reads_30a() -> None:
    """30 A source with ammeter in series with the source reads 30 A (rel tol 1e-9 at low-potential)."""
    circuit = Circuit()
    circuit.add(Ground("GND", "0"))
    circuit.add(Ammeter("A1", "0", "2", r_internal=1e-3))
    circuit.add(DCCurrentSource("I1", "1", "2", current=30.0))
    circuit.add(Resistor("R1", "1", "0", resistance=10e3))

    res = MNASolver(circuit).solve_dc()
    a1 = circuit.get_component("A1")
    assert isinstance(a1, Ammeter)
    assert math.isclose(a1.reading, 30.0, rel_tol=1e-9)


def test_3a_ammeter_series_with_resistor_and_voltmeter_reads_29_97a() -> None:
    """30 A source with ammeter in series with 10k resistor and 10M voltmeter in parallel reads 29.97 A.

    Current divider: I_A = 30 A * 10M / (10M + 10k) = 29.97003 A.
    """
    circuit = Circuit()
    circuit.add(Ground("GND", "0"))
    circuit.add(DCCurrentSource("I1", "1", "0", current=30.0))
    circuit.add(Ammeter("A1", "1", "2", r_internal=1e-3))
    circuit.add(Resistor("R1", "2", "0", resistance=10e3))
    circuit.add(Voltmeter("VM1", "1", "0", r_internal=10e6))

    res = MNASolver(circuit).solve_dc()
    a1 = circuit.get_component("A1")
    assert isinstance(a1, Ammeter)
    expected_i = 30.0 * 10e6 / (10e6 + 10e3 + 1e-3)
    assert math.isclose(a1.reading, expected_i, rel_tol=1e-6)
    assert f"{a1.reading:.2f}" == "29.97"


def test_3a_ideal_ammeter_acts_as_zero_volt_branch() -> None:
    """Ideal ammeter acts as a 0 V branch with zero voltage drop."""
    circuit = Circuit()
    circuit.add(Ground("GND", "0"))
    circuit.add(DCVoltageSource("V1", "1", "0", voltage=12.0))
    circuit.add(Ammeter("A1", "1", "2", is_ideal=True))
    circuit.add(Resistor("R1", "2", "0", resistance=6.0))

    res = MNASolver(circuit).solve_dc()
    a1 = circuit.get_component("A1")
    assert isinstance(a1, Ammeter)
    assert math.isclose(a1.reading, 2.0, rel_tol=1e-9)
    assert math.isclose(a1.voltage, 0.0, abs_tol=1e-12)


def test_3a_diagnostics_preserved_for_ammeters() -> None:
    """Parallel ammeter warning and ideal ammeter loop error are preserved."""
    # 1. Realistic ammeter directly across voltage source produces warning
    c_warn = Circuit()
    c_warn.add(Ground("GND", "0"))
    c_warn.add(DCVoltageSource("V1", "1", "0", voltage=5.0))
    c_warn.add(Ammeter("A1", "1", "0", r_internal=1e-3, is_ideal=False))
    res_warn = MNASolver(c_warn).solve_dc()
    assert any(w.code == "ammeter_in_parallel" for w in res_warn.warnings)

    # 2. Ideal ammeter directly across voltage source produces ammeter_in_parallel warning
    c_ideal = Circuit()
    c_ideal.add(Ground("GND", "0"))
    c_ideal.add(DCVoltageSource("V1", "1", "0", voltage=5.0, r_internal=0.0))
    c_ideal.add(Ammeter("A1", "1", "0", is_ideal=True))
    res_ideal = MNASolver(c_ideal).solve_dc()
    assert any(w.code == "ammeter_in_parallel" for w in res_ideal.warnings)

    # 3. Voltage source loop check is preserved for ideal voltage source loops
    c_err = Circuit()
    c_err.add(Ground("GND", "0"))
    c_err.add(DCVoltageSource("V1", "1", "0", voltage=5.0, r_internal=0.0))
    c_err.add(DCVoltageSource("V2", "1", "0", voltage=3.0, r_internal=0.0))
    with pytest.raises(VoltageSourceLoopError):
        MNASolver(c_err).solve_dc()


def test_3b_meter_circ_save_load_round_trip() -> None:
    """Ideal and realistic meters round-trip cleanly through .circ JSON."""
    doc = CircuitDocument(
        placed=[
            PlacedComponentSpec(
                component=Voltmeter("VM_ideal", "1", "0", is_ideal=True),
                center_px=(100, 100),
            ),
            PlacedComponentSpec(
                component=Voltmeter("VM_real", "2", "0", r_internal=5e6, is_ideal=False),
                center_px=(200, 100),
            ),
            PlacedComponentSpec(
                component=Ammeter("A_ideal", "3", "4", is_ideal=True),
                center_px=(100, 200),
            ),
            PlacedComponentSpec(
                component=Ammeter("A_real", "5", "6", r_internal=2e-3, is_ideal=False),
                center_px=(200, 200),
            ),
        ]
    )

    serialized = dumps_document(doc)
    loaded_doc = loads_document(serialized)
    comps = {s.component.name: s.component for s in loaded_doc.placed}

    vm_ideal = comps["VM_ideal"]
    assert isinstance(vm_ideal, Voltmeter)
    assert vm_ideal.is_ideal is True

    vm_real = comps["VM_real"]
    assert isinstance(vm_real, Voltmeter)
    assert vm_real.is_ideal is False
    assert math.isclose(vm_real.r_internal, 5e6)

    a_ideal = comps["A_ideal"]
    assert isinstance(a_ideal, Ammeter)
    assert a_ideal.is_ideal is True

    a_real = comps["A_real"]
    assert isinstance(a_real, Ammeter)
    assert a_real.is_ideal is False
    assert math.isclose(a_real.r_internal, 2e-3)


# ----------------------------------------------------------------------
# Part 3b-3d: Offscreen Qt UI Tests (Subprocess with timeout)
# ----------------------------------------------------------------------

def test_3b_3c_3d_offscreen_qt_meter_features() -> None:
    """Verify dialog presets, undo/redo, preferences dialog, and tooltip notices in offscreen Qt."""
    script = """
import sys
import math
import tempfile
from PySide6.QtWidgets import QApplication

from circuitsim.app.settings import AppSettings
from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.components.ground import Ground
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import DCCurrentSource
from circuitsim.dialogs.preferences_dialog import PreferencesDialog
from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.solver import MNASolver

app = QApplication.instance() or QApplication(sys.argv)

# 1. Voltmeter dialog presets & loading notice
vm = Voltmeter("VM1", "1", "0", r_internal=10e6, is_ideal=False)
vm.loading_error_message = (
    "VM1 draws 30 uA from the 10 kohm resistor; the reading is 0.1% lower than the unloaded voltage."
)
applied_map = {}
def on_apply_vm(m, _s):
    applied_map.update(m)

dlg_vm = QuickValueDialog(vm, on_apply=on_apply_vm)
assert dlg_vm.meter_preset_combo is not None
assert dlg_vm.meter_preset_combo.count() == 4
assert dlg_vm.meter_preset_combo.currentText() == "10 Mohm (typical multimeter)"
assert dlg_vm.meter_loading_notice_label is not None
assert dlg_vm.meter_loading_notice_label.text() == (
    "VM1 draws 30 uA from the 10 kohm resistor; the reading is 0.1% lower than the unloaded voltage."
)
# Switch to Ideal
dlg_vm.meter_preset_combo.setCurrentText("Ideal")
assert not dlg_vm.inputs["r_internal"].isEnabled()
assert dlg_vm._apply_current_inputs()
assert applied_map.get("is_ideal") is True

# Switch to 1 Mohm
dlg_vm.meter_preset_combo.setCurrentText("1 Mohm")
assert dlg_vm.inputs["r_internal"].isEnabled()
assert dlg_vm._apply_current_inputs()
assert applied_map.get("is_ideal") is False
assert math.isclose(float(applied_map["r_internal"]), 1e6, rel_tol=1e-3)
dlg_vm.close()

# 2. Ammeter dialog presets
am = Ammeter("A1", "1", "2", r_internal=1e-3, is_ideal=False)
applied_map_am = {}
def on_apply_am(m, _s):
    applied_map_am.update(m)

dlg_am = QuickValueDialog(am, on_apply=on_apply_am)
assert dlg_am.meter_preset_combo is not None
assert dlg_am.meter_preset_combo.currentText() == "1 mohm"
# Switch to Ideal
dlg_am.meter_preset_combo.setCurrentText("Ideal (0 V branch)")
assert not dlg_am.inputs["r_internal"].isEnabled()
assert dlg_am._apply_current_inputs()
assert applied_map_am.get("is_ideal") is True
dlg_am.close()

# 3. Meter Undo / Redo in CircuitScene
scene = CircuitScene(SymbolLibrary())
item = scene.place_new_component("voltmeter", (0, 0))
vm_scene = item.component
assert isinstance(vm_scene, Voltmeter)
assert vm_scene.is_ideal is True
scene.edit_component_parameters(item, {"is_ideal": False, "r_internal": 10e6})
assert vm_scene.is_ideal is False
assert math.isclose(vm_scene.r_internal, 10e6)
scene.undo_stack.undo()
assert vm_scene.is_ideal is True
scene.undo_stack.redo()
assert vm_scene.is_ideal is False
assert math.isclose(vm_scene.r_internal, 10e6)

# 4. Preferences Dialog and Settings
with tempfile.TemporaryDirectory() as tmp_dir:
    settings = AppSettings(data_dir=tmp_dir)
    assert settings.get_new_meters_mode() == "ideal"

    pref = PreferencesDialog(settings)
    assert hasattr(pref, "combo_meters_mode")
    assert pref.combo_meters_mode.currentText() == "Ideal"
    pref.combo_meters_mode.setCurrentText("Realistic")
    pref._on_accept()
    assert settings.get_new_meters_mode() == "realistic"

    # Persistence
    pref2 = PreferencesDialog(settings)
    assert pref2.combo_meters_mode.currentText() == "Realistic"
    pref2.close()

    # Palette placement respects setting
    scene_pref = CircuitScene(SymbolLibrary(), settings=settings)
    vm_real = scene_pref.place_new_component("voltmeter", (0, 0))
    assert vm_real.component.is_ideal is False
    assert math.isclose(vm_real.component.r_internal, 10e6)

# 5. Tooltip and Dialog Loading Notice text
c = Circuit()
c.add(Ground("GND", "0"))
c.add(DCCurrentSource("I1", "1", "0", current=30e-3))
c.add(Resistor("R1", "1", "0", resistance=10e3))
vm_load = Voltmeter("VM1", "1", "0", r_internal=10e6, is_ideal=False)
c.add(vm_load)
MNASolver(c).solve_dc()
expected_msg = (
    "VM1 draws 30 uA from the 10 kohm resistor; the reading is 0.1% lower than the unloaded voltage."
)
assert vm_load.loading_error_message == expected_msg
item_load = ComponentItem(vm_load, SymbolLibrary())
tip = item_load.get_live_tooltip(is_running=True)
assert expected_msg in tip

print("OK")
"""
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "OK" in res.stdout
