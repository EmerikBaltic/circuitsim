"""Script to generate the two LED example circuits and verify their MNA solutions."""

from __future__ import annotations

import json
import math
from pathlib import Path

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    WireSpec,
    extract_connectivity,
)
from circuitsim.components import DCVoltageSource, Ground, LED, Resistor
from circuitsim.engine.solver import MNASolver
from circuitsim.io.circ_serializer import CircuitDocument, dumps_document


def create_led_resistor_example() -> CircuitDocument:
    # 5 V source, 150 ohm resistor, Red LED (Vf = 2.0 V, 20 mA)
    v1 = DCVoltageSource("V1", "1", "0", voltage=5.0)
    r1 = Resistor("R1", "1", "2", resistance=150.0)
    d1 = LED(
        "D1",
        "2",
        "0",
        forward_voltage=2.0,
        rated_current=0.02,
        max_current=0.03,
        color_name="Red",
        color="#FF3B30",
    )
    gnd = Ground("GND1", "0")

    placed = [
        PlacedComponentSpec(component=v1, center_px=(-100.0, 0.0), rotation_deg=90),
        PlacedComponentSpec(component=r1, center_px=(0.0, -40.0), rotation_deg=0),
        PlacedComponentSpec(component=d1, center_px=(100.0, 0.0), rotation_deg=90),
        PlacedComponentSpec(component=gnd, center_px=(-100.0, 60.0), rotation_deg=0),
    ]

    wires = [
        # V1 pos (-100, -40) to R1 a (-40, -40)
        WireSpec(wire_id="W1", points=[(-100.0, -40.0), (-40.0, -40.0)]),
        # R1 b (40, -40) to D1 anode (100, -40)
        WireSpec(wire_id="W2", points=[(40.0, -40.0), (100.0, -40.0)]),
        # D1 cathode (100, 40) to V1 neg (-100, 40)
        WireSpec(wire_id="W3", points=[(100.0, 40.0), (-100.0, 40.0)]),
    ]

    junctions = [(-100.0, 40.0)]
    return CircuitDocument(placed=placed, wires=wires, junctions=junctions)


def create_led_colours_example() -> CircuitDocument:
    # 5 V source with 3 branches (Red: 150 ohm, Green: 140 ohm, Blue: 90 ohm)
    v1 = DCVoltageSource("V1", "vcc", "0", voltage=5.0)
    gnd = Ground("GND1", "0")

    r1 = Resistor("R1", "vcc", "n_r", resistance=150.0)
    d1 = LED(
        "D1",
        "n_r",
        "0",
        forward_voltage=2.0,
        rated_current=0.02,
        color_name="Red",
        color="#FF3B30",
    )

    r2 = Resistor("R2", "vcc", "n_g", resistance=140.0)
    d2 = LED(
        "D2",
        "n_g",
        "0",
        forward_voltage=2.2,
        rated_current=0.02,
        color_name="Green",
        color="#34C759",
    )

    r3 = Resistor("R3", "vcc", "n_b", resistance=90.0)
    d3 = LED(
        "D3",
        "n_b",
        "0",
        forward_voltage=3.2,
        rated_current=0.02,
        color_name="Blue",
        color="#007AFF",
    )

    # Top rail at y = -100, Bottom rail at y = 100
    # R at y = -60 rot=90: terminals at (-60,-100) and (-60,-20)
    # D at y = 60 rot=270: terminals at (anode at -60,20) and (cathode at -60,100)
    placed = [
        PlacedComponentSpec(component=v1, center_px=(-160.0, 0.0), rotation_deg=90),
        PlacedComponentSpec(component=gnd, center_px=(-160.0, 120.0), rotation_deg=0),
        # Branch 1: Red
        PlacedComponentSpec(component=r1, center_px=(-60.0, -60.0), rotation_deg=90),
        PlacedComponentSpec(component=d1, center_px=(-60.0, 60.0), rotation_deg=90),
        # Branch 2: Green
        PlacedComponentSpec(component=r2, center_px=(40.0, -60.0), rotation_deg=90),
        PlacedComponentSpec(component=d2, center_px=(40.0, 60.0), rotation_deg=90),
        # Branch 3: Blue
        PlacedComponentSpec(component=r3, center_px=(140.0, -60.0), rotation_deg=90),
        PlacedComponentSpec(component=d3, center_px=(140.0, 60.0), rotation_deg=90),
    ]

    wires = [
        # V1 pos (-160, -40) up to top rail (-160, -100) and across to (140, -100)
        WireSpec(wire_id="W_v1_top", points=[(-160.0, -40.0), (-160.0, -100.0), (140.0, -100.0)]),
        # V1 neg (-160, 40) down to bottom rail (-160, 100) and across to (140, 100)
        WireSpec(wire_id="W_v1_bot", points=[(-160.0, 40.0), (-160.0, 100.0), (140.0, 100.0)]),
        # Branch 1 middle wire: R1 b (-60, -20) to D1 a (-60, 20)
        WireSpec(wire_id="W_r1_d1", points=[(-60.0, -20.0), (-60.0, 20.0)]),
        # Branch 2 middle wire: R2 b (40, -20) to D2 a (40, 20)
        WireSpec(wire_id="W_r2_d2", points=[(40.0, -20.0), (40.0, 20.0)]),
        # Branch 3 middle wire: R3 b (140, -20) to D3 a (140, 20)
        WireSpec(wire_id="W_r3_d3", points=[(140.0, -20.0), (140.0, 20.0)]),
    ]

    junctions = [
        (-60.0, -100.0),
        (40.0, -100.0),
        (-160.0, 100.0),
        (-60.0, 100.0),
        (40.0, 100.0),
    ]

    return CircuitDocument(placed=placed, wires=wires, junctions=junctions)


def main() -> None:
    ex_dir = (
        Path(__file__).resolve().parent.parent
        / "resources"
        / "examples"
    )

    doc1 = create_led_resistor_example()
    conn1 = extract_connectivity(doc1.placed, doc1.wires, doc1.junctions)
    solver1 = MNASolver(conn1.circuit)
    res1 = solver1.solve_dc()
    d1 = conn1.circuit.get_component("D1")
    print(f"LED with resistor: I_D1 = {d1.current * 1000:.2f} mA, V_D1 = {d1.voltage:.3f} V")
    assert math.isclose(d1.current, 0.020, rel_tol=1e-3)
    (ex_dir / "led_resistor.circ").write_text(dumps_document(doc1), encoding="utf-8")

    doc2 = create_led_colours_example()
    conn2 = extract_connectivity(doc2.placed, doc2.wires, doc2.junctions)
    solver2 = MNASolver(conn2.circuit)
    res2 = solver2.solve_dc()
    d1_col = conn2.circuit.get_component("D1")
    d2_col = conn2.circuit.get_component("D2")
    d3_col = conn2.circuit.get_component("D3")
    print(f"LED colours Red:   I = {d1_col.current * 1000:.2f} mA, V = {d1_col.voltage:.3f} V")
    print(f"LED colours Green: I = {d2_col.current * 1000:.2f} mA, V = {d2_col.voltage:.3f} V")
    print(f"LED colours Blue:  I = {d3_col.current * 1000:.2f} mA, V = {d3_col.voltage:.3f} V")
    assert math.isclose(d1_col.current, 0.020, rel_tol=1e-3)
    assert math.isclose(d2_col.current, 0.020, rel_tol=1e-3)
    assert math.isclose(d3_col.current, 0.020, rel_tol=1e-3)
    (ex_dir / "led_colours.circ").write_text(dumps_document(doc2), encoding="utf-8")
    print("SUCCESS: Both LED example files created and verified!")


if __name__ == "__main__":
    main()
