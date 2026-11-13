"""Tests for Item 1: Verification of no stray background plates under LED or empty labels,
and verification that boundingRect() hugs painted content within 2 px across all parts and orientations.
"""

from __future__ import annotations

import numpy as np


def _get_expected_union(item):
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QFont, QFontMetrics, QPainterPath, QTransform
    from circuitsim.canvas.component_item import (
        GRID_PITCH_PX,
        format_component_value_summary,
        led_marks,
        transform_terminal_position,
    )

    w_px, h_px = item.metadata.pixel_size
    t = QTransform()
    if item.flipped_h:
        t.scale(-1.0, 1.0)
    if item.rotation_deg:
        t.rotate(float(item.rotation_deg))
    body = QPainterPath()
    body.addRect(QRectF(-w_px / 2.0 - 4.0, -h_px / 2.0 - 4.0, w_px + 8.0, h_px + 8.0))
    union_p = t.map(body)
    for term in item.metadata.terminals:
        tx, ty = transform_terminal_position(
            term.grid_pos,
            (0.0, 0.0),
            rotation_deg=item.rotation_deg,
            flipped_h=item.flipped_h,
            grid_px=GRID_PITCH_PX,
        )
        tp = QPainterPath()
        tp.addEllipse(QPointF(tx, ty), 6.0, 6.0)
        union_p = union_p.united(tp)
    lbl_rect, val_rect, text_align = item._upright_label_and_value_rects()
    fm = QFontMetrics(QFont("Segoe UI", 8))
    lbl_text = item.component.label or ""
    if lbl_text.strip():
        l_box = fm.boundingRect(lbl_rect.toRect(), int(text_align), lbl_text)
        lp = QPainterPath()
        lp.addRect(QRectF(l_box).adjusted(-2.0, -1.0, 2.0, 1.0))
        union_p = union_p.united(lp)
    val_text = (
        item.live_display_value
        if item.live_display_value is not None
        else format_component_value_summary(item.component)
    )
    if item.component.show_value and item.component.component_type != "ground" and val_text and val_text.strip():
        v_box = fm.boundingRect(val_rect.toRect(), int(text_align), val_text)
        vp = QPainterPath()
        vp.addRect(QRectF(v_box).adjusted(-3.0, -1.0, 3.0, 1.0))
        union_p = union_p.united(vp)
    if item.component.component_type == "led" and (item.isSelected() or item._is_hovered):
        marks = led_marks(item.rotation_deg, item.flipped_h, (0.0, 0.0))
        ax, ay = marks["anode_tag"]
        kx, ky = marks["cathode_tag"]
        tag_p = QPainterPath()
        tag_p.addRect(QRectF(ax - 8.0, ay - 6.0, 16.0, 12.0))
        tag_p.addRect(QRectF(kx - 8.0, ky - 6.0, 16.0, 12.0))
        union_p = union_p.united(tag_p)
    return union_p


def _non_transparent_coords(img) -> tuple[np.ndarray, np.ndarray]:
    """Return (ys, xs) of all pixels with alpha > 0."""
    buf = img.constBits()
    arr = np.frombuffer(buf, dtype=np.uint8).reshape((img.height(), img.bytesPerLine() // 4, 4))
    alpha = arr[:, : img.width(), 3]
    return np.nonzero(alpha > 0)


def test_reproduce_and_verify_no_stray_background_under_led(qapp) -> None:
    """Item 1: Place LED across all 8 orientations, flipped/not, selected/not, stopped/running,

    both themes: verify 0 stray pixels outside body, terminals, and visible labels.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QImage, QPainter
    from circuitsim.app.main_window import MainWindow
    from circuitsim.app.themes import ThemeMode

    win = MainWindow()
    scene = win.circuit_scene

    orientations = [
        (0, False), (90, False), (180, False), (270, False),
        (0, True), (90, True), (180, True), (270, True),
    ]

    stray_count = 0
    img_size = 400
    for theme in (ThemeMode.DARK, ThemeMode.LIGHT):
        win.apply_theme(theme)
        for rot, flip in orientations:
            for sel in (False, True):
                for running in (False, True):
                    scene.clear_schematic()
                    item = scene.place_new_component("led", QPointF(200.0, 200.0))
                    item.rotation_deg = rot
                    item.flipped_h = flip
                    item.setSelected(sel)
                    item.live_display_value = "2.1 V" if running else None

                    img = QImage(img_size, img_size, QImage.Format.Format_ARGB32_Premultiplied)
                    img.fill(QColor(0, 0, 0, 0))
                    painter = QPainter(img)
                    painter.translate(200.0, 200.0)
                    item.paint(painter, None, None)
                    painter.end()

                    union_p = _get_expected_union(item)
                    ys, xs = _non_transparent_coords(img)
                    for y, x in zip(ys.tolist(), xs.tolist()):
                        if not union_p.contains(QPointF(x - 200.0, y - 200.0)):
                            stray_count += 1

    scene.clear_schematic()
    assert stray_count == 0, f"Found {stray_count} stray pixels outside expected union!"


def test_every_part_has_no_painted_pixels_outside_union_and_bounding_rect_hugs_within_2px(qapp) -> None:
    """Item 1: For every part type x 8 orientations, assert no painted pixels outside union

    and boundingRect() hugs painted content within 2 px.
    """
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from circuitsim.app.main_window import MainWindow

    win = MainWindow()
    scene = win.circuit_scene

    parts = [
        "resistor", "capacitor", "inductor", "dc_voltage", "ac_voltage",
        "dc_current", "ground", "switch", "lightbulb", "led", "voltmeter", "ammeter",
    ]
    orientations = [
        (0, False), (90, False), (180, False), (270, False),
        (0, True), (90, True), (180, True), (270, True),
    ]

    outside_pixels = 0
    violations: list[str] = []
    img_size = 400

    for p in parts:
        for rot, flip in orientations:
            scene.clear_schematic()
            item = scene.place_new_component(p, QPointF(200.0, 200.0))
            item.rotation_deg = rot
            item.flipped_h = flip

            img = QImage(img_size, img_size, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(QColor(0, 0, 0, 0))
            painter = QPainter(img)
            painter.translate(200.0, 200.0)
            item.paint(painter, None, None)
            painter.end()

            union_p = _get_expected_union(item)
            ys, xs = _non_transparent_coords(img)
            assert len(xs) > 0, f"No pixels painted for {p}"
            min_x, max_x = int(xs.min()), int(xs.max())
            min_y, max_y = int(ys.min()), int(ys.max())
            for y, x in zip(ys.tolist(), xs.tolist()):
                if not union_p.contains(QPointF(x - 200.0, y - 200.0)):
                    outside_pixels += 1

            p_rect = QRectF(min_x - 200, min_y - 200, max_x - min_x + 1, max_y - min_y + 1)
            b_rect = item.boundingRect()

            d_left = p_rect.left() - b_rect.left()
            d_right = b_rect.right() - p_rect.right()
            d_top = p_rect.top() - b_rect.top()
            d_bottom = b_rect.bottom() - p_rect.bottom()

            for side, d in [("L", d_left), ("R", d_right), ("T", d_top), ("B", d_bottom)]:
                if d < -0.01:
                    violations.append(f"{p} rot={rot} flip={flip} underflow on {side}: {d}")
                elif d > 2.01:
                    violations.append(f"{p} rot={rot} flip={flip} margin > 2 on {side}: {d}")

    scene.clear_schematic()
    assert outside_pixels == 0, f"Found {outside_pixels} outside pixels"
    assert len(violations) == 0, f"Found {len(violations)} bounding rect hugging violations: {violations[:5]}"
