"""Tests for 10 px wire terminal snapping, hover highlighting, and connection guarantees."""

from __future__ import annotations


def test_wire_snapping_all_orientations_and_distances(qapp) -> None:
    """Wire ending and starting at 0, 1, 5, 8, 9 px connects; at 11 px does not."""
    from PySide6.QtCore import QPointF
    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.canvas.symbol_renderer import SymbolLibrary

    lib = SymbolLibrary()

    for rot in (0, 90, 180, 270):
        for flip in (False, True):
            scene = CircuitScene(lib)
            r1 = scene.place_new_component("resistor", QPointF(200, 200), rotation_deg=rot, flipped_h=flip)
            term_a = r1.terminal_scene_positions_px()["a"]

            for dist in (0, 1, 5, 8, 9):
                scene.clearSelection()
                end_candidate = (term_a[0] + dist, term_a[1])

                hover = scene.update_hover_highlight(QPointF(float(end_candidate[0]), float(end_candidate[1])))
                assert hover == term_a, f"Hover highlight failed at dist={dist} px for rot={rot} flip={flip}"

                w = scene.add_wire(((100.0, 100.0), (float(end_candidate[0]), float(end_candidate[1]))))
                assert w is not None
                assert w.points[-1] == term_a, f"Expected wire end {term_a}, got {w.points[-1]} at dist={dist}"
                scene.removeItem(w)

            end_too_far = (term_a[0] + 11, term_a[1])
            hover_far = scene.update_hover_highlight(QPointF(float(end_too_far[0]), float(end_too_far[1])))
            assert hover_far is None, f"Hover highlight unexpectedly triggered at 11 px for rot={rot} flip={flip}"
            w_far = scene.add_wire(((100.0, 100.0), (float(end_too_far[0]), float(end_too_far[1]))))
            assert w_far is not None
            assert w_far.points[-1] != term_a, f"Wire at 11 px unexpectedly snapped to terminal {term_a}"
            scene.removeItem(w_far)

            for dist in (0, 1, 5, 8, 9):
                start_candidate = (term_a[0] + dist, term_a[1])
                w_start = scene.add_wire(((float(start_candidate[0]), float(start_candidate[1])), (300.0, 300.0)))
                assert w_start is not None
                assert w_start.points[0] == term_a, f"Expected wire start {term_a}, got {w_start.points[0]} at dist={dist}"
                scene.removeItem(w_start)

            start_far = (term_a[0] + 11, term_a[1])
            w_start_far = scene.add_wire(((float(start_far[0]), float(start_far[1])), (300.0, 300.0)))
            assert w_start_far is not None
            assert w_start_far.points[0] != term_a, f"Wire start at 11 px unexpectedly snapped to {term_a}"
            scene.removeItem(w_start_far)


def test_nearest_terminal_selection_and_grid_alignment(qapp) -> None:
    """When multiple terminals are within range, the closest terminal is chosen."""
    from PySide6.QtCore import QPointF
    from circuitsim.canvas.scene import CircuitScene
    from circuitsim.canvas.symbol_renderer import SymbolLibrary

    lib = SymbolLibrary()
    scene = CircuitScene(lib)

    r1 = scene.place_new_component("resistor", QPointF(200, 200))
    r2 = scene.place_new_component("resistor", QPointF(300, 200))
    term1 = r1.terminal_scene_positions_px()["b"]
    term2 = r2.terminal_scene_positions_px()["a"]

    hit1 = scene.find_terminal_near(QPointF(244, 200))
    assert hit1 is not None and hit1[2] == term1

    hit2 = scene.find_terminal_near(QPointF(256, 200))
    assert hit2 is not None and hit2[2] == term2

    assert r1.pos().x() % 20 == 0 and r1.pos().y() % 20 == 0
    assert r2.pos().x() % 20 == 0 and r2.pos().y() % 20 == 0
