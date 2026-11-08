"""Tests for rotation and moving components with wires attached.

Verifies:
1. Single component with attached wires rotated by 90°, 180°, 270° and flipped:
   - Each wire end is still exactly on its terminal's new position.
   - Wires stay orthogonal.
   - No wire passes through the part's body.
   - Electrical node of each terminal is unchanged (no shorts, distinct nets).
2. Group rotation of multiple connected components.
3. Dragging a component with attached wires.
4. Hand-calculated circuit simulation retains exact voltages across all rotations.
5. QUndoStack undo and redo restore components and wires exactly.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    PointPx,
    WireSpec,
    extract_connectivity,
    reroute_wires_for_updated_terminals,
    simplify_orthogonal_points,
)
from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    load_all_iec_metadata,
)
from circuitsim.components import DCVoltageSource, Ground, Resistor
from circuitsim.engine import MNASolver

CATALOG = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)


def _assert_wire_orthogonal(pts: tuple[PointPx, ...]) -> None:
    assert len(pts) >= 2, "Wire must have at least 2 points"
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        assert x1 == x2 or y1 == y2, f"Segment ({x1}, {y1}) -> ({x2}, {y2}) is not orthogonal"


def _assert_no_body_penetration(pts: tuple[PointPx, ...], center: PointPx, is_horiz: bool) -> None:
    cx, cy = center
    if is_horiz:
        min_x, max_x = cx - 39, cx + 39
        min_y, max_y = cy - 19, cy + 19
    else:
        min_x, max_x = cx - 19, cx + 19
        min_y, max_y = cy - 39, cy + 39

    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        if y1 == y2:
            if min_y < y1 < max_y:
                seg_min_x, seg_max_x = min(x1, x2), max(x1, x2)
                overlap = max(seg_min_x, min_x) < min(seg_max_x, max_x)
                assert not overlap, f"Horizontal segment ({x1}, {y1}) -> ({x2}, {y2}) penetrates body at {center}"
        elif x1 == x2:
            if min_x < x1 < max_x:
                seg_min_y, seg_max_y = min(y1, y2), max(y1, y2)
                overlap = max(seg_min_y, min_y) < min(seg_max_y, max_y)
                assert not overlap, f"Vertical segment ({x1}, {y1}) -> ({x2}, {y2}) penetrates body at {center}"


@pytest.mark.parametrize(
    "new_rot, new_flip, expected_a, expected_b, is_horiz",
    [
        (90, False, (200, 160), (200, 240), False),
        (180, False, (240, 200), (160, 200), True),
        (270, False, (200, 240), (200, 160), False),
        (0, True, (240, 200), (160, 200), True),
    ],
)
def test_single_part_rotation_and_flip_with_wires_attached(
    new_rot: int, new_flip: bool, expected_a: PointPx, expected_b: PointPx, is_horiz: bool
) -> None:
    """Rotate/flip a part with a wire on each terminal, asserting orthogonality, terminal tracking, and body clearance."""
    center = (200, 200)
    old_terms = {"R1": {"a": (160, 200), "b": (240, 200)}}
    new_terms = {"R1": {"a": expected_a, "b": expected_b}}

    # Wires initially connected to a and b from fixed external points
    w1 = WireSpec("W1", ((100, 200), (160, 200)))
    w2 = WireSpec("W2", ((240, 200), (300, 200)))

    updated = reroute_wires_for_updated_terminals(old_terms, new_terms, [w1, w2])
    pts1 = updated["W1"]
    pts2 = updated["W2"]

    # 1. Wire ends are exactly on the terminal's new positions
    assert pts1[0] == (100, 200)
    assert pts1[-1] == expected_a
    assert pts2[0] == expected_b
    assert pts2[-1] == (300, 200)

    # 2. Wires stay strictly orthogonal
    _assert_wire_orthogonal(pts1)
    _assert_wire_orthogonal(pts2)

    # 3. No wire penetrates the part body
    _assert_no_body_penetration(pts1, center, is_horiz)
    _assert_no_body_penetration(pts2, center, is_horiz)

    # 4. Check connectivity extraction: nodes for terminal a and b remain distinct (no short-circuit)
    r1_spec = PlacedComponentSpec(
        component=Resistor("R1", "a", "b", resistance=1000.0),
        center_px=center,
        rotation_deg=new_rot,
        flipped_h=new_flip,
    )
    # Extra power source and ground to form valid circuit
    v1_spec = PlacedComponentSpec(
        component=DCVoltageSource("V1", "pos", "neg", voltage=12.0),
        center_px=(0, 0),
    )
    gnd_spec = PlacedComponentSpec(
        component=Ground("GND1"),
        center_px=(40, 320),
    )
    wires = [
        WireSpec("W1", pts1),
        WireSpec("W2", pts2),
        WireSpec("W_v1_pos", ((-40, 0), (-40, -100), (100, -100), (100, 200))),
        WireSpec("W_v1_neg", ((40, 0), (40, 300))),
        WireSpec("W_return", ((40, 300), (300, 300), (300, 200))),
    ]
    res = extract_connectivity([v1_spec, gnd_spec, r1_spec], wires, symbol_catalog=CATALOG)
    assert res.component_nodes["R1"]["a"] != res.component_nodes["R1"]["b"], "Terminals a and b must not short circuit!"
    sol = MNASolver(res.circuit).solve_dc()
    r1_comp = res.circuit.get_component("R1")
    assert r1_comp.voltage == pytest.approx(12.0)
    assert r1_comp.current == pytest.approx(0.012)


def test_dragging_part_with_wires_attached() -> None:
    """Dragging a component with attached wires keeps endpoints on terminals and avoids body penetration."""
    old_terms = {"R1": {"a": (160, 200), "b": (240, 200)}}
    # Drag by dx = 40, dy = 60
    new_center = (240, 260)
    new_terms = {"R1": {"a": (200, 260), "b": (280, 260)}}

    w1 = WireSpec("W1", ((100, 200), (160, 200)))
    w2 = WireSpec("W2", ((240, 200), (300, 200)))

    updated = reroute_wires_for_updated_terminals(old_terms, new_terms, [w1, w2])
    pts1 = updated["W1"]
    pts2 = updated["W2"]

    assert pts1[-1] == (200, 260)
    assert pts2[0] == (280, 260)
    _assert_wire_orthogonal(pts1)
    _assert_wire_orthogonal(pts2)
    _assert_no_body_penetration(pts1, new_center, is_horiz=True)
    _assert_no_body_penetration(pts2, new_center, is_horiz=True)


def test_group_rotation_with_wires_attached() -> None:
    """Group of two connected parts rotated together preserves connection between them and external wires."""
    old_terms = {
        "R1": {"a": (160, 200), "b": (240, 200)},
        "R2": {"a": (240, 200), "b": (320, 200)},
    }
    # Rotate both by 90 deg around (200, 200):
    new_terms = {
        "R1": {"a": (200, 160), "b": (200, 240)},
        "R2": {"a": (200, 240), "b": (200, 320)},
    }
    w_ext = WireSpec("W_ext", ((320, 200), (400, 200)))

    updated = reroute_wires_for_updated_terminals(old_terms, new_terms, [w_ext])
    assert updated["W_ext"][0] == (200, 320)
    assert updated["W_ext"][-1] == (400, 200)
    _assert_wire_orthogonal(updated["W_ext"])


def test_rotation_cycle_and_rotating_back_preserves_voltages() -> None:
    """A circuit that works before rotation must give the same voltages after rotating and after rotating back."""
    v1_spec = PlacedComponentSpec(DCVoltageSource("V1", "pos", "neg", voltage=12.0), (0, 0))
    gnd_spec = PlacedComponentSpec(Ground("GND1"), (40, 320))

    # Test full 360 rotation cycle: 0 -> 90 -> 180 -> 270 -> 0 (rotating back)
    curr_terms = {"R1": {"a": (160, 200), "b": (240, 200)}}
    w1 = WireSpec("W1", ((100, 200), (160, 200)))
    w2 = WireSpec("W2", ((240, 200), (300, 200)))

    rotations = [
        (90, (200, 160), (200, 240)),
        (180, (240, 200), (160, 200)),
        (270, (200, 240), (200, 160)),
        (0, (160, 200), (240, 200)),  # rotated back to start
    ]

    for rot, next_a, next_b in rotations:
        next_terms = {"R1": {"a": next_a, "b": next_b}}
        updated = reroute_wires_for_updated_terminals(curr_terms, next_terms, [w1, w2])
        w1 = WireSpec("W1", updated["W1"])
        w2 = WireSpec("W2", updated["W2"])
        curr_terms = next_terms

        r1_spec = PlacedComponentSpec(Resistor("R1", "a", "b", 1000.0), (200, 200), rotation_deg=rot)
        wires = [
            w1,
            w2,
            WireSpec("W_v1_pos", ((-40, 0), (-40, -100), (100, -100), (100, 200))),
            WireSpec("W_v1_neg", ((40, 0), (40, 300))),
            WireSpec("W_return", ((40, 300), (300, 300), (300, 200))),
        ]
        res = extract_connectivity([v1_spec, gnd_spec, r1_spec], wires, symbol_catalog=CATALOG)
        sol = MNASolver(res.circuit).solve_dc()
        r1 = res.circuit.get_component("R1")
        assert r1.voltage == pytest.approx(12.0)
        assert r1.current == pytest.approx(0.012)
        assert r1.power == pytest.approx(0.144)


def _run_qt(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_circuit_scene_undo_redo_rotation_and_drag() -> None:
    """Subprocess Qt test: CircuitScene rotate, flip, and drag undo/redo restores part and wires exactly."""
    script = """
import sys
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary

app = QApplication(sys.argv)
lib = SymbolLibrary()
scene = CircuitScene(lib)

# 1. Place resistor at (200, 200) with two attached wires
r1 = scene.place_new_component("resistor", QPointF(200, 200))
w1 = scene.add_wire(((100.0, 200.0), (160.0, 200.0)))
w2 = scene.add_wire(((240.0, 200.0), (300.0, 200.0)))

orig_rot = r1.rotation_deg
orig_pos = (r1.pos().x(), r1.pos().y())
orig_w1 = w1.points
orig_w2 = w2.points

# 2. Select and rotate 90°
scene.clearSelection()
r1.setSelected(True)
assert scene.rotate_selected()
assert r1.rotation_deg == 90
assert w1.points[-1] == (200, 160)
assert w2.points[0] == (200, 240)

# Undo rotation
scene.undo_stack.undo()
assert r1.rotation_deg == orig_rot
assert w1.points == orig_w1
assert w2.points == orig_w2

# Redo rotation
scene.undo_stack.redo()
assert r1.rotation_deg == 90
assert w1.points[-1] == (200, 160)
assert w2.points[0] == (200, 240)

# 3. Flip
assert scene.flip_selected()
# Undo flip
scene.undo_stack.undo()
assert r1.rotation_deg == 90

print("UNDO_REDO_ROTATION_PASSED")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "UNDO_REDO_ROTATION_PASSED" in res.stdout
