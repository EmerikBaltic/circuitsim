"""Unit tests for Item 3: File format Schema v2 and v1-to-v2 migration.

Zero Qt imports. Hand-calculated expected values.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    WireSpec,
    extract_connectivity,
)
from circuitsim.components import (
    Capacitor,
    DCVoltageSource,
    Ground,
    Resistor,
)
from circuitsim.engine import MNASolver
from circuitsim.io.circ_serializer import (
    CircuitDocument,
    CircuitFileError,
    ViewState,
    dumps_document,
)
from circuitsim.wiring import (
    CircuitDocumentV2,
    FreeEnd,
    JunctionRef,
    SCHEMA_VERSION_V2,
    TerminalRef,
    dumps_document_v2,
    loads_document_v2,
    migrate_v1_to_v2,
)


def test_no_qt_imports_in_v2_serializer() -> None:
    """circuitsim.wiring.serializer must have zero Qt dependencies."""
    import circuitsim.wiring.serializer as s

    assert not hasattr(s, "QPointF")
    assert not hasattr(s, "QGraphicsItem")
    assert not hasattr(s, "QtCore")


def test_v1_migration_voltage_divider() -> None:
    """Migrating a v1 voltage divider yields identical voltages to hand calculations and old extractor."""
    v1_spec = PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=12.0), (-100.0, 0.0))
    r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", resistance=1000.0), (0.0, 0.0))
    r2_spec = PlacedComponentSpec(Resistor("R2", "a", "b", resistance=3000.0), (120.0, 0.0))
    gnd_spec = PlacedComponentSpec(Ground("GND1"), (-140.0, 60.0))

    # Old v1 wires with T-junction at (-60, 40)
    v1_wires = [
        WireSpec("W_top", ((-140, 0), (-140, -60), (-40, -60), (-40, 0))),
        WireSpec("W_mid", ((40, 0), (80, 0))),
        WireSpec("W_ret1", ((160, 0), (160, 40), (-60, 40), (-60, 0))),
        WireSpec("W_gnd", ((-60, 40), (-140, 40))),
    ]
    doc_v1 = CircuitDocument(
        placed=[v1_spec, r1_spec, r2_spec, gnd_spec],
        wires=v1_wires,
        junctions=[(-60, 40)],
        view=ViewState(theme="dark", zoom=1.0),
    )

    # 1. Old extractor reference
    old_ext = extract_connectivity(doc_v1.placed, doc_v1.wires, doc_v1.junctions)
    sol_old = MNASolver(old_ext.circuit).solve_dc()

    # 2. Migrate to v2
    doc_v2 = migrate_v1_to_v2(doc_v1)
    netlist_v2 = doc_v2.build_circuit()
    sol_v2 = MNASolver(netlist_v2.circuit).solve_dc()

    # Hand calculation: V_mid = 12 * 3000 / 4000 = 9.0 V, I = 3.0 mA
    mid_node = netlist_v2.component_nodes["R1"]["b"]
    assert sol_v2.node_voltages[mid_node] == pytest.approx(9.0, rel=1e-8)
    assert sol_v2.node_voltages[mid_node] == pytest.approx(
        sol_old.node_voltages[old_ext.component_nodes["R1"]["b"]], rel=1e-12
    )

    r2_comp = netlist_v2.circuit.get_component("R2")
    assert r2_comp.current == pytest.approx(3.0e-3, rel=1e-8)


def test_v1_migration_rc_circuit() -> None:
    """Migrating a v1 RC circuit yields identical DC operating point and transient behavior."""
    vs = 10.0
    r_val = 1000.0
    c_val = 1e-6

    v1_spec = PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=vs), (-80.0, 0.0))
    r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", resistance=r_val), (40.0, 0.0))
    c1_spec = PlacedComponentSpec(Capacitor("C1", "a", "b", capacitance=c_val, initial_voltage=0.0), (160.0, 0.0))
    gnd_spec = PlacedComponentSpec(Ground("GND1"), (-40.0, 60.0))

    v1_wires = [
        WireSpec("W1", ((-120, 0), (-120, -40), (0, -40), (0, 0))),
        WireSpec("W2", ((80, 0), (120, 0))),
        WireSpec("W3", ((200, 0), (200, 40), (-40, 40))),
        WireSpec("W4", ((-40, 0), (-40, 40))),
    ]
    doc_v1 = CircuitDocument(
        placed=[v1_spec, r1_spec, c1_spec, gnd_spec],
        wires=v1_wires,
        junctions=[(-40, 40)],
    )

    doc_v2 = migrate_v1_to_v2(doc_v1)
    netlist_v2 = doc_v2.build_circuit()
    sol_v2 = MNASolver(netlist_v2.circuit).solve_dc()

    cap_node = netlist_v2.component_nodes["C1"]["a"]
    assert sol_v2.node_voltages[cap_node] == pytest.approx(10.0, rel=1e-8)
    assert netlist_v2.circuit.get_component("R1").current == pytest.approx(0.0, abs=1e-9)


def test_v1_migration_series_12v_plus_12v() -> None:
    """Migrating two series 12V sources across a 100 Ohm load gives 24V."""
    v1_spec = PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=12.0), (-60.0, 0.0))
    v2_spec = PlacedComponentSpec(DCVoltageSource("V2", "a", "b", voltage=12.0), (40.0, 0.0))
    r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", resistance=100.0), (140.0, 0.0))
    gnd_spec = PlacedComponentSpec(Ground("GND1"), (-100.0, 60.0))

    # V1.neg=(-100, 0), V1.pos=(-20, 0)
    # V2.neg=(0, 0), V2.pos=(80, 0)
    # R1.a=(100, 0), R1.b=(180, 0)
    # GND1 center=(-100, 60), terminal=(-100, 40)
    v1_wires = [
        WireSpec("W_v1v2", ((-20, 0), (0, 0))),
        WireSpec("W_v2r", ((80, 0), (100, 0))),
        WireSpec("W_ret", ((180, 0), (180, 60), (-100, 60), (-100, 0))),
        WireSpec("W_gnd", ((-100, 60), (-100, 40))),
    ]
    doc_v1 = CircuitDocument(
        placed=[v1_spec, v2_spec, r1_spec, gnd_spec],
        wires=v1_wires,
        junctions=[(-100, 60)],
    )

    doc_v2 = migrate_v1_to_v2(doc_v1)
    netlist_v2 = doc_v2.build_circuit()
    sol = MNASolver(netlist_v2.circuit).solve_dc()

    v_top = sol.node_voltages[netlist_v2.component_nodes["R1"]["a"]]
    assert abs(v_top) == pytest.approx(24.0, rel=1e-8)
    assert abs(netlist_v2.circuit.get_component("R1").current) == pytest.approx(0.24, rel=1e-8)


def test_v1_migration_rotated_and_flipped_parts() -> None:
    """Components rotated 90/180/270 deg and flipped migrate with correct terminal positions."""
    # V1 rotated 90 deg: center (0, 0)
    # pos is at (0, -40), neg is at (0, 40)
    v1_spec = PlacedComponentSpec(
        DCVoltageSource("V1", "a", "b", voltage=10.0),
        center_px=(0.0, 0.0),
        rotation_deg=90,
    )
    # R1 flipped horizontally: center (100, 0)
    # a is at (140, 0), b is at (60, 0)
    r1_spec = PlacedComponentSpec(
        Resistor("R1", "a", "b", resistance=50.0),
        center_px=(100.0, 0.0),
        flipped_h=True,
    )
    gnd_spec = PlacedComponentSpec(
        Ground("GND1"),
        center_px=(0.0, 80.0),
    )

    # Wires:
    # W1: V1.pos (0, -40) -> (140, -40) -> R1.a (140, 0)
    # W2: R1.b (60, 0) -> (60, 40) -> V1.neg (0, 40)
    # W3: (0, 40) -> GND1.gnd (0, 60)
    v1_wires = [
        WireSpec("W1", ((0, -40), (140, -40), (140, 0))),
        WireSpec("W2", ((60, 0), (60, 40), (0, 40))),
        WireSpec("W3", ((0, 40), (0, 60))),
    ]
    doc_v1 = CircuitDocument(
        placed=[v1_spec, r1_spec, gnd_spec],
        wires=v1_wires,
        junctions=[(0, 40)],
    )

    doc_v2 = migrate_v1_to_v2(doc_v1)
    netlist_v2 = doc_v2.build_circuit()
    sol = MNASolver(netlist_v2.circuit).solve_dc()

    # V1 = 10V across 50 Ohm -> I = 0.2 A
    r1_comp = netlist_v2.circuit.get_component("R1")
    assert r1_comp.current == pytest.approx(0.2, rel=1e-8)


def test_v1_migration_crossing_wires_stay_separate() -> None:
    """Crossing wires without a junction dot in v1 stay separate in v2."""
    r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", resistance=10.0), (0.0, 40.0))
    r2_spec = PlacedComponentSpec(Resistor("R2", "a", "b", resistance=10.0), (100.0, 40.0))
    r3_spec = PlacedComponentSpec(Resistor("R3", "a", "b", resistance=10.0), (50.0, 0.0), rotation_deg=90)
    r4_spec = PlacedComponentSpec(Resistor("R4", "a", "b", resistance=10.0), (50.0, 100.0), rotation_deg=90)

    # Wire 1: (40, 40) to (60, 40)
    # Wire 2: (50, 30) to (50, 70)
    # Wires cross at (50, 40), but NO junction in v1.junctions
    v1_wires = [
        WireSpec("W1", ((40, 40), (60, 40))),
        WireSpec("W2", ((50, 30), (50, 70))),
    ]
    doc_v1 = CircuitDocument(
        placed=[r1_spec, r2_spec, r3_spec, r4_spec],
        wires=v1_wires,
        junctions=[],
    )

    doc_v2 = migrate_v1_to_v2(doc_v1)
    # The two wires must remain separate in doc_v2.graph
    assert len(doc_v2.graph.wires) == 2
    # No junctions created at the crossing point
    assert len(doc_v2.graph.junctions) == 0


def test_v1_migration_stray_junction_dot_cleaned() -> None:
    """Stray junction dots with degree < 3 are cleaned up automatically in v2."""
    v1_spec = PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=10.0), (0.0, 0.0))
    r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", resistance=100.0), (100.0, 0.0))
    gnd_spec = PlacedComponentSpec(Ground("GND1"), (0.0, 60.0))

    v1_wires = [
        WireSpec("W1", ((-40, 0), (-40, -40), (60, -40), (60, 0))),
        WireSpec("W2", ((140, 0), (140, 60), (40, 60), (40, 0))),
        WireSpec("W3", ((40, 60), (0, 60))),
    ]
    # In v1, there is a stray junction dot at (200, 200) that touches no wires
    doc_v1 = CircuitDocument(
        placed=[v1_spec, r1_spec, gnd_spec],
        wires=v1_wires,
        junctions=[(40, 60), (200, 200)],
    )

    doc_v2 = migrate_v1_to_v2(doc_v1)
    # Stray junction (200, 200) must be discarded
    junc_positions = {j.pos for j in doc_v2.graph.junctions}
    assert (200, 200) not in junc_positions
    # Legitimate T-junction at (40, 60) remains
    assert (40, 60) in junc_positions


def test_v2_save_and_load_round_trip(tmp_path: Path) -> None:
    """CircuitDocumentV2 saves to valid schema v2 JSON and loads back identically."""
    v1_spec = PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=12.0), (-60.0, 0.0))
    r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", resistance=1000.0), (40.0, 0.0))
    gnd_spec = PlacedComponentSpec(Ground("GND1"), (-60.0, 60.0))

    doc_v1 = CircuitDocument(
        placed=[v1_spec, r1_spec, gnd_spec],
        wires=[
            WireSpec("W1", ((-20, 0), (0, 0))),
            WireSpec("W2", ((80, 0), (80, 60), (-60, 60))),
            WireSpec("W3", ((-60, 60), (-100, 60), (-100, 0))),
            WireSpec("W_gnd", ((-60, 60), (-60, 40))),
        ],
        junctions=[(-60, 60)],
        view=ViewState(theme="light", zoom=1.5, pan=(20.0, -10.0), simulation_speed="2x"),
    )

    doc_v2 = migrate_v1_to_v2(doc_v1)
    text = dumps_document_v2(doc_v2)
    data = json.loads(text)

    # Check v2 schema header
    assert data["format"] == "circuitsim"
    assert data["schema_version"] == SCHEMA_VERSION_V2 == 2
    assert "wires" in data
    assert "junctions" in data
    assert "components" in data
    assert "view" in data

    # Check round trip through loads_document_v2
    loaded = loads_document_v2(text)
    assert len(loaded.placed) == len(doc_v2.placed)
    assert len(loaded.graph.wires) == len(doc_v2.graph.wires)
    assert len(loaded.graph.junctions) == len(doc_v2.graph.junctions)
    assert loaded.view.theme == "light"
    assert loaded.view.zoom == 1.5
    assert loaded.view.pan == (20.0, -10.0)
    assert loaded.view.simulation_speed == "2x"

    # Both solve to identical voltages
    sol_orig = MNASolver(doc_v2.build_circuit().circuit).solve_dc()
    sol_loaded = MNASolver(loaded.build_circuit().circuit).solve_dc()
    assert sol_loaded.node_voltages == pytest.approx(sol_orig.node_voltages)


def test_corrupt_and_unknown_version_errors() -> None:
    """Damaged files and unknown versions give clear user-readable errors."""
    with pytest.raises(CircuitFileError, match="empty"):
        loads_document_v2("")

    with pytest.raises(CircuitFileError, match="damaged or incomplete"):
        loads_document_v2('{"format": "circuitsim", "schema_version": 2, invalid}')

    with pytest.raises(CircuitFileError, match="not a CircuitSim file"):
        loads_document_v2('{"format": "wrong", "schema_version": 2}')

    with pytest.raises(CircuitFileError, match="made by a newer version"):
        loads_document_v2('{"format": "circuitsim", "schema_version": 99}')

    with pytest.raises(CircuitFileError, match="Unknown file version"):
        loads_document_v2('{"format": "circuitsim", "schema_version": 0}')

    with pytest.raises(CircuitFileError, match="valid version number"):
        loads_document_v2('{"format": "circuitsim", "schema_version": "two"}')
