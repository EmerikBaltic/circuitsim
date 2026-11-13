"""Tests for ThemePalette completeness, crash handler loop prevention, and paint safety."""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pytest


def test_reproduce_led_paint_palette_attribute_error(qapp) -> None:
    """Item 1: Reproduce ThemePalette attribute error when rendering selected/hovered LED in both themes."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter
    from circuitsim.app.main_window import MainWindow
    from circuitsim.app.themes import ThemeMode

    captured: list[tuple[type, BaseException, str]] = []
    old_hook = sys.excepthook

    def hook(exctype, value, tb):
        captured.append((exctype, value, "".join(traceback.format_exception(exctype, value, tb))))

    sys.excepthook = hook
    try:
        win = MainWindow()
        win.show()
        scene = win.circuit_scene

        led_item = scene.place_new_component("led", QPointF(200.0, 200.0))
        led_item.setSelected(True)
        led_item._is_hovered = True

        img_dark = QImage(800, 600, QImage.Format.Format_ARGB32)
        p_dark = QPainter(img_dark)
        try:
            scene.render(p_dark)
        except Exception as e:
            hook(type(e), e, e.__traceback__)
        finally:
            p_dark.end()

        win.apply_theme(ThemeMode.LIGHT)
        img_light = QImage(800, 600, QImage.Format.Format_ARGB32)
        p_light = QPainter(img_light)
        try:
            scene.render(p_light)
        except Exception as e:
            hook(type(e), e, e.__traceback__)
        finally:
            p_light.end()

        assert len(captured) == 0, (
            f"Expected 0 exceptions, caught {len(captured)}: {[str(v) for _, v, _ in captured]}"
        )
    finally:
        sys.excepthook = old_hook


def test_every_palette_attribute_in_code_exists_in_both_themes() -> None:
    """Item 2: Verify that every attribute accessed on palette in the codebase exists in both Dark and Light themes."""
    import ast
    from pathlib import Path
    import dataclasses
    from circuitsim.app.themes import DARK_PALETTE, LIGHT_PALETTE, ThemePalette

    fields = {f.name for f in dataclasses.fields(ThemePalette)}
    assert "symbol_label" in fields, "symbol_label must be a defined field of ThemePalette"

    # Verify both palette instances have all attributes with valid non-empty values
    for palette, name in [(DARK_PALETTE, "DARK_PALETTE"), (LIGHT_PALETTE, "LIGHT_PALETTE")]:
        for field in fields:
            assert hasattr(palette, field), f"{name} is missing field {field}"
            val = getattr(palette, field)
            assert val is not None and str(val).strip() != "", f"{name}.{field} must not be empty"

    # Scan all Python files under src/circuitsim for any attribute accessed on an object named palette
    src_dir = Path(__file__).resolve().parents[1] / "src" / "circuitsim"
    accessed_attrs: dict[str, list[str]] = {}

    for py_file in src_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if "palette" in node.value.id.lower():
                    accessed_attrs.setdefault(node.attr, []).append(f"{py_file.name}:{node.lineno}")

    for attr, locations in accessed_attrs.items():
        assert hasattr(DARK_PALETTE, attr), f"Attribute '{attr}' accessed in {locations} is missing from DARK_PALETTE"
        assert hasattr(LIGHT_PALETTE, attr), f"Attribute '{attr}' accessed in {locations} is missing from LIGHT_PALETTE"


def test_smoke_render_every_palette_entry_all_orientations_states_and_themes(qapp) -> None:
    """Item 3: Smoke test rendering every palette entry across 8 orientations, selected/hovered, running/stopped, and both themes."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QImage, QPainter
    from circuitsim.app.main_window import MainWindow
    from circuitsim.app.themes import ThemeMode
    from circuitsim.components import Lightbulb, Switch

    captured: list[tuple[type, BaseException, str]] = []
    old_hook = sys.excepthook

    def hook(exctype, value, tb):
        captured.append((exctype, value, "".join(traceback.format_exception(exctype, value, tb))))

    sys.excepthook = hook
    try:
        win = MainWindow()
        win.show()
        scene = win.circuit_scene

        orientations = [
            (0, False), (90, False), (180, False), (270, False),
            (0, True), (90, True), (180, True), (270, True),
        ]
        palette_keys = [
            "ac_voltage", "ammeter", "capacitor", "dc_current", "dc_voltage",
            "ground", "inductor", "led", "lightbulb", "resistor", "switch", "voltmeter",
        ]
        led_states = {
            "off": {"voltage": 0.0, "current": 0.0, "brightness": 0.0, "is_over_current": False, "burned_out": False},
            "dim": {"voltage": 1.8, "current": 0.002, "brightness": 0.316, "is_over_current": False, "burned_out": False},
            "on": {"voltage": 2.0, "current": 0.020, "brightness": 1.0, "is_over_current": False, "burned_out": False},
            "over": {"voltage": 2.2, "current": 0.035, "brightness": 1.32, "is_over_current": True, "burned_out": False},
            "burned": {"voltage": 0.0, "current": 0.0, "brightness": 0.0, "is_over_current": False, "burned_out": True},
            "reverse": {"voltage": -5.0, "current": 0.0, "brightness": 0.0, "is_over_current": False, "burned_out": False},
        }

        img = QImage(240, 240, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        for theme in (ThemeMode.DARK, ThemeMode.LIGHT):
            win.apply_theme(theme)
            for comp_key in palette_keys:
                scene.clear_schematic()
                item = scene.place_new_component(comp_key, QPointF(200.0, 200.0))
                for rot, flip in orientations:
                    item.rotation_deg = rot
                    item.flipped_h = flip
                    for sel in (False, True):
                        item.setSelected(sel)
                        for hov in (False, True):
                            item._is_hovered = hov
                            if comp_key == "led":
                                for svals in led_states.values():
                                    for k, v in svals.items():
                                        setattr(item.component, k, v)
                                    scene.render(p, QRectF(0, 0, 240, 240), item.sceneBoundingRect())
                            else:
                                for running in (False, True):
                                    if running:
                                        item.live_display_value = "5.0 V"
                                        if isinstance(item.component, Lightbulb):
                                            item.component.voltage = 12.0
                                            item.component.current = 1.0
                                        elif isinstance(item.component, Switch):
                                            item.component.closed = True
                                            item._lever_angle_deg = 0.0
                                    else:
                                        item.live_display_value = None
                                        if isinstance(item.component, Lightbulb):
                                            item.component.voltage = 0.0
                                            item.component.current = 0.0
                                        elif isinstance(item.component, Switch):
                                            item.component.closed = False
                                            item._lever_angle_deg = 30.0
                                    scene.render(p, QRectF(0, 0, 240, 240), item.sceneBoundingRect())
        p.end()
        assert len(captured) == 0, f"Expected 0 exceptions, caught {len(captured)}"
    finally:
        sys.excepthook = old_hook


@pytest.mark.slow
def test_crash_handler_deduplication_and_no_dialog_loop(qapp) -> None:
    """Item 4: Raising the same exception 1000 times inside paint produces exactly one dialog call and one log entry with count."""
    from PySide6.QtCore import QPointF
    from circuitsim.app.crash_handler import (
        create_crash_dialog,
        get_dialog_call_count,
        install_global_exception_hook,
        reset_crash_state,
        set_dialog_handler,
    )
    from circuitsim.app.main_window import MainWindow

    old_hook = sys.excepthook
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        reset_crash_state()
        install_global_exception_hook(log_dir=tmp_dir)

        dialog_calls = []
        set_dialog_handler(lambda msg, count, path: dialog_calls.append((msg, count, path)))

        win = MainWindow()
        win.show()
        scene = win.circuit_scene
        scene.place_new_component("resistor", QPointF(200.0, 200.0))

        for _ in range(1000):
            try:
                raise AttributeError("Test paint error: missing attribute token")
            except Exception as e:
                sys.excepthook(type(e), e, e.__traceback__)

        from PySide6.QtCore import QEventLoop, QTimer
        qapp.processEvents()
        loop = QEventLoop()
        QTimer.singleShot(20, loop.quit)
        loop.exec()

        assert len(dialog_calls) == 1, f"Expected 1 dialog call, got {len(dialog_calls)}"
        msg, count, log_path = dialog_calls[0]
        assert count == 1000, f"Expected count 1000, got {count}"
        assert get_dialog_call_count() == 1

        log_file = tmp_dir / "crash.log"
        assert log_file.exists(), "crash.log must exist"
        log_text = log_file.read_text(encoding="utf-8")
        report_blocks = log_text.count("=" * 70) // 2
        assert report_blocks == 1, f"Expected exactly 1 log block, got {report_blocks}"
        assert "Occurrences:    1000" in log_text

        box = create_crash_dialog("Test error", count=1000, log_path=log_file)
        btn_texts = [b.text() for b in box.buttons()]
        assert any("Quit" in b for b in btn_texts), f"Quit button missing from {btn_texts}"
        assert any("OK" in b for b in btn_texts), f"OK button missing from {btn_texts}"
        assert "This error occurred 1000 times." in box.text()
        box.close()
    finally:
        set_dialog_handler(None)
        reset_crash_state()
        sys.excepthook = old_hook
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_paint_safety_guard_on_component_wire_and_junction(qapp) -> None:
    """Item 5: Wrap paint() in guard: if drawing fails, log once per item, draw red dashed rect with '!', and continue without propagating."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from circuitsim.app.crash_handler import install_global_exception_hook, reset_crash_state, set_dialog_handler
    from circuitsim.app.main_window import MainWindow
    from circuitsim.canvas.wire_item import JunctionItem, WireItem

    old_hook = sys.excepthook
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        reset_crash_state()
        set_dialog_handler(lambda *args: None)
        install_global_exception_hook(log_dir=tmp_dir)

        win = MainWindow()
        win.show()
        scene = win.circuit_scene

        comp_item = scene.place_new_component("resistor", QPointF(100.0, 100.0))
        comp_item._paint_impl = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Simulated failure in component paint")
        )

        wire_item = WireItem("w_test", [(50.0, 50.0), (150.0, 50.0)])
        scene.addItem(wire_item)
        wire_item._paint_impl = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Simulated failure in wire paint")
        )

        junc_item = JunctionItem(QPointF(200.0, 200.0))
        scene.addItem(junc_item)
        junc_item._paint_impl = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Simulated failure in junction paint")
        )

        img = QImage(300, 300, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.black)
        p = QPainter(img)
        scene.render(p, QRectF(0, 0, 300, 300), QRectF(0, 0, 300, 300))
        p.end()

        assert comp_item._paint_error_logged is True
        assert wire_item._paint_error_logged is True
        assert junc_item._paint_error_logged is True

        arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape((300, img.bytesPerLine() // 4, 4))
        # ARGB32 on little-endian is BGRA
        b, g, r = arr[:, :300, 0], arr[:, :300, 1], arr[:, :300, 2]
        red_count = int(np.count_nonzero((r > 200) & (g < 100) & (b < 100)))
        assert red_count > 50, f"Expected red fallback pixels, found {red_count}"

        p2 = QPainter(img)
        scene.render(p2, QRectF(0, 0, 300, 300), QRectF(0, 0, 300, 300))
        p2.end()

        log_file = tmp_dir / "crash.log"
        assert log_file.exists(), "crash.log must exist"
        log_text = log_file.read_text(encoding="utf-8")
        assert "Simulated failure in component paint" in log_text
        assert "Simulated failure in wire paint" in log_text
    finally:
        set_dialog_handler(None)
        reset_crash_state()
        sys.excepthook = old_hook
        shutil.rmtree(tmp_dir, ignore_errors=True)




