"""Item 3: Polarity in the drawing, not only in the netlist.

3a: Qt-free test of polarity_mark_positions across all 8 orientations with hand-worked values.
3b: Offscreen Qt test rendering each polarized symbol across all 8 orientations to a QImage,
    asserting that the '+' mark (or current arrow) is nearer the terminal named pos than neg.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import pytest

from circuitsim.canvas.symbol_geometry import polarity_mark_positions

# Hand-calculated reference coordinates for all 8 orientations:
# (rot, flip): {"pos": (x, y), "neg": (x, y), "dcv_plus": (x, y), "dcv_minus": (x, y),
#               "meter_plus": (x, y), "cur_tip": (x, y), "cur_tail": (x, y)}
HAND_WORKED_POLARITY_MARKS: dict[tuple[int, bool], dict[str, tuple[float, float]]] = {
    (0, False): {
        "pos": (-40.0, 0.0),
        "neg": (40.0, 0.0),
        "dcv_plus": (-7.0, 0.0),
        "dcv_minus": (7.0, 0.0),
        "meter_plus": (-22.0, -7.0),
        "cur_tip": (-9.0, 0.0),
        "cur_tail": (9.0, 0.0),
    },
    (90, False): {
        "pos": (0.0, -40.0),
        "neg": (0.0, 40.0),
        "dcv_plus": (0.0, -7.0),
        "dcv_minus": (0.0, 7.0),
        "meter_plus": (7.0, -22.0),
        "cur_tip": (0.0, -9.0),
        "cur_tail": (0.0, 9.0),
    },
    (180, False): {
        "pos": (40.0, 0.0),
        "neg": (-40.0, 0.0),
        "dcv_plus": (7.0, 0.0),
        "dcv_minus": (-7.0, 0.0),
        "meter_plus": (22.0, 7.0),
        "cur_tip": (9.0, 0.0),
        "cur_tail": (-9.0, 0.0),
    },
    (270, False): {
        "pos": (0.0, 40.0),
        "neg": (0.0, -40.0),
        "dcv_plus": (0.0, 7.0),
        "dcv_minus": (0.0, -7.0),
        "meter_plus": (-7.0, 22.0),
        "cur_tip": (0.0, 9.0),
        "cur_tail": (0.0, -9.0),
    },
    (0, True): {
        "pos": (40.0, 0.0),
        "neg": (-40.0, 0.0),
        "dcv_plus": (7.0, 0.0),
        "dcv_minus": (-7.0, 0.0),
        "meter_plus": (22.0, 7.0),
        "cur_tip": (9.0, 0.0),
        "cur_tail": (-9.0, 0.0),
    },
    (90, True): {
        "pos": (0.0, -40.0),
        "neg": (0.0, 40.0),
        "dcv_plus": (0.0, -7.0),
        "dcv_minus": (0.0, 7.0),
        "meter_plus": (7.0, -22.0),
        "cur_tip": (0.0, -9.0),
        "cur_tail": (0.0, 9.0),
    },
    (180, True): {
        "pos": (-40.0, 0.0),
        "neg": (40.0, 0.0),
        "dcv_plus": (-7.0, 0.0),
        "dcv_minus": (7.0, 0.0),
        "meter_plus": (-22.0, -7.0),
        "cur_tip": (-9.0, 0.0),
        "cur_tail": (9.0, 0.0),
    },
    (270, True): {
        "pos": (0.0, 40.0),
        "neg": (0.0, -40.0),
        "dcv_plus": (0.0, 7.0),
        "dcv_minus": (0.0, -7.0),
        "meter_plus": (-7.0, 22.0),
        "cur_tip": (0.0, 9.0),
        "cur_tail": (0.0, -9.0),
    },
}


@pytest.mark.parametrize("rotation_deg", [0, 90, 180, 270])
@pytest.mark.parametrize("flipped_h", [False, True])
def test_3a_polarity_mark_positions_hand_worked(rotation_deg: int, flipped_h: bool) -> None:
    """Qt-free verification of polarity_mark_positions for all 8 orientations against hand-worked coordinates."""
    expected = HAND_WORKED_POLARITY_MARKS[(rotation_deg, flipped_h)]

    # 1. DC Voltage Source
    dcv = polarity_mark_positions("dc_voltage", rotation_deg=rotation_deg, flipped_h=flipped_h)
    assert dcv["pos_terminal"] == expected["pos"]
    assert dcv["neg_terminal"] == expected["neg"]
    assert dcv["plus"] == expected["dcv_plus"]
    assert dcv["minus"] == expected["dcv_minus"]
    dist_plus_to_pos = math.hypot(dcv["plus"][0] - dcv["pos_terminal"][0], dcv["plus"][1] - dcv["pos_terminal"][1])
    dist_plus_to_neg = math.hypot(dcv["plus"][0] - dcv["neg_terminal"][0], dcv["plus"][1] - dcv["neg_terminal"][1])
    assert dist_plus_to_pos < dist_plus_to_neg

    # 2. Voltmeter and Ammeter
    for meter in ("voltmeter", "ammeter"):
        m = polarity_mark_positions(meter, rotation_deg=rotation_deg, flipped_h=flipped_h)
        assert m["pos_terminal"] == expected["pos"]
        assert m["neg_terminal"] == expected["neg"]
        assert m["plus"] == expected["meter_plus"]
        dist_m_pos = math.hypot(m["plus"][0] - m["pos_terminal"][0], m["plus"][1] - m["pos_terminal"][1])
        dist_m_neg = math.hypot(m["plus"][0] - m["neg_terminal"][0], m["plus"][1] - m["neg_terminal"][1])
        assert dist_m_pos < dist_m_neg

    # 3. DC Current Source
    dci = polarity_mark_positions("dc_current", rotation_deg=rotation_deg, flipped_h=flipped_h)
    assert dci["pos_terminal"] == expected["pos"]
    assert dci["neg_terminal"] == expected["neg"]
    assert dci["arrow_tip"] == expected["cur_tip"]
    assert dci["arrow_tail"] == expected["cur_tail"]
    dist_tip_to_pos = math.hypot(dci["arrow_tip"][0] - dci["pos_terminal"][0], dci["arrow_tip"][1] - dci["pos_terminal"][1])
    dist_tip_to_neg = math.hypot(dci["arrow_tip"][0] - dci["neg_terminal"][0], dci["arrow_tip"][1] - dci["neg_terminal"][1])
    assert dist_tip_to_pos < dist_tip_to_neg


def _run_qt(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_3b_rendered_qimage_polarity_mark_nearer_pos_than_neg() -> None:
    """Offscreen Qt test: renders each polarized symbol in all 8 orientations to a QImage

    and asserts that the pixel centroid of the polarity mark is nearer the terminal
    named 'pos' than the one named 'neg'.
    """
    script = """
import math
import sys
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.symbol_geometry import polarity_mark_positions

app = QApplication.instance() or QApplication([])
lib = SymbolLibrary()

parts = ["dc_voltage", "voltmeter", "ammeter", "dc_current"]
mark_color = "#FF1744"  # Distinct red for polarity mark

for part in parts:
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

            lib.paint_symbol(
                p,
                part,
                stroke_color="#FFFFFF",
                polarity_color=mark_color,
                rotation_deg=rot,
                flipped_h=flipped,
            )
            p.end()

            # Find all pixels painted with mark_color (#FF1744 -> r > 180, g < 60, b < 120)
            mark_pixels = []
            for y in range(img.height()):
                for x in range(img.width()):
                    col = img.pixelColor(x, y)
                    if col.red() > 180 and col.green() < 60 and col.blue() < 120:
                        mark_pixels.append((x, y))

            assert len(mark_pixels) > 0, (
                f"No polarity mark pixels found for {part} (rot={rot}, flipped={flipped})"
            )

            # Compute pixel centroid of the polarity mark
            centroid_x = sum(x for x, y in mark_pixels) / len(mark_pixels)
            centroid_y = sum(y for x, y in mark_pixels) / len(mark_pixels)

            # Transformed terminal positions in scene/image coordinates (center at 60, 60)
            marks = polarity_mark_positions(part, rotation_deg=rot, flipped_h=flipped, center_px=(60.0, 60.0))
            pos_x, pos_y = marks["pos_terminal"]
            neg_x, neg_y = marks["neg_terminal"]

            dist_to_pos = math.hypot(centroid_x - pos_x, centroid_y - pos_y)
            dist_to_neg = math.hypot(centroid_x - neg_x, centroid_y - neg_y)

            assert dist_to_pos < dist_to_neg, (
                f"Polarity inverted in {part} (rot={rot}, flip={flipped})! "
                f"Centroid ({centroid_x:.1f}, {centroid_y:.1f}) is nearer neg ({dist_to_neg:.1f}) "
                f"than pos ({dist_to_pos:.1f}). Pos=({pos_x}, {pos_y}), Neg=({neg_x}, {neg_y})"
            )
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"Qt subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
