"""Polarity regression tests (pure-Python, Qt-free).

Verifies that for every orientation (rotation in {0, 90, 180, 270} and flip in {False, True}):
1. DC Voltage Source: terminal drawn as '+' is +12 V above the terminal drawn as '-'.
2. DC Current Source: arrow direction decides current flow (leaves '+', enters '-').
3. Voltmeter: '+' side on higher node reads positive voltage (+12 V).
4. Ammeter: current entering at '+' side reads positive current (+12 mA).
5. Two-source chain: 12 V + 12 V in same direction gives 24 V, opposite gives 0 V,
   for all orientations of the second source.
"""

from __future__ import annotations

import pytest

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    WireSpec,
    extract_connectivity,
)
from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    load_all_iec_metadata,
    transform_terminal_position,
)
from circuitsim.components import (
    Ammeter,
    DCCurrentSource,
    DCVoltageSource,
    Ground,
    Resistor,
    Voltmeter,
)
from circuitsim.engine import MNASolver

CATALOG = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)


# Hand-calculated terminal positions for a 2-terminal part centered at (0, 0)
# with base terminals pos at (-40, 0) and neg at (40, 0):
# Order: flip horizontally (lx = -lx), then rotate CW (+90 deg maps (x, y) to (-y, x)).
HAND_CALCULATED_TERMINALS = {
    # (rot, flip): (pos_pos, neg_pos)
    (0, False): ((-40, 0), (40, 0)),
    (90, False): ((0, -40), (0, 40)),
    (180, False): ((40, 0), (-40, 0)),
    (270, False): ((0, 40), (0, -40)),
    (0, True): ((40, 0), (-40, 0)),
    (90, True): ((0, -40), (0, 40)),
    (180, True): ((-40, 0), (40, 0)),
    (270, True): ((0, 40), (0, -40)),
}


def _route_to_top_rail(pt: tuple[float, float], rail_y: float = -100.0, side_x: float = -60.0) -> tuple[tuple[float, float], ...]:
    """Route from terminal pt to top rail without passing through component body."""
    x, y = pt
    if y > 0:  # terminal is at bottom: route around the side
        return ((x, y), (x + side_x, y), (x + side_x, rail_y))
    return ((x, y), (x, rail_y))


def _route_to_bot_rail(pt: tuple[float, float], rail_y: float = 100.0, side_x: float = 60.0) -> tuple[tuple[float, float], ...]:
    """Route from terminal pt to bottom rail without passing through component body."""
    x, y = pt
    if y < 0:  # terminal is at top: route around the side
        return ((x, y), (x + side_x, y), (x + side_x, rail_y))
    return ((x, y), (x, rail_y))


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
def test_dc_voltage_source_polarity_all_orientations(rot: int, flip: bool) -> None:
    """12 V source with one terminal grounded, 1 kΩ resistor to ground, voltmeter across resistor."""
    expected_pos, expected_neg = HAND_CALCULATED_TERMINALS[(rot, flip)]

    # Confirm transform_terminal_position matches hand calculation
    computed_pos = transform_terminal_position((-2, 0), (0, 0), rotation_deg=rot, flipped_h=flip)
    computed_neg = transform_terminal_position((2, 0), (0, 0), rotation_deg=rot, flipped_h=flip)
    assert computed_pos == expected_pos
    assert computed_neg == expected_neg

    v1_spec = PlacedComponentSpec(
        component=DCVoltageSource("V1", "n_pos", "n_neg", voltage=12.0),
        center_px=(0, 0),
        rotation_deg=rot,
        flipped_h=flip,
    )
    gnd_spec = PlacedComponentSpec(
        component=Ground("GND1"),
        center_px=(250, 120),  # terminal at (250, 100) on bottom rail
    )
    r1_spec = PlacedComponentSpec(
        component=Resistor("R1", "a", "b", resistance=1000.0),
        center_px=(200, 0),
        rotation_deg=90,  # a at (200, -40), b at (200, 40)
    )
    vm1_spec = PlacedComponentSpec(
        component=Voltmeter("VM1", "pos", "neg"),
        center_px=(350, 0),
        rotation_deg=90,  # pos at (350, -40), neg at (350, 40)
    )

    pos_branch = _route_to_top_rail(expected_pos, rail_y=-100.0, side_x=-60.0)
    neg_branch = _route_to_bot_rail(expected_neg, rail_y=100.0, side_x=60.0)

    wires = [
        # Positive rail at y = -100: connects V1 pos -> R1 a (200, -40) -> VM1 pos (350, -40)
        WireSpec("W_v1_pos", pos_branch),
        WireSpec("W_top_rail1", ((pos_branch[-1][0], -100), (200, -100))),
        WireSpec("W_r1_top", ((200, -100), (200, -40))),
        WireSpec("W_top_rail2", ((200, -100), (350, -100))),
        WireSpec("W_vm1_top", ((350, -100), (350, -40))),
        # Negative rail at y = 100: connects V1 neg -> GND (250, 100) -> R1 b (200, 40) -> VM1 neg (350, 40)
        WireSpec("W_v1_neg", neg_branch),
        WireSpec("W_bot_rail1", ((neg_branch[-1][0], 100), (200, 100))),
        WireSpec("W_r1_bot", ((200, 100), (200, 40))),
        WireSpec("W_bot_rail2", ((200, 100), (250, 100))),  # ends at GND terminal (250, 100)
        WireSpec("W_bot_rail3", ((250, 100), (350, 100))),
        WireSpec("W_vm1_bot", ((350, 100), (350, 40))),
    ]

    res = extract_connectivity([v1_spec, gnd_spec, r1_spec, vm1_spec], wires, symbol_catalog=CATALOG)
    sol = MNASolver(res.circuit).solve_dc()

    pos_node = res.component_nodes["V1"]["pos"]
    neg_node = res.component_nodes["V1"]["neg"]
    assert pos_node != neg_node
    v_pos = sol.node_voltages.get(pos_node, 0.0)
    v_neg = sol.node_voltages.get(neg_node, 0.0)
    assert v_neg == pytest.approx(0.0)
    assert v_pos == pytest.approx(12.0)
    assert (v_pos - v_neg) == pytest.approx(12.0)

    vm = res.circuit.get_component("VM1")
    assert vm.reading == pytest.approx(12.0)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
def test_dc_current_source_polarity_all_orientations(rot: int, flip: bool) -> None:
    """10 mA current source (arrow toward pos): leaves pos, flows through 1 kΩ to ground, giving +10 V."""
    expected_pos, expected_neg = HAND_CALCULATED_TERMINALS[(rot, flip)]

    i1_spec = PlacedComponentSpec(
        component=DCCurrentSource("I1", "n_pos", "n_neg", current=0.01),
        center_px=(0, 0),
        rotation_deg=rot,
        flipped_h=flip,
    )
    gnd_spec = PlacedComponentSpec(
        component=Ground("GND1"),
        center_px=(250, 120),  # term at (250, 100)
    )
    r1_spec = PlacedComponentSpec(
        component=Resistor("R1", "a", "b", resistance=1000.0),
        center_px=(200, 0),
        rotation_deg=90,  # a at (200, -40), b at (200, 40)
    )

    pos_branch = _route_to_top_rail(expected_pos, rail_y=-100.0, side_x=-60.0)
    neg_branch = _route_to_bot_rail(expected_neg, rail_y=100.0, side_x=60.0)

    wires = [
        WireSpec("W_i1_pos", pos_branch),
        WireSpec("W_top_rail", ((pos_branch[-1][0], -100), (200, -100))),
        WireSpec("W_r1_top", ((200, -100), (200, -40))),
        WireSpec("W_i1_neg", neg_branch),
        WireSpec("W_bot_rail", ((neg_branch[-1][0], 100), (250, 100))),
        WireSpec("W_r1_bot", ((200, 100), (200, 40))),
    ]

    res = extract_connectivity([i1_spec, gnd_spec, r1_spec], wires, symbol_catalog=CATALOG)
    sol = MNASolver(res.circuit).solve_dc()

    pos_node = res.component_nodes["I1"]["pos"]
    neg_node = res.component_nodes["I1"]["neg"]
    v_pos = sol.node_voltages.get(pos_node, 0.0)
    v_neg = sol.node_voltages.get(neg_node, 0.0)
    assert v_neg == pytest.approx(0.0)
    assert v_pos == pytest.approx(10.0)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
def test_voltmeter_polarity_all_orientations(rot: int, flip: bool) -> None:
    """Voltmeter across +12 V and 0 V: when '+' is on +12 V reads +12 V."""
    vm_pos, vm_neg = HAND_CALCULATED_TERMINALS[(rot, flip)]

    # Fixed 12 V source at (0, 0), rot=0: pos at (-40, 0), neg at (40, 0)
    v1_spec = PlacedComponentSpec(
        component=DCVoltageSource("V1", "pos", "neg", voltage=12.0),
        center_px=(0, 0),
    )
    gnd_spec = PlacedComponentSpec(component=Ground("GND1"), center_px=(40, 120))
    r1_spec = PlacedComponentSpec(
        component=Resistor("R1", "a", "b", resistance=1000.0),
        center_px=(150, 0),
        rotation_deg=90,  # a at (150, -40), b at (150, 40)
    )
    # Voltmeter VM1 at (300, 0)
    vm1_spec = PlacedComponentSpec(
        component=Voltmeter("VM1", "pos", "neg"),
        center_px=(300, 0),
        rotation_deg=rot,
        flipped_h=flip,
    )

    vm_pos_world = (300 + vm_pos[0], vm_pos[1])
    vm_neg_world = (300 + vm_neg[0], vm_neg[1])
    vm_pos_branch = _route_to_top_rail(vm_pos_world, rail_y=-100.0, side_x=-40.0)
    vm_neg_branch = _route_to_bot_rail(vm_neg_world, rail_y=100.0, side_x=40.0)

    wires = [
        # Top rail (12 V)
        WireSpec("W_v1_top", ((-40, 0), (-40, -100), (150, -100))),
        WireSpec("W_r1_top", ((150, -100), (150, -40))),
        WireSpec("W_vm_top_rail", ((150, -100), (vm_pos_branch[-1][0], -100))),
        WireSpec("W_vm_pos", vm_pos_branch),
        # Bottom rail (0 V)
        WireSpec("W_v1_bot", ((40, 0), (40, 100))),  # ends at (40, 100) GND terminal
        WireSpec("W_r1_bot", ((40, 100), (150, 100), (150, 40))),
        WireSpec("W_vm_bot_rail", ((150, 100), (vm_neg_branch[-1][0], 100))),
        WireSpec("W_vm_neg", vm_neg_branch),
    ]

    res = extract_connectivity([v1_spec, gnd_spec, r1_spec, vm1_spec], wires, symbol_catalog=CATALOG)
    sol = MNASolver(res.circuit).solve_dc()
    vm = res.circuit.get_component("VM1")
    assert vm.reading == pytest.approx(12.0)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
def test_ammeter_polarity_all_orientations(rot: int, flip: bool) -> None:
    """Ammeter in series: current entering '+' reads +12 mA (+0.012 A)."""
    am_pos, am_neg = HAND_CALCULATED_TERMINALS[(rot, flip)]

    # 12 V source at (0, 0), fixed: pos at (-40, 0), neg at (40, 0)
    v1_spec = PlacedComponentSpec(
        component=DCVoltageSource("V1", "pos", "neg", voltage=12.0),
        center_px=(0, 0),
    )
    gnd_spec = PlacedComponentSpec(component=Ground("GND1"), center_px=(40, 160))  # term at (40, 140)

    # Ammeter A1 at (200, 0)
    a1_spec = PlacedComponentSpec(
        component=Ammeter("A1", "pos", "neg", r_internal=1e-3),
        center_px=(200, 0),
        rotation_deg=rot,
        flipped_h=flip,
    )
    # Resistor R1 at (400, 0), rot=90: a at (400, -40), b at (400, 40)
    r1_spec = PlacedComponentSpec(
        component=Resistor("R1", "a", "b", resistance=1000.0),
        center_px=(400, 0),
        rotation_deg=90,
    )

    am_pos_world = (200 + am_pos[0], am_pos[1])
    am_neg_world = (200 + am_neg[0], am_neg[1])
    am_pos_branch = _route_to_top_rail(am_pos_world, rail_y=-100.0, side_x=-40.0)
    am_neg_branch = _route_to_bot_rail(am_neg_world, rail_y=100.0, side_x=40.0)

    # Current path: V1 pos -> Top rail -> Ammeter pos -> Ammeter neg -> Mid rail -> R1 a -> R1 b -> Bot rail -> V1 neg
    wires = [
        # V1 pos (-40, 0) to top rail y = -100, then to ammeter pos
        WireSpec("W1", ((-40, 0), (-40, -100), (am_pos_branch[-1][0], -100))),
        WireSpec("W_am_pos", am_pos_branch),
        # Ammeter neg to mid rail y = 100, then to R1 a (400, -40)
        WireSpec("W_am_neg", am_neg_branch),
        WireSpec("W2", ((am_neg_branch[-1][0], 100), (450, 100), (450, -40), (400, -40))),
        # R1 b (400, 40) to bot rail y = 140 at (40, 140) where GND is, then to V1 neg (40, 0)
        WireSpec("W3a", ((400, 40), (400, 140), (40, 140))),
        WireSpec("W3b", ((40, 140), (40, 0))),
    ]

    res = extract_connectivity([v1_spec, gnd_spec, a1_spec, r1_spec], wires, symbol_catalog=CATALOG)
    sol = MNASolver(res.circuit).solve_dc()
    ammeter = res.circuit.get_component("A1")
    assert ammeter.reading == pytest.approx(0.012, rel=1e-3)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
def test_two_source_chain_all_orientations_of_second_source(rot: int, flip: bool) -> None:
    """12 V + 12 V chain: same direction gives 24 V, opposite direction gives 0 V."""
    pos2, neg2 = HAND_CALCULATED_TERMINALS[(rot, flip)]

    # V1 fixed at (0, 0): pos at (-40, 0), neg at (40, 0) wired to ground
    v1_spec = PlacedComponentSpec(
        component=DCVoltageSource("V1", "pos", "neg", voltage=12.0),
        center_px=(0, 0),
    )
    gnd_spec = PlacedComponentSpec(component=Ground("GND1"), center_px=(40, 160))  # term at (40, 140)

    # V2 at (200, 0) with tested orientation
    v2_spec = PlacedComponentSpec(
        component=DCVoltageSource("V2", "pos", "neg", voltage=12.0),
        center_px=(200, 0),
        rotation_deg=rot,
        flipped_h=flip,
    )
    # Load resistor 1 kΩ at (400, 0), rot=90: a at (400, -40), b at (400, 40)
    r_load = PlacedComponentSpec(
        component=Resistor("R_load", "a", "b", resistance=1000.0),
        center_px=(400, 0),
        rotation_deg=90,
    )

    v2_pos_world = (200 + pos2[0], pos2[1])
    v2_neg_world = (200 + neg2[0], neg2[1])

    # 1. SAME DIRECTION: V2 neg connected to V1 pos.
    # Output taken from V2 pos. Expected voltage = +24 V.
    v2_neg_branch = _route_to_top_rail(v2_neg_world, rail_y=-100.0, side_x=-40.0)
    v2_pos_branch = _route_to_bot_rail(v2_pos_world, rail_y=100.0, side_x=40.0)

    wires_same = [
        # V1 pos (-40, 0) to V2 neg via top rail y = -100
        WireSpec("W_mid", ((-40, 0), (-40, -100), (v2_neg_branch[-1][0], -100))),
        WireSpec("W_v2_neg", v2_neg_branch),
        # V2 pos via bot rail y = 100 to R_load a (400, -40)
        WireSpec("W_v2_pos", v2_pos_branch),
        WireSpec("W_out", ((v2_pos_branch[-1][0], 100), (450, 100), (450, -40), (400, -40))),
        # R_load b (400, 40) via return rail y = 140 to GND at (40, 140), then to V1 neg (40, 0)
        WireSpec("W_ret1", ((400, 40), (400, 140), (40, 140))),
        WireSpec("W_ret2", ((40, 140), (40, 0))),
    ]
    res_same = extract_connectivity([v1_spec, gnd_spec, v2_spec, r_load], wires_same, symbol_catalog=CATALOG)
    sol_same = MNASolver(res_same.circuit).solve_dc()
    top_node = res_same.component_nodes["V2"]["pos"]
    assert sol_same.node_voltages[top_node] == pytest.approx(24.0)

    # 2. OPPOSITE DIRECTION: V2 pos connected to V1 pos.
    # Output taken from V2 neg. Expected voltage = 12 V - 12 V = 0 V.
    v2_pos_branch_opp = _route_to_top_rail(v2_pos_world, rail_y=-100.0, side_x=-40.0)
    v2_neg_branch_opp = _route_to_bot_rail(v2_neg_world, rail_y=100.0, side_x=40.0)

    wires_opp = [
        # V1 pos (-40, 0) to V2 pos via top rail y = -100
        WireSpec("W_mid_opp", ((-40, 0), (-40, -100), (v2_pos_branch_opp[-1][0], -100))),
        WireSpec("W_v2_pos_opp", v2_pos_branch_opp),
        # V2 neg via bot rail y = 100 to R_load a (400, -40)
        WireSpec("W_v2_neg_opp", v2_neg_branch_opp),
        WireSpec("W_out_opp", ((v2_neg_branch_opp[-1][0], 100), (450, 100), (450, -40), (400, -40))),
        # R_load b (400, 40) via return rail y = 140 to GND at (40, 140), then to V1 neg (40, 0)
        WireSpec("W_ret_opp1", ((400, 40), (400, 140), (40, 140))),
        WireSpec("W_ret_opp2", ((40, 140), (40, 0))),
    ]
    res_opp = extract_connectivity([v1_spec, gnd_spec, v2_spec, r_load], wires_opp, symbol_catalog=CATALOG)
    sol_opp = MNASolver(res_opp.circuit).solve_dc()
    out_node = res_opp.component_nodes["V2"]["neg"]
    assert sol_opp.node_voltages.get(out_node, 0.0) == pytest.approx(0.0)
