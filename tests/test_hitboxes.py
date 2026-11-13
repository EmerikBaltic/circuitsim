"""Qt tests for component hitboxes, bounding rects, and label plates."""

from __future__ import annotations


def test_hitboxes_and_bounding_rects_all_parts_and_orientations(qapp) -> None:
    """Test hitboxes and bounding rects for all part types across all 8 orientations."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QTransform
    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.canvas.symbol_geometry import DEFAULT_IEC_SYMBOLS_DIR, load_all_iec_metadata
    from circuitsim.canvas.symbol_renderer import SymbolLibrary

    lib = SymbolLibrary()
    catalog = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
    part_types = list(catalog.keys())

    for ptype in part_types:
        for rot in (0, 90, 180, 270):
            for flip in (False, True):
                scene = CircuitScene(lib)
                pos_x, pos_y = 200.0, 200.0
                item = scene.place_new_component(ptype, QPointF(pos_x, pos_y), rotation_deg=rot, flipped_h=flip)

                shape = item.shape()
                brect = item.boundingRect()
                assert shape.contains(QPointF(0, 0)), f"Shape missing center for {ptype} rot={rot} flip={flip}"
                assert brect.contains(QPointF(0, 0)), f"BoundingRect missing center for {ptype} rot={rot} flip={flip}"

                terminals = item.terminal_scene_positions()
                for tname, (tx, ty) in terminals.items():
                    local_pt = item.mapFromScene(QPointF(tx, ty))
                    assert shape.contains(local_pt), f"Shape missing terminal {tname} for {ptype} rot={rot} flip={flip}"
                    assert brect.contains(local_pt), f"BoundingRect missing terminal {tname} for {ptype} rot={rot} flip={flip}"

                    hit = scene.itemAt(QPointF(tx, ty), QTransform())
                    assert hit is item, (
                        f"Click at terminal {tname} ({tx}, {ty}) reached {hit} instead of {item.component.name}"
                    )

                for dx, dy in ((100.0, 0.0), (-100.0, 0.0), (0.0, 100.0), (0.0, -100.0)):
                    away_pt = QPointF(pos_x + dx, pos_y + dy)
                    hit_away = scene.itemAt(away_pt, QTransform())
                    assert hit_away is None, f"Point 100 px away ({dx}, {dy}) hit {hit_away} for {ptype}"

                if ptype != "ground":
                    old_terms = list(item.terminal_scene_positions().values())
                    item.rotate_90_cw()
                    new_terms = set(item.terminal_scene_positions().values())
                    for ot in old_terms:
                        if ot not in new_terms:
                            hit_old = scene.itemAt(QPointF(ot[0], ot[1]), QTransform())
                            assert hit_old is None, (
                                f"Former terminal position {ot} was not cleared after rotate for {ptype}, hit {hit_old}"
                            )

                new_x, new_y = 400.0, 300.0
                item.set_snapped_pos(new_x, new_y)
                assert scene.itemAt(QPointF(pos_x, pos_y), QTransform()) is None, (
                    f"Old center {pos_x}, {pos_y} still hit after move"
                )
                for tname, (tx, ty) in item.terminal_scene_positions().items():
                    hit_moved = scene.itemAt(QPointF(tx, ty), QTransform())
                    assert hit_moved is item, f"Terminal {tname} not hit after move to ({new_x}, {new_y})"
                for dx, dy in ((100.0, 0.0), (-100.0, 0.0), (0.0, 100.0), (0.0, -100.0)):
                    assert scene.itemAt(QPointF(new_x + dx, new_y + dy), QTransform()) is None

                item.flip_horizontal()
                for tname, (tx, ty) in item.terminal_scene_positions().items():
                    assert scene.itemAt(QPointF(tx, ty), QTransform()) is item, (
                        f"Terminal {tname} not hit after flip"
                    )


def test_label_background_plate_does_not_intercept_clicks_or_block_wires(qapp) -> None:
    """Label background plates must not accept mouse clicks or steal selection from wires."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QTransform
    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.canvas.symbol_renderer import SymbolLibrary

    lib = SymbolLibrary()
    scene = CircuitScene(lib)

    r1 = scene.place_new_component("resistor", QPointF(200, 200))
    lbl_rect, _val_rect, _ = r1._upright_label_and_value_rects()
    lbl_scene_pt = r1.pos() + lbl_rect.center()

    hit_label = scene.itemAt(lbl_scene_pt, QTransform())
    assert hit_label is None, f"Empty label plate intercepted click, returned {hit_label}"

    wire_y = 160.0
    w = scene.add_wire(((100.0, wire_y), (300.0, wire_y)))
    wire_hit_pt = QPointF(200.0, wire_y)
    hit_wire = scene.itemAt(wire_hit_pt, QTransform())
    assert hit_wire is w, f"Wire behind label was blocked by label plate; got {hit_wire} instead of {w}"

    r2 = scene.place_new_component("resistor", QPointF(500, 500), rotation_deg=90)
    _lbl_rect2, val_rect2, _ = r2._upright_label_and_value_rects()
    val_scene_pt = r2.pos() + val_rect2.center()

    hit_val = scene.itemAt(val_scene_pt, QTransform())
    assert hit_val is None, f"Empty value label plate intercepted click, returned {hit_val}"

    w2 = scene.add_wire(((540.0, 400.0), (540.0, 600.0)))
    test_pt = QPointF(540.0, 510.0)
    assert val_rect2.contains(test_pt - r2.pos()), "test_pt not inside val_rect2"
    hit_w2 = scene.itemAt(test_pt, QTransform())
    assert hit_w2 is w2, f"Wire behind value label was blocked; got {hit_w2} instead of {w2}"
