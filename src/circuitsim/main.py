"""Entry point for the CircuitSim desktop application.

In Milestone 1, the simulation engine operates headlessly without a Qt UI.
Running this module executes a small DC voltage divider demonstration and
prints the solved node voltages and branch currents to the console.
"""

from __future__ import annotations

from circuitsim.components.ground import Ground
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import DCVoltageSource
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.solver import MNASolver


def run_demo() -> int:
    """Run a quick headless DC demonstration of the Milestone 1 Step A engine."""
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "in", "0", voltage=120.0))
    circuit.add(Ammeter("A1", "in", "mid"))
    circuit.add(Lightbulb("B1", "mid", "0", rated_power=60.0, rated_voltage=120.0))
    circuit.add(Voltmeter("VM1", "mid", "0"))
    circuit.add(Resistor("R_load", "mid", "0", resistance=240.0))
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)
    result = solver.solve_dc()

    print("=== CircuitSim Milestone 1 (Step A) Engine Demo ===")
    print(f"Node 'in' voltage : {result.node_voltages['in']:.4f} V")
    print(f"Node 'mid' voltage: {result.node_voltages['mid']:.4f} V")
    bulb = circuit.get_component("B1")
    ammeter = circuit.get_component("A1")
    voltmeter = circuit.get_component("VM1")
    assert isinstance(bulb, Lightbulb)
    assert isinstance(ammeter, Ammeter)
    assert isinstance(voltmeter, Voltmeter)
    print(f"Ammeter reading   : {ammeter.format_reading()}")
    print(f"Voltmeter reading : {voltmeter.format_reading()}")
    print(f"Bulb resistance   : {bulb.effective_resistance():.2f} Ohm")
    print(f"Bulb brightness   : {bulb.brightness_percent:.1f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
