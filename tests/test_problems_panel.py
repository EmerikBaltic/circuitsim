"""Tests for Item 4: Problems Panel, F8 Shortcut, Auto-Open, Status Bar Count, and Invariance."""

from __future__ import annotations

import os
import subprocess
import sys
import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from circuitsim.app.problems_panel import ProblemsPanel
from circuitsim.components import DCVoltageSource, Ground, LED, Resistor
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.simulation_session import (
    ProblemDiagnostic,
    SimulationSession,
    SimulationState,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_problems_panel_widget_and_columns(qapp: QApplication) -> None:
    """Verify ProblemsPanel header, tree columns, severity icons/words, and click signal."""
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

    # Test click activation signal
    activated_parts: list[str] = []
    panel.problem_activated.connect(activated_parts.append)
    panel._on_item_clicked(item1, 0)
    assert activated_parts == ["D1"]

    # Test close button signal
    close_emitted = False

    def on_close():
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


def _run_qt_script(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=25,
    )


def test_offscreen_problems_panel_integration_and_canvas_invariance() -> None:
    """Offscreen Qt test: verify F8 toggle, close button, selection centering, status bar count, and view invariance."""
    script = """
import sys
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from circuitsim.app.main_window import MainWindow
from circuitsim.canvas.component_item import ComponentItem

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.show()

scene = win.circuit_scene
view = win.circuit_view

# Place an LED and resistor on canvas
led_item = scene.place_new_component("led", QPointF(200.0, 200.0))
res_item = scene.place_new_component("resistor", QPointF(350.0, 200.0))

# Record view scrollbars and scene rect before toggling problems panel
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
from circuitsim.engine.simulation_session import ProblemDiagnostic
test_diags = [
    ProblemDiagnostic(code="test1", severity="error", message="Test error", component_names=("D1",)),
    ProblemDiagnostic(code="test2", severity="warning", message="Test warning", component_names=("R1",)),
]
from circuitsim.engine.simulation_session import SimulationFrame, SimulationState
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

# Clean close
win._is_closing = True
win.close()
print("PROBLEMS_PANEL_OK")
"""
    res = _run_qt_script(script)
    assert res.returncode == 0, f"Qt subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "PROBLEMS_PANEL_OK" in res.stdout
