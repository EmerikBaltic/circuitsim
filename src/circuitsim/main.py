"""Entry point for the CircuitSim desktop application.

Usage:
    # Launch the interactive PySide6 desktop schematic editor:
    python -m circuitsim.main

    # Run the headless Milestone 1 CLI simulation demo:
    python -m circuitsim.main --demo
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QPointF

from circuitsim.components import (
    ACVoltageSource,
    Ammeter,
    Capacitor,
    DCVoltageSource,
    Ground,
    Inductor,
    Lightbulb,
    MeterMode,
    Resistor,
    Voltmeter,
    WaveformType,
)
from circuitsim.engine import Circuit, MNASolver


def run_demo() -> int:
    """Run a quick headless DC and Transient demonstration of the Milestone 1 engine."""
    dc_circuit = Circuit()
    dc_circuit.add(DCVoltageSource("V1", "in", "0", voltage=120.0))
    dc_circuit.add(Ammeter("A1", "in", "mid"))
    dc_circuit.add(Lightbulb("B1", "mid", "0", rated_power=60.0, rated_voltage=120.0))
    dc_circuit.add(Voltmeter("VM1", "mid", "0"))
    dc_circuit.add(Resistor("R_load", "mid", "0", resistance=240.0))
    dc_circuit.add(Ground("GND", "0"))

    dc_solver = MNASolver(dc_circuit)
    dc_result = dc_solver.solve_dc()

    print("=== CircuitSim Milestone 1 Engine Demo ===")
    print("[DC Operating Point]")
    print(f"  Node 'in' voltage : {dc_result.node_voltages['in']:.4f} V")
    print(f"  Node 'mid' voltage: {dc_result.node_voltages['mid']:.4f} V")
    bulb = dc_circuit.get_component("B1")
    ammeter = dc_circuit.get_component("A1")
    voltmeter = dc_circuit.get_component("VM1")
    assert isinstance(bulb, Lightbulb)
    assert isinstance(ammeter, Ammeter)
    assert isinstance(voltmeter, Voltmeter)
    print(f"  Ammeter reading   : {ammeter.format_reading()}")
    print(f"  Voltmeter reading : {voltmeter.format_reading()}")
    print(f"  Bulb resistance   : {bulb.effective_resistance():.2f} Ohm")
    print(f"  Bulb brightness   : {bulb.brightness_percent:.1f} %")

    ac_circuit = Circuit()
    ac_circuit.add(
        ACVoltageSource(
            "Vac",
            "src",
            "0",
            waveform=WaveformType.SINE,
            amplitude=10.0,
            frequency=1000.0,
        )
    )
    ac_ammeter = Ammeter("A_ac", "src", "load", mode=MeterMode.RMS, window_duration=0.004)
    ind = Inductor("L1", "load", "0", inductance="10m", dcr=10.0)
    cap = Capacitor("C_bypass", "load", "0", capacitance="100n")
    ac_voltmeter = Voltmeter("VM_ac", "load", "0", mode=MeterMode.RMS, window_duration=0.004)
    ac_circuit.add(ac_ammeter)
    ac_circuit.add(ind)
    ac_circuit.add(cap)
    ac_circuit.add(ac_voltmeter)
    ac_circuit.add(Ground("GND", "0"))

    tr_solver = MNASolver(ac_circuit)
    tr_res = tr_solver.solve_transient(duration=0.01, dt=5e-6)
    print("\n[Transient AC Analysis -- 1 kHz Sine into Parallel RL/C Load]")
    print(f"  Steps executed    : {tr_res.step_count}")
    print(f"  LU factorizations : {tr_res.matrix_rebuild_count}")
    print(f"  Inductor X_L      : {ind.reactance(1000.0):.2f} Ohm")
    print(f"  AC Voltmeter (RMS): {ac_voltmeter.format_reading()}")
    print(f"  AC Ammeter (RMS)  : {ac_ammeter.format_reading()}")
    return 0


def run_gui() -> int:
    """Launch the interactive PySide6 desktop main window."""
    from PySide6.QtWidgets import QApplication
    from circuitsim.app.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()

    # Place a few sample IEC components on the grid so the user can immediately
    # see and interact with the schematic canvas on launch.
    scene = window.circuit_scene
    scene.place_new_component("dc_voltage", QPointF(-160.0, -40.0))
    scene.place_new_component("switch", QPointF(-40.0, -40.0))
    scene.place_new_component("resistor", QPointF(80.0, -40.0))
    scene.place_new_component("lightbulb", QPointF(200.0, -40.0))
    scene.place_new_component("ground", QPointF(0.0, 60.0))

    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CircuitSim Desktop Application")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the headless CLI simulation demo and exit.",
    )
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
