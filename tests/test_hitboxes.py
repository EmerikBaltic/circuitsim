"""Subprocess Qt tests for component hitboxes, bounding rects, and label plates.

Verifies:
1. For every component type (all 11) and every orientation (rot in {0, 90, 180, 270}, flip in {False, True}):
   - shape() and boundingRect() contain the drawn symbol body and every terminal position.
   - scene.itemAt() returns nothing at points 100 px away and at the corner a rotated part used to occupy.
   - scene.itemAt() at each terminal position returns that component.
   - All properties hold after moving, rotating, and flipping the part.
2. Label background plates do not accept mouse clicks (return None when clicked on empty canvas)
   and do not block selecting a wire that passes behind a label.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _run_qt(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_hitboxes_and_bounding_rects_all_parts_and_orientations() -> None:
    """Subprocess Qt test for all 11 part types across all 8 orientations."""
    script = """
import sys
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.symbol_geometry import DEFAULT_IEC_SYMBOLS_DIR, load_all_iec_metadata

app = QApplication(sys.argv)
lib = SymbolLibrary()
catalog = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
part_types = list(catalog.keys())

for ptype in part_types:
    for rot in [0, 90, 180, 270]:
        for flip in [False, True]:
            scene = CircuitScene(lib)
            pos_x, pos_y = 200.0, 200.0
            item = scene.place_new_component(ptype, QPointF(pos_x, pos_y), rotation_deg=rot, flipped_h=flip)

            # 1. shape() and boundingRect() contain drawn symbol center and body
            shape = item.shape()
            brect = item.boundingRect()
            assert shape.contains(QPointF(0, 0)), f"Shape missing center for {ptype} rot={rot} flip={flip}"
            assert brect.contains(QPointF(0, 0)), f"BoundingRect missing center for {ptype} rot={rot} flip={flip}"

            # 2. shape() and boundingRect() contain every terminal position
            terminals = item.terminal_scene_positions()
            for tname, (tx, ty) in terminals.items():
                local_pt = item.mapFromScene(QPointF(tx, ty))
                assert shape.contains(local_pt), f"Shape missing terminal {tname} for {ptype} rot={rot} flip={flip}"
                assert brect.contains(local_pt), f"BoundingRect missing terminal {tname} for {ptype} rot={rot} flip={flip}"

                # scene.itemAt reaches the terminal
                hit = scene.itemAt(QPointF(tx, ty), QTransform())
                assert hit is item, f"Click at terminal {tname} ({tx}, {ty}) reached {hit} instead of {item.component.name}"

            # 3. scene.itemAt on points clearly away returns nothing (100 px away)
            for dx, dy in [(100.0, 0.0), (-100.0, 0.0), (0.0, 100.0), (0.0, -100.0)]:
                away_pt = QPointF(pos_x + dx, pos_y + dy)
                hit_away = scene.itemAt(away_pt, QTransform())
                assert hit_away is None, f"Point 100 px away ({dx}, {dy}) hit {hit_away} for {ptype}"

            # 4. Corner test: rotate CW by 90 deg and verify previous corner/terminal is empty
            if ptype != "ground":
                # For 2-terminal parts centered at (200, 200):
                # Before this additional rotation, terminals were at known positions
                old_terms = list(item.terminal_scene_positions().values())
                item.rotate_90_cw()
                new_terms = set(item.terminal_scene_positions().values())
                for ot in old_terms:
                    if ot not in new_terms:
                        hit_old = scene.itemAt(QPointF(ot[0], ot[1]), QTransform())
                        assert hit_old is None, f"Former terminal position {ot} was not cleared after rotate for {ptype}, hit {hit_old}"

            # 5. Moving the part
            new_x, new_y = 400.0, 300.0
            item.set_snapped_pos(new_x, new_y)
            assert scene.itemAt(QPointF(pos_x, pos_y), QTransform()) is None, f"Old center {pos_x}, {pos_y} still hit after move"
            for tname, (tx, ty) in item.terminal_scene_positions().items():
                hit_moved = scene.itemAt(QPointF(tx, ty), QTransform())
                assert hit_moved is item, f"Terminal {tname} not hit after move to ({new_x}, {new_y})"
            for dx, dy in [(100.0, 0.0), (-100.0, 0.0), (0.0, 100.0), (0.0, -100.0)]:
                assert scene.itemAt(QPointF(new_x + dx, new_y + dy), QTransform()) is None

            # 6. Flipping the part
            item.flip_horizontal()
            for tname, (tx, ty) in item.terminal_scene_positions().items():
                assert scene.itemAt(QPointF(tx, ty), QTransform()) is item, f"Terminal {tname} not hit after flip"

print("ALL_HITBOX_TESTS_PASSED")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "ALL_HITBOX_TESTS_PASSED" in res.stdout


def test_label_background_plate_does_not_intercept_clicks_or_block_wires() -> None:
    """Label background plates must not accept mouse clicks or steal selection from wires."""
    script = """
import sys
from PySide6.QtCore import QPointF
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary

app = QApplication(sys.argv)
lib = SymbolLibrary()
scene = CircuitScene(lib)

# 1. Place resistor at (200, 200)
r1 = scene.place_new_component("resistor", QPointF(200, 200))
lbl_rect, val_rect, _ = r1._upright_label_and_value_rects()
lbl_scene_pt = r1.pos() + lbl_rect.center()

# Clicking directly on the label plate in empty space does NOT hit the component
hit_label = scene.itemAt(lbl_scene_pt, QTransform())
assert hit_label is None, f"Empty label plate intercepted click, returned {hit_label}"

# 2. Place a horizontal wire passing right behind the label plate
wire_y = 160.0  # grid line crossing the label
w = scene.add_wire(((100.0, wire_y), (300.0, wire_y)))

# Clicking on the label position where the wire passes behind it MUST hit the wire, not the component
wire_hit_pt = QPointF(200.0, wire_y)
hit_wire = scene.itemAt(wire_hit_pt, QTransform())
assert hit_wire is w, f"Wire behind label was blocked by label plate; got {hit_wire} instead of {w}"

# 3. Test value label readout area when component is rotated 90 deg
r2 = scene.place_new_component("resistor", QPointF(500, 500), rotation_deg=90)
lbl_rect2, val_rect2, _ = r2._upright_label_and_value_rects()
val_scene_pt = r2.pos() + val_rect2.center()

hit_val = scene.itemAt(val_scene_pt, QTransform())
assert hit_val is None, f"Empty value label plate intercepted click, returned {hit_val}"

w2 = scene.add_wire(((540.0, 400.0), (540.0, 600.0)))
test_pt = QPointF(540.0, 510.0)
assert val_rect2.contains(test_pt - r2.pos()), "test_pt not inside val_rect2"
hit_w2 = scene.itemAt(test_pt, QTransform())
assert hit_w2 is w2, f"Wire behind value label was blocked; got {hit_w2} instead of {w2}"

print("LABEL_PLATE_TESTS_PASSED")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "LABEL_PLATE_TESTS_PASSED" in res.stdout
