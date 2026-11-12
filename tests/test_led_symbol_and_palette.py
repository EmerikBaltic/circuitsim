"""Tests for Item 1: LED Symbol, Palette Entry, and Pure Geometry Marks."""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path
import pytest

from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    led_marks,
)
from circuitsim.components import LED, create_default_component_model

# Hand-calculated reference coordinates for all 8 orientations with center_px = (0.0, 0.0):
# (rotation_deg, flipped_h): {
#     "anode": (x, y), "cathode": (x, y), "bar": (x, y), "flat": (x, y),
#     "anode_tag": (x, y), "cathode_tag": (x, y)
# }
HAND_WORKED_LED_MARKS: dict[tuple[int, bool], dict[str, tuple[float, float]]] = {
    (0, False): {
        "anode": (-40.0, 0.0),
        "cathode": (40.0, 0.0),
        "bar": (8.0, 0.0),
        "flat": (14.0, 0.0),
        "anode_tag": (-28.0, -8.0),
        "cathode_tag": (28.0, -8.0),
    },
    (0, True): {
        "anode": (40.0, 0.0),
        "cathode": (-40.0, 0.0),
        "bar": (-8.0, 0.0),
        "flat": (-14.0, 0.0),
        "anode_tag": (28.0, 8.0),
        "cathode_tag": (-28.0, 8.0),
    },
    (90, False): {
        "anode": (0.0, -40.0),
        "cathode": (0.0, 40.0),
        "bar": (0.0, 8.0),
        "flat": (0.0, 14.0),
        "anode_tag": (8.0, -28.0),
        "cathode_tag": (8.0, 28.0),
    },
    (90, True): {
        "anode": (0.0, -40.0),
        "cathode": (0.0, 40.0),
        "bar": (0.0, 8.0),
        "flat": (0.0, 14.0),
        "anode_tag": (8.0, -28.0),
        "cathode_tag": (8.0, 28.0),
    },
    (180, False): {
        "anode": (40.0, 0.0),
        "cathode": (-40.0, 0.0),
        "bar": (-8.0, 0.0),
        "flat": (-14.0, 0.0),
        "anode_tag": (28.0, 8.0),
        "cathode_tag": (-28.0, 8.0),
    },
    (180, True): {
        "anode": (-40.0, 0.0),
        "cathode": (40.0, 0.0),
        "bar": (8.0, 0.0),
        "flat": (14.0, 0.0),
        "anode_tag": (-28.0, -8.0),
        "cathode_tag": (28.0, -8.0),
    },
    (270, False): {
        "anode": (0.0, 40.0),
        "cathode": (0.0, -40.0),
        "bar": (0.0, -8.0),
        "flat": (0.0, -14.0),
        "anode_tag": (-8.0, 28.0),
        "cathode_tag": (-8.0, -28.0),
    },
    (270, True): {
        "anode": (0.0, 40.0),
        "cathode": (0.0, -40.0),
        "bar": (0.0, -8.0),
        "flat": (0.0, -14.0),
        "anode_tag": (-8.0, 28.0),
        "cathode_tag": (-8.0, -28.0),
    },
}


@pytest.mark.parametrize("rotation_deg", [0, 90, 180, 270])
@pytest.mark.parametrize("flipped_h", [False, True])
def test_led_marks_hand_worked_all_8_orientations(
    rotation_deg: int, flipped_h: bool
) -> None:
    """Verify that led_marks computes hand-worked coordinates and flat is nearer cathode in all 8 orientations."""
    expected = HAND_WORKED_LED_MARKS[(rotation_deg, flipped_h)]
    marks = led_marks(rotation_deg=rotation_deg, flipped_h=flipped_h, center_px=(0.0, 0.0))

    assert marks["anode_terminal"] == expected["anode"]
    assert marks["cathode_terminal"] == expected["cathode"]
    assert marks["bar"] == expected["bar"]
    assert marks["flat"] == expected["flat"]
    assert marks["anode_tag"] == expected["anode_tag"]
    assert marks["cathode_tag"] == expected["cathode_tag"]

    # Flat must be strictly nearer cathode than anode in every orientation
    flat_x, flat_y = marks["flat"]
    ax, ay = marks["anode_terminal"]
    kx, ky = marks["cathode_terminal"]
    dist_flat_to_cathode = math.hypot(flat_x - kx, flat_y - ky)
    dist_flat_to_anode = math.hypot(flat_x - ax, flat_y - ay)

    # In all 8 orientations, distance to cathode is 26 px and to anode is 54 px
    assert math.isclose(dist_flat_to_cathode, 26.0, abs_tol=1e-3)
    assert math.isclose(dist_flat_to_anode, 54.0, abs_tol=1e-3)
    assert dist_flat_to_cathode < dist_flat_to_anode


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


def test_led_palette_entry_and_metadata() -> None:
    """Verify LED palette category 'Semiconductors', metadata terminals, and factory model creation."""
    script = """
import sys
from circuitsim.app.palette_dock import CATEGORY_ORDER, COMPONENT_ORDER_IN_CATEGORY
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.components import LED, create_default_component_model

assert "Semiconductors" in CATEGORY_ORDER
assert "led" in COMPONENT_ORDER_IN_CATEGORY["Semiconductors"]

lib = SymbolLibrary()
catalog = lib.metadata_catalog
assert "led" in catalog
meta = catalog["led"]
assert meta.category == "Semiconductors"
assert meta.grid_size == (4, 2)
assert meta.pixel_size == (80, 40)

term_names = [t.name for t in meta.terminals]
assert term_names == ["anode", "cathode"]

anode_vb = meta.terminal_in_svg_viewbox(meta.terminals[0])
cathode_vb = meta.terminal_in_svg_viewbox(meta.terminals[1])
assert anode_vb == (0.0, 20.0)
assert cathode_vb == (80.0, 20.0)

comp = create_default_component_model("led", "D1")
assert isinstance(comp, LED)
assert comp.name == "D1"
assert comp.forward_voltage == 2.0
assert comp.color_name == "Red"
"""
    proc = _run_qt_script(script)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_offscreen_led_rendering_flat_centroid_nearer_cathode_all_8_orientations() -> None:
    """Offscreen Qt test: render LED across all 8 orientations and verify cathode flat centroid is nearer cathode."""
    script = """
import math
import sys
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.symbol_geometry import led_marks

app = QApplication.instance() or QApplication([])
lib = SymbolLibrary()

flat_highlight_color = "#FF1744"  # Distinct red to isolate cathode flat pixels

for rot in (0, 90, 180, 270):
    for flipped in (False, True):
        img = QImage(120, 120, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.black)

        p = QPainter(img)
        p.translate(60.0, 60.0)

        # Match ComponentItem.paint() transform order
        if flipped:
            p.scale(-1.0, 1.0)
        if rot:
            p.rotate(float(rot))

        # Render symbol with flat line painted in flat_highlight_color
        lib.paint_symbol(
            p,
            "led",
            stroke_color="#FFFFFF",
            polarity_color=flat_highlight_color,
            rotation_deg=rot,
            flipped_h=flipped,
        )
        p.end()

        # Find all pixels painted with flat_highlight_color
        flat_pixels = []
        for y in range(img.height()):
            for x in range(img.width()):
                col = img.pixelColor(x, y)
                if col.red() > 200 and col.green() < 50 and col.blue() < 100:
                    flat_pixels.append((x, y))

        assert len(flat_pixels) > 0, (
            f"No cathode flat pixels found for LED (rot={rot}, flipped={flipped})"
        )

        # Centroid of the cathode flat pixels
        centroid_x = sum(x for x, y in flat_pixels) / len(flat_pixels)
        centroid_y = sum(y for x, y in flat_pixels) / len(flat_pixels)

        # Transformed terminal coordinates with center at (60, 60)
        marks = led_marks(rot, flipped, center_px=(60.0, 60.0))
        anode_x, anode_y = marks["anode_terminal"]
        cathode_x, cathode_y = marks["cathode_terminal"]

        dist_to_cathode = math.hypot(centroid_x - cathode_x, centroid_y - cathode_y)
        dist_to_anode = math.hypot(centroid_x - anode_x, centroid_y - anode_y)

        assert dist_to_cathode < dist_to_anode, (
            f"Cathode flat inverted! For rot={rot}, flip={flipped}: "
            f"Flat centroid ({centroid_x:.1f}, {centroid_y:.1f}) is nearer anode ({dist_to_anode:.1f}) "
            f"than cathode ({dist_to_cathode:.1f}). Anode=({anode_x}, {anode_y}), Cathode=({cathode_x}, {cathode_y})"
        )
"""
    res = _run_qt_script(script)
    assert res.returncode == 0, f"Qt subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
