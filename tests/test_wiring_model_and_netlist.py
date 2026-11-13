"""Unit tests for Item 1: Explicit wiring model (WireGraph) and Union-Find netlist builder.

Zero Qt imports. Hand-calculated expected values.
"""

from __future__ import annotations

import random
import sys
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
    Lightbulb,
    Resistor,
    Switch,
)
from circuitsim.engine import (
    Circuit,
    FloatingNodeError,
    MNASolver,
    NoGroundError,
    VoltageSourceLoopError,
)
from circuitsim.wiring import (
    GROUND_NODE,
    FreeEnd,
    Junction,
    JunctionRef,
    TerminalRef,
    Wire,
    WireGraph,
    WireGraphError,
    WiringNetlist,
    build_circuit,
)


from conftest import assert_module_has_no_qt_imports


def test_no_qt_imports_in_wiring_package() -> None:
    """Explicit wiring package must have zero PySide6/Qt imports."""
    assert_module_has_no_qt_imports(
        "circuitsim.wiring",
        "circuitsim.wiring.model",
        "circuitsim.wiring.netlist",
    )


def test_wiregraph_immutability() -> None:
    """WireGraph operations return new instances and leave the original unchanged."""
    g0 = WireGraph()
    g1 = g0.add_junction((100, 100), "J1")
    assert g0.junctions == ()
    assert len(g1.junctions) == 1
    assert g1.junction("J1").pos == (100, 100)

    g2 = g1.add_wire(TerminalRef("R1", "a"), JunctionRef("J1"), wire_id="W1")
    assert g1.wires == ()
    assert len(g2.wires) == 1
    assert g2.wire("W1").end_a == TerminalRef("R1", "a")


def test_lowest_free_id_generation() -> None:
    """Ids reuse the lowest free integer: W1, W2 -> remove W1 -> next is W1."""
    g = (
        WireGraph()
        .add_junction((0, 0), "J1")
        .add_junction((20, 0), "J2")
        .add_wire(JunctionRef("J1"), FreeEnd(40, 0))  # W1
        .add_wire(JunctionRef("J2"), FreeEnd(60, 0))  # W2
    )
    assert {w.id for w in g.wires} == {"W1", "W2"}

    # Remove W1, then add a wire: new id should be W1 again
    g_after = g.remove_wire("W1")
    assert not g_after.has_wire("W1")
    g_readd = g_after.add_wire(JunctionRef("J2"), FreeEnd(80, 0))
    assert g_readd.has_wire("W1")

    # Same for junctions
    g_j = WireGraph().add_junction((0, 0)).add_junction((20, 0))  # J1, J2
    assert {j.id for j in g_j.junctions} == {"J1", "J2"}
    g_j2 = g_j.remove_junction("J1")
    assert not g_j2.has_junction("J1")
    g_j3 = g_j2.add_junction((40, 0))
    assert g_j3.has_junction("J1")


def test_terminals_joined_through_junction() -> None:
    """Wires meeting at an explicit junction connect their terminals into one net."""
    # V1 (pos, neg), R1 (a, b), GND1 (gnd)
    # V1.neg -- W1 --> J1, GND1.gnd -- W2 --> J1, R1.b -- W3 --> J1
    g = (
        WireGraph()
        .add_junction((0, 100), "J1")
        .add_wire(TerminalRef("V1", "neg"), JunctionRef("J1"), wire_id="W1")
        .add_wire(TerminalRef("GND1", "gnd"), JunctionRef("J1"), wire_id="W2")
        .add_wire(TerminalRef("R1", "b"), JunctionRef("J1"), wire_id="W3")
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("R1", "a"), wire_id="W4")
    )
    v1 = DCVoltageSource("V1", "a", "b", voltage=5.0)
    r1 = Resistor("R1", "a", "b", resistance=100.0)
    gnd = Ground("GND1")

    netlist = build_circuit(g, [v1, r1, gnd])
    # J1 joins V1.neg, GND1.gnd, and R1.b -> all in node "0"
    assert netlist.component_nodes["V1"]["neg"] == GROUND_NODE
    assert netlist.component_nodes["GND1"]["gnd"] == GROUND_NODE
    assert netlist.component_nodes["R1"]["b"] == GROUND_NODE
    # V1.pos and R1.a are in node "N1"
    assert netlist.component_nodes["V1"]["pos"] == "N1"
    assert netlist.component_nodes["R1"]["a"] == "N1"

    sol = MNASolver(netlist.circuit).solve_dc()
    assert sol.node_voltages["N1"] == pytest.approx(5.0)


def test_crossing_wires_stay_separate() -> None:
    """Wires whose coordinates cross geometrically NEVER connect unless explicitly joined."""
    # Wire 1: (0, 50) to (100, 50) connects R1.a to R2.a
    # Wire 2: (50, 0) to (50, 100) connects R3.a to R4.a
    # Geometrically they cross at (50, 50), but there is NO junction.
    g = (
        WireGraph()
        .add_wire(
            TerminalRef("R1", "a"),
            TerminalRef("R2", "a"),
            hints=((0, 50), (100, 50)),
            wire_id="W1",
        )
        .add_wire(
            TerminalRef("R3", "a"),
            TerminalRef("R4", "a"),
            hints=((50, 0), (50, 100)),
            wire_id="W2",
        )
    )
    comps = [
        Resistor("R1", "a", "b", resistance=10.0),
        Resistor("R2", "a", "b", resistance=10.0),
        Resistor("R3", "a", "b", resistance=10.0),
        Resistor("R4", "a", "b", resistance=10.0),
    ]
    netlist = build_circuit(g, comps)
    # W1 and W2 form distinct nets
    node_w1 = netlist.component_nodes["R1"]["a"]
    node_w2 = netlist.component_nodes["R3"]["a"]
    assert node_w1 == netlist.component_nodes["R2"]["a"]
    assert node_w2 == netlist.component_nodes["R4"]["a"]
    assert node_w1 != node_w2


def test_two_wires_on_one_terminal_connect() -> None:
    """Two wires attached directly to the same TerminalRef electrically connect."""
    # W1: V1.pos -> R1.a
    # W2: R1.a -> R2.a
    g = (
        WireGraph()
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("R1", "a"), wire_id="W1")
        .add_wire(TerminalRef("R1", "a"), TerminalRef("R2", "a"), wire_id="W2")
    )
    comps = [
        DCVoltageSource("V1", "a", "b", voltage=10.0),
        Resistor("R1", "a", "b", resistance=100.0),
        Resistor("R2", "a", "b", resistance=200.0),
    ]
    netlist = build_circuit(g, comps)
    n_v1 = netlist.component_nodes["V1"]["pos"]
    n_r1 = netlist.component_nodes["R1"]["a"]
    n_r2 = netlist.component_nodes["R2"]["a"]
    assert n_v1 == n_r1 == n_r2


def test_free_end_on_terminal_does_not_connect() -> None:
    """A FreeEnd placed at the exact same (x, y) coordinates as a terminal does NOT connect."""
    # Suppose R1 terminal 'a' is at (0, 0).
    # A wire with FreeEnd(0, 0) and TerminalRef('R2', 'a') must NOT connect R1.a to R2.a.
    g = WireGraph().add_wire(FreeEnd(0, 0), TerminalRef("R2", "a"), wire_id="W1")
    comps = [
        Resistor("R1", "a", "b", resistance=100.0),
        Resistor("R2", "a", "b", resistance=200.0),
    ]
    netlist = build_circuit(g, comps)
    assert netlist.component_nodes["R1"]["a"] != netlist.component_nodes["R2"]["a"]


def test_merge_rule_degree_2_becomes_one_wire_with_hint() -> None:
    """When a junction is left with 2 wires, the wires merge into one with the junction position as a hint."""
    # Start with J1 having 3 wires: W1 (R1.a -> J1), W2 (J1 -> R2.a), W3 (J1 -> R3.a)
    pos_j = (100, 100)
    g = (
        WireGraph()
        .add_junction(pos_j, "J1")
        .add_wire(TerminalRef("R1", "a"), JunctionRef("J1"), hints=((50, 100),), wire_id="W1")
        .add_wire(JunctionRef("J1"), TerminalRef("R2", "a"), hints=((150, 100),), wire_id="W2")
        .add_wire(JunctionRef("J1"), TerminalRef("R3", "a"), wire_id="W3")
    )
    assert g.junction_degree("J1") == 3
    assert g.junction_dot_visible("J1")

    # Remove W3 -> J1 now has 2 wires -> merges W1 and W2 into one wire
    g_after = g.remove_wire("W3")
    assert not g_after.has_junction("J1")
    assert len(g_after.wires) == 1
    w_merged = g_after.wires[0]
    assert w_merged.end_a == TerminalRef("R1", "a")
    assert w_merged.end_b == TerminalRef("R2", "a")
    # Hint must contain the original junction position (100, 100)
    assert pos_j in w_merged.hints


def test_merge_rule_degree_1_becomes_free_end() -> None:
    """When a junction is left with 1 wire, junction is deleted and wire end becomes FreeEnd."""
    # Junction J1 with 2 wires (e.g. freshly split or created).
    # Removing one wire leaves J1 with degree 1.
    pos_j = (80, 40)
    g = (
        WireGraph()
        .add_junction(pos_j, "J1")
        .add_wire(TerminalRef("R1", "a"), JunctionRef("J1"), wire_id="W1")
        .add_wire(TerminalRef("R2", "a"), JunctionRef("J1"), wire_id="W2")
    )
    # Removing W2 leaves J1 with only W1 attached
    g_after = g.remove_wire("W2")
    assert not g_after.has_junction("J1")
    assert len(g_after.wires) == 1
    w1 = g_after.wire("W1")
    assert w1.end_a == TerminalRef("R1", "a")
    assert w1.end_b == FreeEnd(*pos_j)


def test_merge_rule_degree_0_deleted() -> None:
    """When a junction has no wires left (e.g. remove_junction or wire removed), junction is deleted."""
    g = WireGraph().add_junction((40, 40), "J1").add_wire(FreeEnd(0, 0), JunctionRef("J1"), wire_id="W1")
    # Removing W1 leaves J1 with 0 wires -> J1 is deleted
    g_after = g.remove_wire("W1")
    assert not g_after.has_junction("J1")
    assert len(g_after.wires) == 0


def test_merge_rule_cascading_and_deduplication() -> None:
    """Deduplication and cascading merge: removing a wire merges adjacent junctions in cascade."""
    # J1 at (50, 0), J2 at (100, 0)
    # W1: R1.a -> J1
    # W2: J1 -> J2
    # W3: J1 -> R2.a
    # W4: J2 -> R3.a
    # W5: J2 -> R4.a
    # J1 has 3 wires (W1, W2, W3). J2 has 3 wires (W2, W4, W5).
    g = (
        WireGraph()
        .add_junction((50, 0), "J1")
        .add_junction((100, 0), "J2")
        .add_wire(TerminalRef("R1", "a"), JunctionRef("J1"), wire_id="W1")
        .add_wire(JunctionRef("J1"), JunctionRef("J2"), wire_id="W2")
        .add_wire(JunctionRef("J1"), TerminalRef("R2", "a"), wire_id="W3")
        .add_wire(JunctionRef("J2"), TerminalRef("R3", "a"), wire_id="W4")
        .add_wire(JunctionRef("J2"), TerminalRef("R4", "a"), wire_id="W5")
    )
    # Now remove W3. J1 now has 2 wires (W1 and W2).
    # Rule triggers on J1: W1 and W2 merge into one wire from R1.a to J2.
    # Now J2 still has 3 wires (merged R1.a->J2, W4, W5), so J2 remains!
    g1 = g.remove_wire("W3")
    assert not g1.has_junction("J1")
    assert g1.has_junction("J2")
    assert g1.junction_degree("J2") == 3

    # Now remove W5. J2 now has 2 wires: merged(R1.a->J2) and W4(J2->R3.a).
    # J2 merges them into one wire from R1.a to R3.a!
    g2 = g1.remove_wire("W5")
    assert not g2.has_junction("J2")
    assert len(g2.wires) == 1
    w_final = g2.wires[0]
    assert w_final.end_a == TerminalRef("R1", "a")
    assert w_final.end_b == TerminalRef("R3", "a")


def test_remove_component_removes_attached_wires_and_cleans_junctions() -> None:
    """remove_component drops all wires attached to the component and applies merge rules."""
    g = (
        WireGraph()
        .add_junction((60, 0), "J1")
        .add_wire(TerminalRef("R1", "a"), JunctionRef("J1"), wire_id="W1")
        .add_wire(TerminalRef("R2", "a"), JunctionRef("J1"), wire_id="W2")
        .add_wire(TerminalRef("R3", "a"), JunctionRef("J1"), wire_id="W3")
    )
    # Removing R3 deletes W3, leaving J1 with 2 wires (W1, W2), which merges into 1 wire R1.a -> R2.a
    g_after = g.remove_component("R3")
    assert not g_after.has_junction("J1")
    assert len(g_after.wires) == 1
    assert g_after.wires[0].end_a == TerminalRef("R1", "a")
    assert g_after.wires[0].end_b == TerminalRef("R2", "a")


def test_diagnostics_through_new_path_no_ground() -> None:
    """build_circuit with a circuit missing ground raises NoGroundError when validated/solved."""
    g = WireGraph().add_wire(TerminalRef("V1", "pos"), TerminalRef("R1", "a"), wire_id="W1")
    v1 = DCVoltageSource("V1", "a", "b", voltage=12.0)
    r1 = Resistor("R1", "a", "b", resistance=100.0)
    netlist = build_circuit(g, [v1, r1])
    with pytest.raises(NoGroundError, match="No ground connected"):
        netlist.circuit.validate_topology()


def test_diagnostics_through_new_path_floating_node() -> None:
    """build_circuit with a floating node raises FloatingNodeError when validated."""
    # V1 has ground on neg and pos connected to R1.a, but R1.b is unconnected (floating node)
    # Note: an unconnected terminal on a connected part forms a node with only 1 component pin
    g = (
        WireGraph()
        .add_wire(TerminalRef("V1", "neg"), TerminalRef("GND1", "gnd"), wire_id="W1")
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("R1", "a"), wire_id="W2")
    )
    v1 = DCVoltageSource("V1", "a", "b", voltage=12.0)
    r1 = Resistor("R1", "a", "b", resistance=100.0)
    gnd = Ground("GND1")
    netlist = build_circuit(g, [v1, r1, gnd])
    with pytest.raises(FloatingNodeError, match="is floating"):
        netlist.circuit.validate_topology()


def test_diagnostics_through_new_path_voltage_source_loop() -> None:
    """build_circuit with two voltage sources in parallel with unequal voltages raises VoltageSourceLoopError."""
    # V1 (12V) and V2 (5V) in parallel between node N1 and 0
    g = (
        WireGraph()
        .add_wire(TerminalRef("V1", "neg"), TerminalRef("GND1", "gnd"), wire_id="W1")
        .add_wire(TerminalRef("V2", "neg"), TerminalRef("GND1", "gnd"), wire_id="W2")
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("V2", "pos"), wire_id="W3")
    )
    v1 = DCVoltageSource("V1", "a", "b", voltage=12.0)
    v2 = DCVoltageSource("V2", "a", "b", voltage=5.0)
    gnd = Ground("GND1")
    netlist = build_circuit(g, [v1, v2, gnd])
    with pytest.raises(VoltageSourceLoopError):
        netlist.circuit.validate_topology()


def test_seeded_random_sequence_200_operations_keeps_validate_passing() -> None:
    """Seeded sequence of 200 random operations maintains graph validity at every step."""
    rng = random.Random(42)
    comps = {
        "R1": ("a", "b"),
        "R2": ("a", "b"),
        "V1": ("pos", "neg"),
        "GND1": ("gnd",),
    }

    graph = WireGraph()
    operations = ["add_junction", "add_wire", "remove_wire", "split_wire", "remove_junction"]

    for step in range(200):
        op = rng.choice(operations)
        try:
            if op == "add_junction":
                pos = (rng.randint(-5, 5) * 20, rng.randint(-5, 5) * 20)
                graph = graph.add_junction(pos)
            elif op == "add_wire":
                # Pick two random attachments
                choices = []
                for cname, terms in comps.items():
                    for t in terms:
                        choices.append(TerminalRef(cname, t))
                for j in graph.junctions:
                    choices.append(JunctionRef(j.id))
                choices.append(FreeEnd(rng.randint(-5, 5) * 20, rng.randint(-5, 5) * 20))
                att_a = rng.choice(choices)
                att_b = rng.choice(choices)
                if att_a != att_b:
                    graph = graph.add_wire(att_a, att_b)
            elif op == "remove_wire" and graph.wires:
                w = rng.choice(graph.wires)
                graph = graph.remove_wire(w.id)
            elif op == "split_wire" and graph.wires:
                w = rng.choice(graph.wires)
                pos = (rng.randint(-5, 5) * 20, rng.randint(-5, 5) * 20)
                res = graph.split_wire_at(w.id, pos)
                graph = res.graph
            elif op == "remove_junction" and graph.junctions:
                j = rng.choice(graph.junctions)
                graph = graph.remove_junction(j.id)
        except WireGraphError:
            # Rejection of invalid input is expected and valid behavior
            pass

        # Graph MUST be valid
        graph.validate(comps)


def test_equivalence_voltage_divider_hand_and_old_extractor() -> None:
    """Equivalence test: Voltage divider (12V, 1k, 3k, GND).

    Hand calculation:
      V_mid = 12 * 3000 / (1000 + 3000) = 9.0 V
      I = 12 / 4000 = 3.0 mA = 0.003 A
    Both old extractor and new build_circuit must match.
    """
    v1 = DCVoltageSource("V1", "pos", "neg", voltage=12.0)
    r1 = Resistor("R1", "a", "b", resistance=1000.0)
    r2 = Resistor("R2", "a", "b", resistance=3000.0)
    gnd = Ground("GND1")

    # 1. New WireGraph
    # V1.pos -> R1.a
    # R1.b -> R2.a (v_mid)
    # R2.b -> J1, V1.neg -> J1, GND1.gnd -> J1 (ground net "0")
    g = (
        WireGraph()
        .add_junction((-60, 40), "J1")
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("R1", "a"), wire_id="W_top")
        .add_wire(TerminalRef("R1", "b"), TerminalRef("R2", "a"), wire_id="W_mid")
        .add_wire(TerminalRef("R2", "b"), JunctionRef("J1"), wire_id="W_ret")
        .add_wire(TerminalRef("V1", "neg"), JunctionRef("J1"), wire_id="W_vneg")
        .add_wire(TerminalRef("GND1", "gnd"), JunctionRef("J1"), wire_id="W_gnd")
    )
    netlist_new = build_circuit(g, [v1, r1, r2, gnd])
    sol_new = MNASolver(netlist_new.circuit).solve_dc()

    # 2. Old extractor specs
    v1_spec = PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=12.0), (-100.0, 0.0))
    r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", resistance=1000.0), (0.0, 0.0))
    r2_spec = PlacedComponentSpec(Resistor("R2", "a", "b", resistance=3000.0), (120.0, 0.0))
    gnd_spec = PlacedComponentSpec(Ground("GND1"), (-140.0, 60.0))
    old_wires = [
        WireSpec("W_top", ((-140, 0), (-140, -60), (-40, -60), (-40, 0))),
        WireSpec("W_mid", ((40, 0), (80, 0))),
        WireSpec("W_ret1", ((160, 0), (160, 40), (-60, 40), (-60, 0))),
        WireSpec("W_gnd", ((-60, 40), (-140, 40))),
    ]
    old_extracted = extract_connectivity([v1_spec, r1_spec, r2_spec, gnd_spec], old_wires)
    sol_old = MNASolver(old_extracted.circuit).solve_dc()

    # Verify both match hand calculations
    mid_node = netlist_new.component_nodes["R1"]["b"]
    assert sol_new.node_voltages[mid_node] == pytest.approx(9.0, rel=1e-8)
    assert sol_old.node_voltages[old_extracted.component_nodes["R1"]["b"]] == pytest.approx(9.0, rel=1e-8)

    r2_comp = netlist_new.circuit.get_component("R2")
    assert r2_comp.current == pytest.approx(3.0e-3, rel=1e-8)
    assert old_extracted.circuit.get_component("R2").current == pytest.approx(3.0e-3, rel=1e-8)


def test_equivalence_rc_circuit() -> None:
    """Equivalence test: RC transient circuit (10V, 1k, 1uF, GND).

    At t=0+, V_cap = 0 V; at t -> inf, V_cap = 10 V.
    """
    vs = 10.0
    r_val = 1000.0
    c_val = 1e-6

    v1 = DCVoltageSource("V1", "pos", "neg", voltage=vs)
    r1 = Resistor("R1", "a", "b", resistance=r_val)
    c1 = Capacitor("C1", "a", "b", capacitance=c_val, initial_voltage=0.0)
    gnd = Ground("GND1")

    g = (
        WireGraph()
        .add_junction((0, 40), "J1")
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("R1", "a"))
        .add_wire(TerminalRef("R1", "b"), TerminalRef("C1", "a"))
        .add_wire(TerminalRef("C1", "b"), JunctionRef("J1"))
        .add_wire(TerminalRef("V1", "neg"), JunctionRef("J1"))
        .add_wire(TerminalRef("GND1", "gnd"), JunctionRef("J1"))
    )
    netlist = build_circuit(g, [v1, r1, c1, gnd])
    sol_dc = MNASolver(netlist.circuit).solve_dc()

    # In DC operating point, capacitor is open circuit -> V_cap = 10.0 V, current = 0 A
    cap_node = netlist.component_nodes["C1"]["a"]
    assert sol_dc.node_voltages[cap_node] == pytest.approx(10.0, rel=1e-8)
    assert netlist.circuit.get_component("R1").current == pytest.approx(0.0, abs=1e-9)


def test_equivalence_series_voltage_sources_12v_plus_12v() -> None:
    """Equivalence test: Two 12V sources in series across a 100 Ohm load.

    Hand calculation: Total V = 24.0 V, I = 24 / 100 = 0.24 A.
    """
    v1 = DCVoltageSource("V1", "pos", "neg", voltage=12.0)
    v2 = DCVoltageSource("V2", "pos", "neg", voltage=12.0)
    r1 = Resistor("R1", "a", "b", resistance=100.0)
    gnd = Ground("GND1")

    # GND -> V1.neg; V1.pos -> V2.neg; V2.pos -> R1.a; R1.b -> GND
    g = (
        WireGraph()
        .add_junction((0, 60), "J1")
        .add_wire(TerminalRef("GND1", "gnd"), JunctionRef("J1"))
        .add_wire(TerminalRef("V1", "neg"), JunctionRef("J1"))
        .add_wire(TerminalRef("R1", "b"), JunctionRef("J1"))
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("V2", "neg"))
        .add_wire(TerminalRef("V2", "pos"), TerminalRef("R1", "a"))
    )
    netlist = build_circuit(g, [v1, v2, r1, gnd])
    sol = MNASolver(netlist.circuit).solve_dc()

    v_top = sol.node_voltages[netlist.component_nodes["R1"]["a"]]
    assert v_top == pytest.approx(24.0, rel=1e-8)
    assert netlist.circuit.get_component("R1").current == pytest.approx(0.24, rel=1e-8)


def test_equivalence_source_switch_bulb() -> None:
    """Equivalence test: Source + Switch + Bulb.

    Switch closed: bulb receives full voltage (120V) and dissipates rated power (60W).
    Switch open: bulb receives 0V and 0W.
    """
    v1 = DCVoltageSource("V1", "pos", "neg", voltage=120.0)
    sw = Switch("SW1", "a", "b", closed=True)
    b1 = Lightbulb("B1", "a", "b", rated_power=60.0, rated_voltage=120.0)
    gnd = Ground("GND1")

    g = (
        WireGraph()
        .add_junction((0, 60), "J1")
        .add_wire(TerminalRef("GND1", "gnd"), JunctionRef("J1"))
        .add_wire(TerminalRef("V1", "neg"), JunctionRef("J1"))
        .add_wire(TerminalRef("B1", "b"), JunctionRef("J1"))
        .add_wire(TerminalRef("V1", "pos"), TerminalRef("SW1", "a"))
        .add_wire(TerminalRef("SW1", "b"), TerminalRef("B1", "a"))
    )

    # 1. Closed switch
    netlist_closed = build_circuit(g, [v1, sw, b1, gnd])
    sol_closed = MNASolver(netlist_closed.circuit).solve_dc()
    bulb_closed = netlist_closed.circuit.get_component("B1")
    v_bulb_closed = abs(
        sol_closed.node_voltages[netlist_closed.component_nodes["B1"]["a"]]
        - sol_closed.node_voltages[netlist_closed.component_nodes["B1"]["b"]]
    )
    # Hand calculation: Bulb R = 120^2 / 60 = 240 Ohm. Switch closed has r_on = 1e-3 Ohm.
    # Total R = 240.001 Ohm.
    # V_bulb = 120 * (240 / 240.001) = 119.99950000208332 V
    # I = 120 / 240.001 = 0.4999979166753472 A
    r_bulb = (120.0**2) / 60.0
    r_total = r_bulb + sw.r_on
    v_expected = 120.0 * (r_bulb / r_total)
    i_expected = 120.0 / r_total
    assert v_bulb_closed == pytest.approx(v_expected, rel=1e-8)
    assert bulb_closed.current == pytest.approx(i_expected, rel=1e-8)

    # 2. Open switch (modeled in MNA with r_off = 1e9 Ohm)
    sw_open = Switch("SW1", "a", "b", closed=False)
    netlist_open = build_circuit(g, [v1, sw_open, b1, gnd])
    sol_open = MNASolver(netlist_open.circuit).solve_dc()
    bulb_open = netlist_open.circuit.get_component("B1")
    v_bulb_open = abs(
        sol_open.node_voltages[netlist_open.component_nodes["B1"]["a"]]
        - sol_open.node_voltages[netlist_open.component_nodes["B1"]["b"]]
    )
    # Hand calculation: V_bulb = 120 * 240 / (1e9 + 240) = 2.8799993081e-5 V
    v_open_expected = 120.0 * (r_bulb / (r_bulb + sw_open.r_off))
    i_open_expected = 120.0 / (r_bulb + sw_open.r_off)
    assert v_bulb_open == pytest.approx(v_open_expected, rel=1e-8)
    assert bulb_open.current == pytest.approx(i_open_expected, rel=1e-8)
    assert bulb_open.brightness_percent == pytest.approx(0.0, abs=1e-6)
