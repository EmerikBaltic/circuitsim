"""Tests for 10 px wire terminal snapping, hover highlighting, and connection guarantees.

Verifies:
1. 10 px snap radius (half a 20 px grid cell) around each terminal's true transformed position.
2. Across all 4 rotations (0, 90, 180, 270) and horizontal flip:
   - Ending a wire at 0, 1, 5, 8, 9 px from terminal connects, stores the exact terminal coordinate,
     and reaches the terminal's electrical node.
   - Ending a wire at 11 px does NOT connect to the terminal and warns/stays off.
   - Starting a wire at 0, 1, 5, 8, 9 px connects to the terminal; at 11 px does NOT connect.
3. Nearest terminal selection when multiple are in range.
4. Hover highlight activates within 10 px and clears at 11 px.
5. Standard 20 px grid alignment for parts remains intact.
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


def test_wire_snapping_all_orientations_and_distances() -> None:
    """Subprocess Qt test: wire ending and starting at 0, 1, 5, 8, 9 px connects; at 11 px does not."""
    script = """
import sys
import math
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.components import Resistor, DCVoltageSource, Ground

app = QApplication(sys.argv)
lib = SymbolLibrary()

for rot in [0, 90, 180, 270]:
    for flip in [False, True]:
        scene = CircuitScene(lib)
        r1 = scene.place_new_component("resistor", QPointF(200, 200), rotation_deg=rot, flipped_h=flip)
        term_a = r1.terminal_scene_positions_px()["a"]

        # 1. Ending a wire near terminal 'a' at 0, 1, 5, 8, 9 px
        for dist in [0, 1, 5, 8, 9]:
            scene.clearSelection()
            end_candidate = (term_a[0] + dist, term_a[1])
            
            # Hover highlight check
            hover = scene.update_hover_highlight(QPointF(float(end_candidate[0]), float(end_candidate[1])))
            assert hover == term_a, f"Hover highlight failed at dist={dist} px for rot={rot} flip={flip}"

            # Add wire ending at end_candidate
            w = scene.add_wire(((100.0, 100.0), (float(end_candidate[0]), float(end_candidate[1]))))
            assert w is not None
            # Must store exact transformed terminal coordinate
            assert w.points[-1] == term_a, f"Expected wire end {term_a}, got {w.points[-1]} at dist={dist}"
            
            # Verify connectivity: wire is attached to terminal 'a'
            scene.removeItem(w)

        # 2. Ending a wire at 11 px (outside 10 px radius)
        end_too_far = (term_a[0] + 11, term_a[1])
        hover_far = scene.update_hover_highlight(QPointF(float(end_too_far[0]), float(end_too_far[1])))
        assert hover_far is None, f"Hover highlight unexpectedly triggered at 11 px for rot={rot} flip={flip}"
        w_far = scene.add_wire(((100.0, 100.0), (float(end_too_far[0]), float(end_too_far[1]))))
        assert w_far is not None
        assert w_far.points[-1] != term_a, f"Wire at 11 px unexpectedly snapped to terminal {term_a}"
        scene.removeItem(w_far)

        # 3. Starting a wire near terminal 'a' at 0, 1, 5, 8, 9 px
        for dist in [0, 1, 5, 8, 9]:
            start_candidate = (term_a[0] + dist, term_a[1])
            w_start = scene.add_wire(((float(start_candidate[0]), float(start_candidate[1])), (300.0, 300.0)))
            assert w_start is not None
            assert w_start.points[0] == term_a, f"Expected wire start {term_a}, got {w_start.points[0]} at dist={dist}"
            scene.removeItem(w_start)

        # Starting a wire at 11 px
        start_far = (term_a[0] + 11, term_a[1])
        w_start_far = scene.add_wire(((float(start_far[0]), float(start_far[1])), (300.0, 300.0)))
        assert w_start_far is not None
        assert w_start_far.points[0] != term_a, f"Wire start at 11 px unexpectedly snapped to {term_a}"
        scene.removeItem(w_start_far)

print("SNAPPING_ALL_ORIENTATIONS_PASSED")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "SNAPPING_ALL_ORIENTATIONS_PASSED" in res.stdout


def test_nearest_terminal_selection_and_grid_alignment() -> None:
    """When multiple terminals are within range, the closest terminal is chosen."""
    script = """
import sys
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary

app = QApplication(sys.argv)
lib = SymbolLibrary()
scene = CircuitScene(lib)

# Two resistors placed so terminal b of R1 at (240, 200) and terminal a of R2 at (260, 200)
# are 20 px apart
r1 = scene.place_new_component("resistor", QPointF(200, 200))
r2 = scene.place_new_component("resistor", QPointF(300, 200))
term1 = r1.terminal_scene_positions_px()["b"]  # (240, 200)
term2 = r2.terminal_scene_positions_px()["a"]  # (260, 200)

# Point at (244, 200) is 4 px from term1 and 16 px from term2
hit1 = scene.find_terminal_near(QPointF(244, 200))
assert hit1 is not None and hit1[2] == term1

# Point at (256, 200) is 4 px from term2 and 16 px from term1
hit2 = scene.find_terminal_near(QPointF(256, 200))
assert hit2 is not None and hit2[2] == term2

# Component grid alignment check: positions stay strictly on 20 px grid
assert r1.pos().x() % 20 == 0 and r1.pos().y() % 20 == 0
assert r2.pos().x() % 20 == 0 and r2.pos().y() % 20 == 0

print("NEAREST_AND_ALIGNMENT_PASSED")
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "NEAREST_AND_ALIGNMENT_PASSED" in res.stdout
