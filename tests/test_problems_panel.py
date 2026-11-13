"""Tests for Item 4: Problems Panel, F8 Shortcut, Auto-Open, Status Bar Count, and Invariance."""

from __future__ import annotations

import numpy as np

from circuitsim.components import Ammeter, DCVoltageSource, Ground, LED, Lightbulb, Resistor, Voltmeter
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.simulation_session import (
    ProblemDiagnostic,
    SimulationFrame,
    SimulationSession,
    SimulationState,
)


def _image_array(img) -> np.ndarray:
    from PySide6.QtGui import QImage

    rgba = img.convertToFormat(QImage.Format.Format_ARGB32)
    arr = np.frombuffer(rgba.constBits(), dtype=np.uint8)
    return arr.reshape((rgba.height(), rgba.width(), 4)).copy()


def test_problems_panel_widget_and_columns(qapp) -> None:
    """Verify ProblemsPanel header, tree columns, severity icons/words, and click signal."""
    from circuitsim.app.problems_panel import ProblemsPanel

    panel = ProblemsPanel()
    assert panel.title_label.text() == "Problems"
    assert panel.close_btn is not None

    diags = [
        ProblemDiagnostic(
            code="no_ground",
            severity="error",
            message="No ground connected: circuit requires reference; Add a Ground part",
            component_names=("V1", "R1"),
        ),
        ProblemDiagnostic(
            code="led_over_current",
            severity="warning",
            message="LED D1 over-current: current 35 mA exceeds max 30 mA; increase resistor",
            component_names=("D1",),
        ),
    ]

    panel.update_diagnostics(diags)
    assert panel.count_label.text() == "(2)"
    assert panel.tree.topLevelItemCount() == 2

    item0 = panel.tree.topLevelItem(0)
    assert item0.text(0) == "Error"
    assert "No ground connected" in item0.text(1)
    assert "V1, R1" in item0.text(2)
    assert not item0.icon(0).isNull()

    item1 = panel.tree.topLevelItem(1)
    assert item1.text(0) == "Warning"
    assert "LED D1 over-current" in item1.text(1)
    assert "D1" in item1.text(2)
    assert not item1.icon(0).isNull()

    activated_parts: list[str] = []
    panel.problem_activated.connect(activated_parts.append)
    panel._on_item_clicked(item1, 0)
    assert activated_parts == ["D1"]

    close_emitted = False

    def on_close() -> None:
        nonlocal close_emitted
        close_emitted = True

    panel.close_requested.connect(on_close)
    panel.close_btn.click()
    assert close_emitted is True


def test_structured_diagnostics_what_why_how() -> None:
    """Verify diagnostics are written in what/why/how-to-fix style with component names and numbers."""
    # 1. Connected circuit with LED over-current
    c = Circuit()
    c.add(DCVoltageSource("V1", "1", "0", voltage=5.0))
    c.add(Resistor("R1", "1", "2", resistance=80.0))
    # LED with 80 ohm resistor -> I = (5-2)/80 = 37.5 mA > 30 mA max
    c.add(LED("D1", "2", "0", forward_voltage=2.0, max_current=0.03))
    c.add(Ground("GND", "0"))

    session = SimulationSession(circuit=c)
    frame = session.start()

    codes = {d.code: d for d in frame.diagnostics}
    assert "led_over_current" in codes
    diag_led = codes["led_over_current"]
    assert "D1" in diag_led.message
    assert "exceeds maximum rating" in diag_led.message
    assert "increase series resistor" in diag_led.message

    # 2. Topology error: floating node
    c_float = Circuit()
    c_float.add(DCVoltageSource("V1", "1", "0", voltage=5.0))
    c_float.add(Resistor("R_float", "foo", "bar", resistance=100.0))
    c_float.add(Ground("GND", "0"))
    session_float = SimulationSession(circuit=c_float)
    frame_float = session_float.start()
    assert frame_float.state == SimulationState.ERROR
    codes_float = {d.code: d for d in frame_float.diagnostics}
    assert "floating_node" in codes_float
    diag_float = codes_float["floating_node"]
    assert "is floating" in diag_float.message
    assert "no DC path to ground" in diag_float.message
    assert "tied to ground" in diag_float.message


def test_offscreen_problems_panel_integration_and_canvas_invariance(qapp) -> None:
    """Offscreen Qt test: verify F8 toggle, close button, selection centering, status bar count, and view invariance."""
    from PySide6.QtCore import QPointF
    from circuitsim.app.main_window import MainWindow

    win = MainWindow()
    win.show()

    scene = win.circuit_scene
    view = win.circuit_view

    led_item = scene.place_new_component("led", QPointF(200.0, 200.0))
    scene.place_new_component("resistor", QPointF(350.0, 200.0))

    h_before = view.horizontalScrollBar().value()
    v_before = view.verticalScrollBar().value()
    rect_before = (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height())
    zoom_before = view._zoom_factor

    # 1. Toggle problems panel with F8
    assert win.problems_dock.isHidden()
    win.action_view_problems.trigger()
    assert win.problems_dock.isVisible()
    assert win.action_view_problems.isChecked()

    # Verify view has NOT shifted (NoAnchor)
    assert view.horizontalScrollBar().value() == h_before, "Horizontal scrollbar shifted on panel open!"
    assert view.verticalScrollBar().value() == v_before, "Vertical scrollbar shifted on panel open!"
    assert (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height()) == rect_before
    assert view._zoom_factor == zoom_before

    # 2. Close problems panel via close button
    win.problems_dock.panel.close_btn.click()
    assert win.problems_dock.isHidden()
    assert not win.action_view_problems.isChecked()

    # Verify view still has NOT shifted
    assert view.horizontalScrollBar().value() == h_before, "Horizontal scrollbar shifted on panel close!"
    assert view.verticalScrollBar().value() == v_before, "Vertical scrollbar shifted on panel close!"

    # 3. Test problem selection and view centering
    win.problems_dock.show()
    win._on_problem_part_selected(led_item.component.name)
    assert led_item.isSelected()

    # 4. Status bar short count test
    test_diags = [
        ProblemDiagnostic(code="test1", severity="error", message="Test error", component_names=("D1",)),
        ProblemDiagnostic(code="test2", severity="warning", message="Test warning", component_names=("R1",)),
    ]
    frame = SimulationFrame(
        state=SimulationState.RUNNING,
        sim_time=0.1,
        dt=1e-3,
        speed_ratio=1.0,
        node_voltages={},
        components={},
        diagnostics=tuple(test_diags),
    )
    win._on_simulation_frame(frame)
    assert win.status_warnings.text() == "2 problems"

    win._is_closing = True
    win.close()


def test_problems_panel_close_button_visual_and_accessible_in_both_themes(qapp) -> None:
    """Item 2: Verify close button text/icon, min size 24x24, tooltip, accessible name,

    visibility in dark and light themes, zero canvas shift on click, and severity icons.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QImage
    from circuitsim.app.main_window import MainWindow
    from circuitsim.app.problems_panel import make_severity_icon
    from circuitsim.app.themes import ThemeMode

    win = MainWindow()
    win.resize(1000, 700)
    win.show()

    panel = win.problems_dock.panel
    btn = panel.close_btn

    # 1. Properties
    assert btn.minimumWidth() >= 24, f"Expected min width >= 24, got {btn.minimumWidth()}"
    assert btn.minimumHeight() >= 24, f"Expected min height >= 24, got {btn.minimumHeight()}"
    assert btn.toolTip() == "Close (F8)", f"Expected tooltip 'Close (F8)', got '{btn.toolTip()}'"
    assert btn.accessibleName() == "Close (F8)", f"Expected accessibleName 'Close (F8)', got '{btn.accessibleName()}'"
    assert (bool(btn.text().strip()) or not btn.icon().isNull()), "Button must have non-empty text or non-null icon"
    assert "✕" in btn.text(), f"Expected '✕' in button text, got '{btn.text()}'"

    # 2. Render in both Dark and Light themes and assert button pixels differ from background
    for theme in [ThemeMode.DARK, ThemeMode.LIGHT]:
        win.apply_theme(theme)
        win.problems_dock.show()
        qapp.processEvents()

        btn_size = btn.size()
        img = QImage(btn_size, QImage.Format.Format_ARGB32)
        bg_col = QColor("#161B22" if theme == ThemeMode.DARK else "#FFFFFF")
        img.fill(bg_col)
        btn.render(img)

        arr = _image_array(img)
        bg_bgra = np.array([bg_col.blue(), bg_col.green(), bg_col.red(), bg_col.alpha()], dtype=np.uint8)
        differing_pixels = int(np.any(arr != bg_bgra, axis=2).sum())
        assert differing_pixels > 0, f"Close button pixels did not differ from background in {theme.value} theme!"

    # 3. Canvas shift invariance on button click
    scene = win.circuit_scene
    view = win.circuit_view
    scene.place_new_component("resistor", QPointF(200.0, 200.0))

    h_val = view.horizontalScrollBar().value()
    v_val = view.verticalScrollBar().value()
    s_rect = (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height())

    assert win.problems_dock.isVisible()
    btn.click()
    qapp.processEvents()
    assert win.problems_dock.isHidden(), "ProblemsDock should be hidden after clicking close button"
    assert view.horizontalScrollBar().value() == h_val, "Canvas horizontal scroll shifted on close!"
    assert view.verticalScrollBar().value() == v_val, "Canvas vertical scroll shifted on close!"
    assert (scene.sceneRect().x(), scene.sceneRect().y(), scene.sceneRect().width(), scene.sceneRect().height()) == s_rect

    # 4. Severity icons verification (error, warning, info)
    for sev in ["error", "warning", "info"]:
        icon = make_severity_icon(sev)
        assert not icon.isNull(), f"Severity icon for '{sev}' is null"
        pm = icon.pixmap(16, 16)
        assert not pm.isNull()
        arr_sev = _image_array(pm.toImage())
        colored_pixels = int((arr_sev[:, :, 3] > 0).sum())
        assert colored_pixels >= 20, f"Severity icon for '{sev}' has too few pixels ({colored_pixels})"

    win._is_closing = True
    win.close()


def test_no_blank_buttons_or_icons_in_both_themes(qapp) -> None:
    """Scan every dialog, panel, toolbar button, and menu/severity icon in dark and light themes."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QAbstractButton, QMenu
    from circuitsim.app.main_window import MainWindow
    from circuitsim.app.problems_panel import ProblemsPanel, make_severity_icon
    from circuitsim.app.themes import ThemeMode
    from circuitsim.canvas.export import ExportOptionsDialog
    from circuitsim.dialogs.preferences_dialog import PreferencesDialog
    from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog

    def has_non_uniform_pixels(img: QImage) -> bool:
        if img.isNull() or img.width() == 0 or img.height() == 0:
            return False
        arr = _image_array(img)
        return bool(np.any(arr != arr[0, 0]))

    def assert_button_not_blank(btn: QAbstractButton, ctx: str) -> None:
        if btn.objectName() in ("qt_toolbar_ext_button", "qt_dockwidget_closebutton", "qt_dockwidget_floatbutton"):
            return
        txt = btn.text().strip()
        icon = btn.icon()
        btn.ensurePolished()
        if btn.width() <= 0 or btn.height() <= 0:
            btn.resize(btn.sizeHint().expandedTo(QSize(24, 24)))
        img = btn.grab().toImage()
        assert has_non_uniform_pixels(img), f"Blank button in {ctx}: {btn.objectName() or type(btn).__name__}"
        assert txt or not icon.isNull() or has_non_uniform_pixels(img), f"Button has no text, icon, or custom paint: {ctx}"

    for theme_name in ("dark", "light"):
        win = MainWindow()
        win.apply_theme(ThemeMode(theme_name))
        win.show()
        qapp.processEvents()

        panel = win.problems_dock.findChild(ProblemsPanel)
        assert panel is not None
        panel.update_diagnostics([
            ProblemDiagnostic(code="no_ground", severity="error", message="No ground", component_names=("V1",)),
            ProblemDiagnostic(code="ammeter_in_parallel", severity="warning", message="Ammeter parallel", component_names=("A1",)),
        ])
        win.problems_dock.show()
        qapp.processEvents()

        for btn in win.findChildren(QAbstractButton):
            if btn.isVisible():
                assert_button_not_blank(btn, f"MainWindow({theme_name})")

        for sev in ("error", "warning", "info"):
            ic = make_severity_icon(sev)
            assert not ic.isNull()
            assert has_non_uniform_pixels(ic.pixmap(16, 16).toImage()), f"Blank severity icon {sev}"

        for menu in win.menuBar().findChildren(QMenu):
            for act in menu.actions():
                if not act.icon().isNull():
                    assert has_non_uniform_pixels(act.icon().pixmap(16, 16).toImage()), f"Blank menu icon {act.text()}"

        for comp in (LED("D1", "1", "0"), Voltmeter("VM1", "1", "0"), Ammeter("A1", "1", "0"), Resistor("R1", "1", "0"), Lightbulb("L1", "1", "0")):
            dlg = QuickValueDialog(comp)
            dlg.show()
            qapp.processEvents()
            for btn in dlg.findChildren(QAbstractButton):
                if btn.isVisible():
                    assert_button_not_blank(btn, f"QuickValueDialog({type(comp).__name__}, {theme_name})")
            dlg.close()

        for dlg in (PreferencesDialog(win.settings), ExportOptionsDialog(ThemeMode(theme_name))):
            dlg.show()
            qapp.processEvents()
            for btn in dlg.findChildren(QAbstractButton):
                if btn.isVisible():
                    assert_button_not_blank(btn, f"{type(dlg).__name__}({theme_name})")
            dlg.close()

        win.circuit_scene.undo_stack.setClean()
        win.close()
        qapp.processEvents()
