"""Item 0: quick checks from the last report.

0a. Drawing (terminal dots), hit areas, snapping, terminal positions and the netlist
    all take terminal positions from `transform_terminal_position`. Compared for all
    11 part types and all 8 orientations.
0b. A deliberate 40 px drag moves a part by exactly two grid cells; a 3 px jitter
    moves it by 0 px.
"""

from __future__ import annotations

import numpy as np


def test_0a_all_terminal_consumers_share_transform_terminal_position(qapp) -> None:
    """Drawn terminal dots, shape(), snapping, item positions and netlist specs agree."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    from circuitsim.app.themes import get_theme_palette
    from circuitsim.canvas.connectivity import PlacedComponentSpec
    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.canvas.symbol_geometry import (
        DEFAULT_IEC_SYMBOLS_DIR,
        load_all_iec_metadata,
        transform_terminal_position,
    )
    from circuitsim.canvas.symbol_renderer import SymbolLibrary

    lib = SymbolLibrary()
    catalog = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
    center = (200.0, 200.0)

    def dot_centroid(img: QImage, rgb: tuple[int, int, int]):
        w, h = img.width(), img.height()
        arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape((h, img.bytesPerLine() // 4, 4))
        b = arr[:, :w, 0].astype(np.int16)
        g = arr[:, :w, 1].astype(np.int16)
        r = arr[:, :w, 2].astype(np.int16)
        mask = (np.abs(r - rgb[0]) <= 8) & (np.abs(g - rgb[1]) <= 8) & (np.abs(b - rgb[2]) <= 8)
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return None
        return (float((xs + 0.5).mean()), float((ys + 0.5).mean()), int(len(xs)))

    checked = 0
    for ptype, meta in catalog.items():
        for rot in (0, 90, 180, 270):
            for flip in (False, True):
                scene = CircuitScene(lib)
                item = scene.place_new_component(
                    ptype, QPointF(*center), rotation_deg=rot, flipped_h=flip
                )
                tag = f"{ptype} rot={rot} flip={flip}"
                expected = {
                    t.name: transform_terminal_position(
                        t.grid_pos, center, rotation_deg=rot, flipped_h=flip
                    )
                    for t in meta.terminals
                }

                assert item.terminal_scene_positions() == expected, tag

                spec = item.to_placed_spec()
                resolved = spec.resolve_terminals_px(catalog)
                for name, (ex, ey) in expected.items():
                    assert resolved[name] == (int(round(ex)), int(round(ey))), tag
                bare = PlacedComponentSpec(
                    component=item.component, center_px=center,
                    rotation_deg=rot, flipped_h=flip,
                )
                assert bare.resolve_terminals_px(catalog) == resolved, tag

                shape = item.shape()
                for name, (ex, ey) in expected.items():
                    assert shape.contains(item.mapFromScene(QPointF(ex, ey))), (tag, name)

                for name, (ex, ey) in expected.items():
                    hit = scene.find_terminal_near(QPointF(ex + 9.0, ey))
                    assert hit is not None and hit[0] is item and hit[1] == name, (tag, name)
                    assert hit[2] == (int(round(ex)), int(round(ey))), (tag, name)

                pal = get_theme_palette(item.theme)
                col = pal.terminal_dot.lstrip("#")
                rgb = (int(col[0:2], 16), int(col[2:4], 16), int(col[4:6], 16))
                img = QImage(240, 240, QImage.Format.Format_ARGB32)
                img.fill(Qt.GlobalColor.black)
                p = QPainter(img)
                p.translate(120.0, 120.0)
                item.paint(p, QStyleOptionGraphicsItem(), None)
                p.end()

                for name, (ex, ey) in expected.items():
                    lx, ly = ex - center[0] + 120.0, ey - center[1] + 120.0
                    crop = img.copy(int(lx) - 10, int(ly) - 10, 20, 20)
                    res = dot_centroid(crop, rgb)
                    assert res is not None, (tag, name, "no drawn terminal dot found")
                    cx, cy, _n = res
                    cx += int(lx) - 10
                    cy += int(ly) - 10
                    assert abs(cx - lx) <= 1.0 and abs(cy - ly) <= 1.0, (
                        tag, name, "drawn dot", (cx, cy), "expected", (lx, ly)
                    )
                checked += 1

    assert checked == 11 * 8, checked


def test_0b_deliberate_drag_moves_two_cells_and_jitter_moves_nothing(qapp) -> None:
    """40 px drag = +2 grid cells (one undo command); 3 px jitter = 0 px (no command)."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtTest import QTest
    from circuitsim.app.main_window import MainWindow

    win = MainWindow()
    win.resize(1100, 800)
    win.show()
    qapp.processEvents()

    scene, view = win.circuit_scene, win.circuit_view
    vp = view.viewport()
    assert abs(view.transform().m11() - 1.0) < 1e-9
    r = scene.place_new_component("resistor", QPointF(-100.0, 0.0))
    qapp.processEvents()
    start = (r.pos().x(), r.pos().y())
    stack = scene.undo_stack
    base_count = stack.count()

    def press_move_release(delta: tuple[int, int]) -> None:
        p0 = view.mapFromScene(r.pos())
        QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0)
        qapp.processEvents()
        QTest.mouseMove(vp, p0 + QPoint(*delta))
        qapp.processEvents()
        QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0 + QPoint(*delta))
        qapp.processEvents()

    for delta in ((3, 0), (-3, 0), (0, 3), (0, -3), (2, 1)):
        press_move_release(delta)
        assert (r.pos().x(), r.pos().y()) == start, ("jitter moved the part", delta, r.pos())
        assert stack.count() == base_count, ("jitter pushed an undo command", delta)

    press_move_release((40, 0))
    assert (r.pos().x(), r.pos().y()) == (start[0] + 40.0, start[1]), r.pos()
    assert stack.count() == base_count + 1

    press_move_release((0, 40))
    assert (r.pos().x(), r.pos().y()) == (start[0] + 40.0, start[1] + 40.0), r.pos()
    assert stack.count() == base_count + 2
