"""Unit tests for Step 2B connectivity rules, netlist extraction, and QUndoStack editing."""

from __future__ import annotations

import math
import subprocess
import sys
import textwrap

import pytest

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    WireSpec,
    extract_connectivity,
    find_wires_attached_to_components,
    reroute_wires_for_updated_terminals,
    route_orthogonal_wire,
    simplify_orthogonal_points,
)
from circuitsim.components import (
    Capacitor,
    DCVoltageSource,
    Ground,
    Resistor,
)
from circuitsim.engine import Circuit, MNASolver, NoGroundError


from conftest import assert_module_has_no_qt_imports


def test_no_qt_imports_in_connectivity_module() -> None:
    """Rule 4: Verify circuitsim.canvas.connectivity has zero PySide6 imports."""
    assert_module_has_no_qt_imports("circuitsim.canvas.connectivity")


def test_voltage_divider_built_through_extractor_matches_analytic_and_hand_built() -> None:
    """Rule 5: Voltage divider built through extractor matches analytic formula and Milestone 1."""
    v1_spec = PlacedComponentSpec(
        component=DCVoltageSource("V1", "n_a", "n_b", voltage=12.0),
        center_px=(-100.0, 0.0),
    )
    r1_spec = PlacedComponentSpec(
        component=Resistor("R1", "n_a", "n_b", resistance=1000.0),
        center_px=(0.0, 0.0),
    )
    r2_spec = PlacedComponentSpec(
        component=Resistor("R2", "n_a", "n_b", resistance=3000.0),
        center_px=(120.0, 0.0),
    )
    gnd_spec = PlacedComponentSpec(
        component=Ground("GND1"),
        center_px=(-140.0, 60.0),
    )

    wires = [
        WireSpec("W_top", ((-140, 0), (-140, -60), (-40, -60), (-40, 0))),
        WireSpec("W_mid", ((40, 0), (80, 0))),
        WireSpec("W_ret1", ((160, 0), (160, 40), (-60, 40), (-60, 0))),
        WireSpec("W_gnd", ((-60, 40), (-140, 40))),  # T-junction at (-60, 40)
    ]

    extracted = extract_connectivity([v1_spec, r1_spec, r2_spec, gnd_spec], wires)
    sol_extracted = MNASolver(extracted.circuit).solve_dc()

    # Hand-built Milestone 1 reference circuit
    hand_circuit = Circuit()
    hand_circuit.add(DCVoltageSource("V1", "vin", "0", voltage=12.0))
    hand_circuit.add(Resistor("R1", "vin", "vmid", resistance=1000.0))
    hand_circuit.add(Resistor("R2", "vmid", "0", resistance=3000.0))
    hand_circuit.add(Ground("GND1", "0"))
    sol_hand = MNASolver(hand_circuit).solve_dc()

    # Analytic values: V_mid = 12 * 3000 / 4000 = 9.0 V, I = 12 / 4000 = 3.0 mA
    mid_node = extracted.component_nodes["R1"]["b"]
    assert mid_node == extracted.component_nodes["R2"]["a"]
    assert extracted.component_nodes["R2"]["b"] == "0"
    assert extracted.component_nodes["V1"]["neg"] == "0"

    v_mid = sol_extracted.node_voltages[mid_node]
    assert v_mid == pytest.approx(9.0, rel=1e-8)
    assert v_mid == pytest.approx(sol_hand.node_voltages["vmid"], rel=1e-12)

    r2_ext = extracted.circuit.get_component("R2")
    r2_hand = hand_circuit.get_component("R2")
    assert r2_ext.current == pytest.approx(3.0e-3, rel=1e-8)
    assert r2_ext.current == pytest.approx(r2_hand.current, rel=1e-12)
    # T-junction at (-60, 40) must produce a junction dot
    assert (-60, 40) in extracted.junction_dots


def test_rc_transient_built_through_extractor_matches_analytic_and_hand_built() -> None:
    """Rule 5: RC circuit built through extractor matches Vs*(1 - exp(-t/RC)) and hand-built circuit."""
    vs = 10.0
    r_val = 1000.0
    c_val = 1e-6
    tau = r_val * c_val  # 1 ms

    specs = [
        PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=vs), (-80.0, 0.0)),
        PlacedComponentSpec(Resistor("R1", "a", "b", resistance=r_val), (40.0, 0.0)),
        PlacedComponentSpec(
            Capacitor("C1", "a", "b", capacitance=c_val, initial_voltage=0.0),
            (160.0, 0.0),
        ),
        PlacedComponentSpec(Ground("GND1"), (-40.0, 60.0)),
    ]
    wires = [
        WireSpec("W1", ((-120, 0), (-120, -40), (0, -40), (0, 0))),
        WireSpec("W2", ((80, 0), (120, 0))),
        WireSpec("W3", ((200, 0), (200, 40), (-40, 40))),
        WireSpec("W4", ((-40, 0), (-40, 40))),
    ]

    extracted = extract_connectivity(specs, wires)
    solver_ext = MNASolver(extracted.circuit)

    hand = Circuit()
    hand.add(DCVoltageSource("V1", "n_src", "0", voltage=vs))
    hand.add(Resistor("R1", "n_src", "n_cap", resistance=r_val))
    hand.add(Capacitor("C1", "n_cap", "0", capacitance=c_val, initial_voltage=0.0))
    hand.add(Ground("GND1", "0"))
    solver_hand = MNASolver(hand)

    dt = tau / 200.0
    res_ext = solver_ext.solve_transient(duration=5.0 * tau, dt=dt)
    res_hand = solver_hand.solve_transient(duration=5.0 * tau, dt=dt)

    cap_node = extracted.component_nodes["C1"]["a"]
    for k_tau in (1, 2, 5):
        idx = int(round((k_tau * tau) / dt))
        t = res_ext.times[idx]
        v_ext = res_ext.node_voltages[cap_node][idx]
        v_hand = res_hand.node_voltages["n_cap"][idx]
        v_analytic = vs * (1.0 - math.exp(-t / tau))
        assert v_ext == pytest.approx(v_hand, rel=1e-12, abs=1e-12)
        assert v_ext == pytest.approx(v_analytic, rel=2e-3)


def test_crossing_wires_do_not_connect_unless_explicit_junction_or_t_junction() -> None:
    """Rule 1 & 5: Crossing wires do NOT connect; T-junctions and explicit junction dots DO connect."""
    r1 = PlacedComponentSpec(Resistor("R1", "a", "b", 1000.0), (-100.0, 0.0))
    r2 = PlacedComponentSpec(Resistor("R2", "a", "b", 1000.0), (100.0, 0.0))
    r3 = PlacedComponentSpec(
        Resistor("R3", "a", "b", 1000.0), (0.0, -100.0), rotation_deg=90
    )
    r4 = PlacedComponentSpec(
        Resistor("R4", "a", "b", 1000.0), (0.0, 100.0), rotation_deg=90
    )

    w_horiz = WireSpec("W_horiz", ((-60, 0), (60, 0)))
    w_vert = WireSpec("W_vert", ((0, -60), (0, 60)))

    # 1. Pure crossing without junction dot: must NOT connect
    res_cross = extract_connectivity([r1, r2, r3, r4], [w_horiz, w_vert])
    assert res_cross.wire_to_node["W_horiz"] != res_cross.wire_to_node["W_vert"]
    assert res_cross.component_nodes["R1"]["b"] == res_cross.component_nodes["R2"]["a"]
    assert res_cross.component_nodes["R3"]["b"] == res_cross.component_nodes["R4"]["a"]
    assert res_cross.component_nodes["R1"]["b"] != res_cross.component_nodes["R3"]["b"]
    assert (0, 0) not in res_cross.junction_dots

    # 2. Place an explicit junction dot at (0, 0): now they MUST connect
    res_junc = extract_connectivity(
        [r1, r2, r3, r4], [w_horiz, w_vert], explicit_junctions=[(0, 0)]
    )
    assert res_junc.wire_to_node["W_horiz"] == res_junc.wire_to_node["W_vert"]
    assert res_junc.component_nodes["R1"]["b"] == res_junc.component_nodes["R3"]["b"]
    assert (0, 0) in res_junc.junction_dots

    # 3. T-junction: W_stem starts at (0, 0) (on the interior of W_horiz) and goes to (0, 60)
    w_stem = WireSpec("W_stem", ((0, 0), (0, 60)))
    res_t = extract_connectivity([r1, r2, r4], [w_horiz, w_stem])
    assert res_t.wire_to_node["W_horiz"] == res_t.wire_to_node["W_stem"]
    assert res_t.component_nodes["R1"]["b"] == res_t.component_nodes["R4"]["a"]
    assert (0, 0) in res_t.junction_dots


def test_wire_passing_through_terminal_without_ending_does_not_connect() -> None:
    """Rule 1: A wire end connects to a terminal only if it sits on it."""
    r1 = PlacedComponentSpec(Resistor("R1", "a", "b", 1000.0), (0.0, 0.0))
    w_pass = WireSpec("W_pass", ((-100, 0), (100, 0)))

    res = extract_connectivity([r1], [w_pass])
    assert res.component_nodes["R1"]["a"] != res.wire_to_node["W_pass"]
    assert res.component_nodes["R1"]["b"] != res.wire_to_node["W_pass"]


def test_zero_length_duplicate_and_overlapping_wires_no_phantom_connections() -> None:
    """Rule 3: Zero-length, duplicate, and collinear overlapping wires create no phantom connections."""
    r1 = PlacedComponentSpec(Resistor("R1", "a", "b", 1000.0), (-100.0, 0.0))
    r2 = PlacedComponentSpec(Resistor("R2", "a", "b", 1000.0), (100.0, 0.0))

    wires = [
        WireSpec("W_zero1", ((0, 0), (0, 0))),
        WireSpec("W_zero2", ((0, 0), (20, 0), (0, 0))),  # Foldback zero-length
        WireSpec("W_h1", ((-60, 0), (20, 0))),
        WireSpec("W_h2_overlap", ((-20, 0), (60, 0))),  # Collinear overlap with W_h1
        WireSpec("W_h1_dup", ((20, 0), (-60, 0))),  # Reversed duplicate of W_h1
        WireSpec("W_vert_cross", ((0, -60), (0, 60))),  # Crosses at (0, 0)
    ]

    res = extract_connectivity([r1, r2], wires)
    assert res.component_nodes["R1"]["b"] == res.component_nodes["R2"]["a"]
    assert res.wire_to_node["W_h1"] == res.wire_to_node["W_h2_overlap"]
    assert res.wire_to_node["W_h1_dup"] == res.wire_to_node["W_h1"]
    assert res.wire_to_node["W_vert_cross"] != res.wire_to_node["W_h1"]
    assert "W_zero1" not in res.wire_to_node
    assert "W_zero2" not in res.wire_to_node

    # Also test find_wires_attached_to_components in pure Python
    from circuitsim.canvas.symbol_geometry import (
        DEFAULT_IEC_SYMBOLS_DIR,
        load_all_iec_metadata,
    )

    cat = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
    terms = {"R1": r1.resolve_terminals_px(cat), "R2": r2.resolve_terminals_px(cat)}
    attached_r1 = find_wires_attached_to_components(terms, {"R1"}, wires)
    assert "W_h1" in attached_r1
    assert "W_vert_cross" not in attached_r1


def test_rotate_and_flip_component_keeps_terminals_and_reroutes_wires() -> None:
    """Rule 2 & 5: Rotating or flipping a component updates terminals and re-routes attached wires."""
    v1_normal = PlacedComponentSpec(
        DCVoltageSource("V1", "pos", "neg", voltage=5.0),
        center_px=(0.0, 0.0),
        rotation_deg=0,
        flipped_h=False,
    )
    v1_flipped = PlacedComponentSpec(
        DCVoltageSource("V1", "pos", "neg", voltage=5.0),
        center_px=(0.0, 0.0),
        rotation_deg=0,
        flipped_h=True,
    )
    r1 = PlacedComponentSpec(
        Resistor("R1", "a", "b", resistance=1000.0),
        center_px=(0.0, -60.0),
    )
    gnd = PlacedComponentSpec(Ground("GND1"), center_px=(40.0, 40.0))

    wires = [
        WireSpec("W_left", ((-40, 0), (-40, -60))),
        WireSpec("W_right", ((40, 0), (40, -60))),
        WireSpec("W_gnd", ((40, 0), (40, 20))),
    ]

    ext_normal = extract_connectivity([v1_normal, r1, gnd], wires)
    sol_normal = MNASolver(ext_normal.circuit).solve_dc()
    left_node_norm = ext_normal.component_nodes["R1"]["a"]
    assert sol_normal.node_voltages[left_node_norm] == pytest.approx(5.0, abs=1e-9)

    ext_flipped = extract_connectivity([v1_flipped, r1, gnd], wires)
    sol_flipped = MNASolver(ext_flipped.circuit).solve_dc()
    left_node_flip = ext_flipped.component_nodes["R1"]["a"]
    assert sol_flipped.node_voltages[left_node_flip] == pytest.approx(-5.0, abs=1e-9)

    r1_rot90 = PlacedComponentSpec(
        Resistor("R1", "a", "b", resistance=1000.0),
        center_px=(0.0, -60.0),
        rotation_deg=90,
    )
    from circuitsim.canvas.symbol_geometry import (
        DEFAULT_IEC_SYMBOLS_DIR,
        load_all_iec_metadata,
    )

    cat = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
    old_terms = {"R1": r1.resolve_terminals_px(cat)}
    new_terms = {"R1": r1_rot90.resolve_terminals_px(cat)}
    rerouted = reroute_wires_for_updated_terminals(old_terms, new_terms, wires)

    assert rerouted["W_left"][0] == (-40, 0)
    assert rerouted["W_left"][-1] == (0, -100)
    assert rerouted["W_right"][0] == (40, 0)
    assert rerouted["W_right"][-1] == (0, -20)
    for wid in ("W_left", "W_right"):
        pts = rerouted[wid]
        for i in range(len(pts) - 1):
            assert pts[i][0] == pts[i + 1][0] or pts[i][1] == pts[i + 1][1]


def test_missing_ground_raises_no_ground_connected() -> None:
    """Rule 5: A circuit extracted without a Ground component produces 'No ground connected'."""
    v1 = PlacedComponentSpec(DCVoltageSource("V1", "pos", "neg", 9.0), (0.0, 0.0))
    r1 = PlacedComponentSpec(Resistor("R1", "a", "b", 1000.0), (0.0, -60.0))
    wires = [
        WireSpec("W1", ((-40, 0), (-40, -60))),
        WireSpec("W2", ((40, 0), (40, -60))),
    ]
    extracted = extract_connectivity([v1, r1], wires)
    with pytest.raises(NoGroundError, match="No ground connected"):
        MNASolver(extracted.circuit).solve_dc()


def test_undo_redo_and_attached_wire_deletion_in_circuit_scene(qapp) -> None:
    """Rules 2, 5, 6: Full QUndoStack undo/redo for add, wire, move, rotate, flip, delete, copy/paste."""
    from PySide6.QtCore import QPointF
    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.canvas.symbol_renderer import SymbolLibrary
    from circuitsim.engine import MNASolver

    scene = CircuitScene(SymbolLibrary())

    # 1. Place V1 (12 V), R1 (1 kOhm), GND1
    scene.place_new_component("dc_voltage", QPointF(0.0, 0.0))
    r1_item = scene.place_new_component("resistor", QPointF(0.0, -60.0))
    scene.place_new_component("ground", QPointF(40.0, 40.0))
    assert len(scene.placed_items) == 3

    # 2. Wire them up
    w1 = scene.add_routed_wire((-40, 0), (-40, -60))
    w2 = scene.add_routed_wire((40, 0), (40, -60))
    w3 = scene.add_routed_wire((40, 0), (40, 20))
    assert len(scene.placed_wires) == 3

    c_init = scene.build_circuit()
    sol_init = MNASolver(c_init).solve_dc()
    assert math.isclose(abs(c_init.get_component("R1").current), 0.012, rel_tol=1e-7)

    # 3. Move R1 up by 40 px: attached wires w1 and w2 re-route automatically and keep connectivity
    scene.move_components_by([r1_item], 0.0, -40.0)
    assert r1_item.pos() == QPointF(0.0, -100.0)
    assert w1.points[-1] == (-40, -100)
    assert w2.points[-1] == (40, -100)
    c_moved = scene.build_circuit()
    MNASolver(c_moved).solve_dc()
    assert math.isclose(abs(c_moved.get_component("R1").current), 0.012, rel_tol=1e-7)

    # Undo move -> R1 and wires return to (-60), Redo -> back to (-100)
    scene.undo_stack.undo()
    assert r1_item.pos() == QPointF(0.0, -60.0)
    assert w1.points[-1] == (-40, -60)
    scene.undo_stack.redo()
    assert r1_item.pos() == QPointF(0.0, -100.0)
    scene.undo_stack.undo()

    # 4. Rotate and Flip R1 with Undo/Redo
    scene.clearSelection()
    r1_item.setSelected(True)
    scene.rotate_selected()
    assert r1_item.rotation_deg == 90
    scene.undo_stack.undo()
    assert r1_item.rotation_deg == 0

    scene.flip_selected()
    assert r1_item.flipped_h is True
    scene.undo_stack.undo()
    assert r1_item.flipped_h is False

    # 5. Delete R1 -> also deletes attached wires w1 and w2 (Rule 2)
    scene.clearSelection()
    r1_item.setSelected(True)
    scene.delete_selected()
    assert len(scene.placed_items) == 2
    assert len(scene.placed_wires) == 1
    assert scene.placed_wires[0] is w3

    # Undo delete -> restores R1 AND attached wires w1 and w2 with identical solved voltages
    scene.undo_stack.undo()
    assert len(scene.placed_items) == 3
    assert len(scene.placed_wires) == 3
    c_restored = scene.build_circuit()
    sol_restored = MNASolver(c_restored).solve_dc()
    for k, v in sol_init.node_voltages.items():
        assert math.isclose(sol_restored.node_voltages[k], v, rel_tol=1e-12, abs_tol=1e-12)

    # 6. Copy / Paste R1 -> adds R2, Undo removes R2
    scene.clearSelection()
    r1_item.setSelected(True)
    assert scene.copy_selected() is True
    assert scene.paste_clipboard(offset_px=(80.0, 0.0)) is True
    assert len(scene.placed_items) == 4
    scene.undo_stack.undo()
    assert len(scene.placed_items) == 3
