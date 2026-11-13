"""Tests for Item 6: Comprehensive LED Integration Test Suite."""

from __future__ import annotations

import math


def test_led_full_lifecycle_and_problems_panel_integration(qapp) -> None:
    """Run full offscreen integration suite covering all Item 6 requirements."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter
    from circuitsim.app.main_window import MainWindow
    from circuitsim.canvas.symbol_geometry import led_marks
    from circuitsim.components import DCVoltageSource, Ground, LED
    from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog
    from circuitsim.engine.netlist import Circuit
    from circuitsim.engine.simulation_session import SimulationSession
    from circuitsim.io.circ_serializer import (
        CircuitDocument,
        PlacedComponentSpec,
        dumps_document,
        loads_document,
    )

    win = MainWindow()
    win.show()

    scene = win.circuit_scene
    view = win.circuit_view

    tree = win.palette_widget.tree
    cat_found = False
    led_item_found = False
    for i in range(tree.topLevelItemCount()):
        cat = tree.topLevelItem(i)
        if cat.text(0) == "Semiconductors":
            cat_found = True
            for j in range(cat.childCount()):
                child = cat.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == "led":
                    led_item_found = True
                    break

    assert cat_found, "Missing 'Semiconductors' category in palette tree"
    assert led_item_found, "Missing 'led' item under 'Semiconductors' category"

    initial_item_count = len(scene.placed_items)
    win.palette_widget.component_activated.emit("led")
    assert len(scene.placed_items) == initial_item_count + 1, "LED was not placed on canvas via palette"

    led_item = scene.placed_items[-1]
    assert isinstance(led_item.component, LED), f"Expected LED, got {type(led_item.component)}"

    pos = led_item.pos()
    assert math.isclose(pos.x() % 20.0, 0.0, abs_tol=1e-5), f"X pos {pos.x()} not snapped to 20 px grid"
    assert math.isclose(pos.y() % 20.0, 0.0, abs_tol=1e-5), f"Y pos {pos.y()} not snapped to 20 px grid"

    meta = led_item.metadata
    t_anode = next(t for t in meta.terminals if t.name == "anode")
    t_cathode = next(t for t in meta.terminals if t.name == "cathode")
    assert meta.terminal_in_svg_viewbox(t_anode) == (0.0, 20.0)
    assert meta.terminal_in_svg_viewbox(t_cathode) == (80.0, 20.0)
    assert t_anode.local_px == (-40.0, 0.0)
    assert t_cathode.local_px == (40.0, 0.0)

    scene_terms = led_item.terminal_scene_positions()
    assert "anode" in scene_terms and "cathode" in scene_terms
    assert math.isclose(scene_terms["anode"][0], pos.x() - 40.0, abs_tol=1e-3)
    assert math.isclose(scene_terms["anode"][1], pos.y(), abs_tol=1e-3)
    assert math.isclose(scene_terms["cathode"][0], pos.x() + 40.0, abs_tol=1e-3)
    assert math.isclose(scene_terms["cathode"][1], pos.y(), abs_tol=1e-3)

    scene.clearSelection()
    led_item.setSelected(True)
    dlg = QuickValueDialog(
        led_item.component,
        on_apply=lambda p, s: scene.edit_component_parameters(led_item, p, show_value=s),
        parent=win,
    )
    assert dlg.led_color_combo is not None
    assert dlg.led_color_combo.currentText() == "Red"

    dlg.led_color_combo.setCurrentText("Blue")
    assert math.isclose(float(dlg.inputs["forward_voltage"].text()), 3.2, abs_tol=1e-3)
    assert dlg._apply_current_inputs() is True
    dlg.accept()

    assert led_item.component.color_name == "Blue"
    assert math.isclose(led_item.component.forward_voltage, 3.2, abs_tol=1e-3)

    scene.undo_stack.undo()
    assert led_item.component.color_name == "Red"
    assert math.isclose(led_item.component.forward_voltage, 2.0, abs_tol=1e-3)

    scene.undo_stack.redo()
    assert led_item.component.color_name == "Blue"
    assert math.isclose(led_item.component.forward_voltage, 3.2, abs_tol=1e-3)

    c = Circuit()
    c.add(DCVoltageSource("V1", "1", "0", voltage=5.0))
    c.add(LED("D_rev", "0", "1", forward_voltage=2.0))
    c.add(Ground("GND", "0"))

    session = SimulationSession(circuit=c)
    frame = session.start()
    diag_codes = {d.code: d for d in frame.diagnostics}
    assert "led_reversed" in diag_codes
    assert "led_no_resistor" in diag_codes
    assert "LED reversed: cathode is at a higher potential than anode" in diag_codes["led_reversed"].message
    assert "LED has no current limiting resistor" in diag_codes["led_no_resistor"].message

    win._on_simulation_frame(frame)
    assert win.problems_dock.isHidden()
    win.action_view_problems.trigger()
    assert win.problems_dock.isVisible()
    assert win.action_view_problems.isChecked()

    panel = win.problems_dock.panel
    assert panel.tree.topLevelItemCount() == 2
    item_codes_in_tree = [panel.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole).code for i in range(2)]
    assert "led_reversed" in item_codes_in_tree
    assert "led_no_resistor" in item_codes_in_tree

    h_scroll_0 = view.horizontalScrollBar().value()
    v_scroll_0 = view.verticalScrollBar().value()
    scene_rect_0 = (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height())
    zoom_0 = view._zoom_factor

    panel.close_btn.click()
    assert win.problems_dock.isHidden()
    assert not win.action_view_problems.isChecked()
    assert view.horizontalScrollBar().value() == h_scroll_0
    assert view.verticalScrollBar().value() == v_scroll_0
    assert (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height()) == scene_rect_0
    assert view._zoom_factor == zoom_0

    win.action_view_problems.trigger()
    assert win.problems_dock.isVisible()
    assert win.action_view_problems.isChecked()
    assert view.horizontalScrollBar().value() == h_scroll_0
    assert view.verticalScrollBar().value() == v_scroll_0
    assert (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height()) == scene_rect_0
    assert view._zoom_factor == zoom_0

    win.action_view_problems.trigger()
    assert win.problems_dock.isHidden()

    for rot in (0, 90, 180, 270):
        for flip in (False, True):
            marks = led_marks(rotation_deg=rot, flipped_h=flip, center_px=(0.0, 0.0))
            flat_x, flat_y = marks["flat"]
            ax, ay = marks["anode_terminal"]
            kx, ky = marks["cathode_terminal"]
            d_k = math.hypot(flat_x - kx, flat_y - ky)
            d_a = math.hypot(flat_x - ax, flat_y - ay)
            assert d_k < d_a
            assert math.isclose(d_k, 26.0, abs_tol=1e-3)
            assert math.isclose(d_a, 54.0, abs_tol=1e-3)

            img = QImage(120, 120, QImage.Format.Format_ARGB32)
            img.fill(0)
            painter = QPainter(img)
            pix = win.symbol_library.create_palette_icon("led", theme=win.theme, size=(80, 40)).pixmap(80, 40)
            assert not pix.isNull()
            painter.end()

    d_test = LED(
        "D_save", "n1", "0",
        forward_voltage=3.2, rated_current=0.025, max_current=0.035,
        color_name="Blue", color="#007AFF", burnout_enabled=True, burnout_current=0.045,
    )
    spec = PlacedComponentSpec(component=d_test, center_px=(160.0, 220.0), rotation_deg=180, flipped_h=True)
    loaded_doc = loads_document(dumps_document(CircuitDocument(placed=[spec], wires=[], junctions=[])))
    assert len(loaded_doc.placed) == 1
    loaded_led = loaded_doc.placed[0].component
    assert isinstance(loaded_led, LED)
    assert loaded_led.name == "D_save"
    assert math.isclose(loaded_led.forward_voltage, 3.2, abs_tol=1e-5)
    assert math.isclose(loaded_led.rated_current, 0.025, abs_tol=1e-5)
    assert math.isclose(loaded_led.max_current, 0.035, abs_tol=1e-5)
    assert loaded_led.color_name == "Blue"
    assert loaded_led.color == "#007AFF"
    assert loaded_led.burnout_enabled is True
    assert math.isclose(loaded_led.burnout_current, 0.045, abs_tol=1e-5)
