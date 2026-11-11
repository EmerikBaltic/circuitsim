"""Canvas QGraphicsObject for schematic components, upright labels, switch animation, and bulb glow."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

from circuitsim.app.themes import ThemeMode, ThemePalette, get_theme_palette
from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    PointPx,
    normalize_point_px,
)
from circuitsim.canvas.symbol_geometry import (
    GRID_PITCH_PX,
    SymbolMetadata,
    snap_to_grid,
    transform_terminal_position,
)
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.components import (
    ACVoltageSource,
    Ammeter,
    Capacitor,
    Component,
    DCCurrentSource,
    DCVoltageSource,
    Ground,
    Inductor,
    Lightbulb,
    Resistor,
    Switch,
    Voltmeter,
)
from circuitsim.dialogs.value_parser import format_engineering_value
from circuitsim.engine.simulation_session import ComponentTelemetry

COMPONENT_PREFIXES: dict[str, str] = {
    "resistor": "R",
    "capacitor": "C",
    "inductor": "L",
    "dc_voltage": "V",
    "ac_voltage": "Vac",
    "dc_current": "I",
    "ground": "GND",
    "switch": "SW",
    "lightbulb": "B",
    "voltmeter": "VM",
    "ammeter": "A",
}


# Re-exported from the Qt-free factory so the .circ loader can use it too.
from circuitsim.components.factory import create_default_component_model  # noqa: E402,F401


def format_component_value_summary(comp: Component) -> str:
    """Return a concise engineering-notation summary string for canvas display."""
    if isinstance(comp, Resistor):
        return format_engineering_value(comp.resistance, "Ω")
    if isinstance(comp, Capacitor):
        return format_engineering_value(comp.capacitance, "F")
    if isinstance(comp, Inductor):
        return format_engineering_value(comp.inductance, "H")
    if isinstance(comp, DCVoltageSource):
        return format_engineering_value(comp.dc_voltage, "V")
    if isinstance(comp, ACVoltageSource):
        v_str = format_engineering_value(comp.amplitude, "V")
        f_str = format_engineering_value(comp.frequency, "Hz")
        return f"{v_str} {f_str}"
    if isinstance(comp, DCCurrentSource):
        return format_engineering_value(comp.dc_current, "A")
    if isinstance(comp, Switch):
        if comp.arcing and not comp.closed:
            return "ARC!"
        return "ON" if comp.closed else "OFF"
    if isinstance(comp, Lightbulb):
        if comp.burned_out:
            return "BURNED OUT"
        return f"{comp.rated_power:g}W / {comp.rated_voltage:g}V"
    if isinstance(comp, (Voltmeter, Ammeter)):
        return comp.format_reading()
    return ""


def rect_intersects_segment(
    rect: QRectF,
    p1: tuple[float, float] | QPointF,
    p2: tuple[float, float] | QPointF,
) -> bool:
    """Check if an orthogonal or general line segment intersects or enters a rectangle."""
    rx1 = rect.left()
    ry1 = rect.top()
    rx2 = rect.right()
    ry2 = rect.bottom()

    x1 = p1.x() if isinstance(p1, QPointF) else p1[0]
    y1 = p1.y() if isinstance(p1, QPointF) else p1[1]
    x2 = p2.x() if isinstance(p2, QPointF) else p2[0]
    y2 = p2.y() if isinstance(p2, QPointF) else p2[1]

    # Either endpoint is inside the rectangle
    if (rx1 <= x1 <= rx2 and ry1 <= y1 <= ry2) or (rx1 <= x2 <= rx2 and ry1 <= y2 <= ry2):
        return True

    # Orthogonal horizontal segment
    if abs(y1 - y2) < 1e-6:
        seg_y = y1
        if ry1 <= seg_y <= ry2:
            seg_min_x = min(x1, x2)
            seg_max_x = max(x1, x2)
            if max(seg_min_x, rx1) <= min(seg_max_x, rx2):
                return True
        return False

    # Orthogonal vertical segment
    if abs(x1 - x2) < 1e-6:
        seg_x = x1
        if rx1 <= seg_x <= ry2:
            seg_min_y = min(y1, y2)
            seg_max_y = max(y1, y2)
            if max(seg_min_y, ry1) <= min(seg_max_y, ry2):
                return True
        return False

    # Bounding box test for general line
    if max(x1, x2) < rx1 or min(x1, x2) > rx2 or max(y1, y2) < ry1 or min(y1, y2) > ry2:
        return False
    return True


class ComponentItem(QGraphicsObject):
    """Visual schematic item representing an electrical component on the canvas.

    Supports:
        - Grid snapping (20 px pitch)
        - 90-degree rotations and horizontal flip with upright, readable text labels
        - SVG rendering (if file exists in `resources/symbols/iec/`) or procedural IEC fallback
        - Animated switch lever, real-power lightbulb glow + over-bright warning, and
          live meter readouts (`-- V` / `-- A` until simulation produces a reading)
        - Problem diagnostic highlighting (`error` in red, `warning` in amber)
    """

    OPEN_LEVER_ANGLE_DEG: float = 26.0
    CLOSED_LEVER_ANGLE_DEG: float = 0.0

    def __init__(
        self,
        component: Component,
        symbol_library: SymbolLibrary,
        *,
        theme: ThemeMode = ThemeMode.DARK,
        is_ghost: bool = False,
        rotation_deg: int = 0,
        flipped_h: bool = False,
    ) -> None:
        super().__init__()
        self.component: Component = component
        self.symbol_library: SymbolLibrary = symbol_library
        self.metadata: SymbolMetadata = symbol_library.get_metadata(
            component.component_type
        )
        self.theme: ThemeMode = theme
        self.is_ghost: bool = is_ghost
        self._rotation_deg: int = 0
        self._flipped_h: bool = False
        if rotation_deg:
            self.set_rotation_deg(rotation_deg)
        if flipped_h:
            self.set_flipped_h(flipped_h)

        # Live simulation visual states
        self.live_display_value: str | None = None
        self.diagnostic_severity: str | None = None  # "error", "warning", or None
        self.diagnostic_message: str = ""
        self.diagnostic_code: str = ""
        self.is_unconnected: bool = False
        self.label_position: str = "default"

        # Switch lever animation state
        self._lever_angle_deg: float = (
            self.CLOSED_LEVER_ANGLE_DEG
            if (isinstance(component, Switch) and component.closed)
            else self.OPEN_LEVER_ANGLE_DEG
        )
        self._lever_anim: QVariantAnimation | None = None

        if not is_ghost:
            self.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            )
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if isinstance(component, Switch)
                else Qt.CursorShape.OpenHandCursor
            )
            self.setZValue(20.0)
        else:
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.setOpacity(0.65)
            self.setZValue(100.0)

    @property
    def symbol_state(self) -> str | None:
        """Return active symbol state name (e.g. 'open' or 'closed' for Switch)."""
        if isinstance(self.component, Switch):
            return "closed" if self.component.closed else "open"
        if isinstance(self.component, Lightbulb):
            if self.component.burned_out:
                return "burned_out"
            if self.component.brightness > 0.05:
                return "lit"
            return "normal"
        return None

    @property
    def lever_angle_deg(self) -> float:
        return self._lever_angle_deg

    def effective_text_angle_deg(self) -> float:
        """Return the scene rotation angle of text labels (always 0° upright)."""
        return 0.0

    def set_theme(self, theme: ThemeMode) -> None:
        """Update item theme and trigger a repaint."""
        self.theme = theme
        self.update()

    def set_unconnected(self, unconnected: bool) -> None:
        """Dim or restore the component visually when it has no wires connected."""
        if self.is_unconnected == bool(unconnected):
            return
        self.is_unconnected = bool(unconnected)
        if not self.is_ghost:
            self.setOpacity(0.45 if self.is_unconnected else 1.0)
        self.update()

    def set_diagnostic(
        self, severity: str | None, message: str = "", *, code: str = ""
    ) -> None:
        """Set or clear canvas problem highlighting on this component."""
        if (
            self.diagnostic_severity == severity
            and self.diagnostic_message == message
            and self.diagnostic_code == code
        ):
            return
        self.diagnostic_severity = severity
        self.diagnostic_message = message
        self.diagnostic_code = code
        self.setToolTip(message if message else f"{self.component.name} ({self.metadata.display_name})")
        self.update()

    def effective_highlight_color(self) -> str | None:
        """Return the active problem-highlight hex color ('#FF5252' for error, '#FFA726' for warning), or None."""
        if self.diagnostic_severity == "error":
            return "#FF5252"
        if self.diagnostic_severity == "warning":
            return "#FFA726"
        return None

    def apply_telemetry(self, telemetry: ComponentTelemetry) -> None:
        """Update live operating state from a `SimulationFrame` telemetry snapshot."""
        self.component.voltage = telemetry.voltage
        self.component.current = telemetry.current
        self.component.power = telemetry.power
        self.live_display_value = telemetry.display_value

        if isinstance(self.component, Lightbulb):
            self.component.burned_out = telemetry.burned_out
        elif isinstance(self.component, Switch):
            if self.component.closed != telemetry.switch_closed:
                self.animate_switch_state(telemetry.switch_closed)
            self.component.arcing = telemetry.switch_arcing
        elif isinstance(self.component, (Voltmeter, Ammeter)):
            self.component.has_reading = not telemetry.display_value.startswith("--")

        self.update()

    def reset_live_telemetry(self) -> None:
        """Clear live telemetry and restore initial component state (when simulation stops)."""
        self.live_display_value = None
        self.component.reset_state()
        if isinstance(self.component, Switch):
            self._lever_angle_deg = (
                self.CLOSED_LEVER_ANGLE_DEG
                if self.component.closed
                else self.OPEN_LEVER_ANGLE_DEG
            )
        self.update()

    def animate_switch_state(self, closed: bool, *, duration_ms: int = 110) -> None:
        """Smoothly animate the switch lever between open (`26°`) and closed (`0°`)."""
        if not isinstance(self.component, Switch):
            return
        self.component.set_closed(closed)
        target_angle = (
            self.CLOSED_LEVER_ANGLE_DEG if closed else self.OPEN_LEVER_ANGLE_DEG
        )
        if duration_ms <= 0:
            self._lever_angle_deg = target_angle
            self.update()
            return

        if self._lever_anim is None:
            self._lever_anim = QVariantAnimation(self)
            self._lever_anim.valueChanged.connect(self._on_lever_anim_step)

        self._lever_anim.stop()
        self._lever_anim.setDuration(duration_ms)
        self._lever_anim.setStartValue(float(self._lever_angle_deg))
        self._lever_anim.setEndValue(float(target_angle))
        self._lever_anim.start()
        # Also set immediately in case no event loop spins in a synchronous test
        self._lever_angle_deg = target_angle
        self.update()

    def _on_lever_anim_step(self, value: object) -> None:
        if isinstance(value, (int, float)):
            self._lever_angle_deg = float(value)
            self.update()

    def set_snapped_pos(self, x_px: float, y_px: float) -> None:
        """Snap `(x_px, y_px)` to the 20 px grid and set the item's scene position."""
        sx, sy = snap_to_grid(x_px, y_px, GRID_PITCH_PX)
        self.setPos(sx, sy)

    @property
    def rotation_deg(self) -> int:
        return self._rotation_deg

    @rotation_deg.setter
    def rotation_deg(self, deg: int) -> None:
        self.set_rotation_deg(deg)

    @property
    def flipped_h(self) -> bool:
        return self._flipped_h

    @flipped_h.setter
    def flipped_h(self, flipped: bool) -> None:
        self.set_flipped_h(flipped)

    def rotate_90_cw(self) -> None:
        """Rotate component 90 degrees clockwise around its center `(0, 0)`."""
        self.set_rotation_deg((self._rotation_deg + 90) % 360)

    def rotate_90_ccw(self) -> None:
        """Rotate component 90 degrees counter-clockwise around its center `(0, 0)`."""
        self.set_rotation_deg((self._rotation_deg - 90) % 360)

    def set_rotation_deg(self, rotation_deg: int) -> None:
        """Set explicit rotation angle in `{0, 90, 180, 270}`."""
        target = int(rotation_deg) % 360
        if self._rotation_deg != target:
            self._rotation_deg = target
            self._apply_local_transform()

    def flip_horizontal(self) -> None:
        """Mirror the component horizontally across its local Y axis."""
        self.set_flipped_h(not self._flipped_h)

    def set_flipped_h(self, flipped: bool) -> None:
        """Set explicit horizontal mirror state."""
        target = bool(flipped)
        if self._flipped_h != target:
            self._flipped_h = target
            self._apply_local_transform()

    def _apply_local_transform(self) -> None:
        # Keep QGraphicsObject transform as identity and apply rotation/flip inside
        # paint() only for the symbol geometry so text labels always remain upright!
        self.prepareGeometryChange()
        self.update()

    def terminal_scene_positions(self) -> dict[str, tuple[float, float]]:
        """Return scene pixel coordinates `(x, y)` for every terminal of this item."""
        cx, cy = self.pos().x(), self.pos().y()
        result: dict[str, tuple[float, float]] = {}
        for term in self.metadata.terminals:
            result[term.name] = transform_terminal_position(
                term.grid_pos,
                (cx, cy),
                rotation_deg=self.rotation_deg,
                flipped_h=self.flipped_h,
                grid_px=GRID_PITCH_PX,
            )
        return result

    def terminal_scene_positions_px(self) -> dict[str, PointPx]:
        """Return integer snapped scene pixel coordinates `(x, y)` for every terminal."""
        return {
            tname: normalize_point_px(pos, snap=True)
            for tname, pos in self.terminal_scene_positions().items()
        }

    def to_placed_spec(self) -> PlacedComponentSpec:
        """Build a pure-Python `PlacedComponentSpec` snapshot for netlist extraction."""
        return PlacedComponentSpec(
            component=self.component,
            center_px=(self.pos().x(), self.pos().y()),
            rotation_deg=self.rotation_deg,
            flipped_h=self.flipped_h,
            terminals_px=self.terminal_scene_positions_px(),
        )

    def selection_outline_rect_local(self) -> QRectF:
        """Return the selection/problem outline rectangle in upright local coordinates."""
        w_px, h_px = self.metadata.pixel_size
        if self.rotation_deg in (90, 270):
            return QRectF(
                -float(h_px) / 2.0 - 3.0,
                -float(w_px) / 2.0 - 3.0,
                float(h_px) + 6.0,
                float(w_px) + 6.0,
            )
        return QRectF(
            -float(w_px) / 2.0 - 3.0,
            -float(h_px) / 2.0 - 3.0,
            float(w_px) + 6.0,
            float(h_px) + 6.0,
        )

    def set_label_position(self, pos: str) -> None:
        """Set the label position ('default', 'below', 'above', 'right', 'left')."""
        if self.label_position != pos:
            self.prepareGeometryChange()
            self.label_position = pos
            self.update()

    def _get_label_and_value_rects_for_position(
        self, pos: str
    ) -> tuple[QRectF, QRectF, Qt.AlignmentFlag]:
        w_px, h_px = self.metadata.pixel_size
        is_vert = self.rotation_deg in (90, 270)
        eff_w = float(h_px if is_vert else w_px)
        eff_h = float(w_px if is_vert else h_px)

        if pos == "default":
            if is_vert:
                right_x = float(h_px) / 2.0 + 7.0
                lbl_rect = QRectF(right_x, -18.0, 96.0, 17.0)
                val_rect = QRectF(right_x, 1.0, 110.0, 17.0)
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                return lbl_rect, val_rect, align

            if self.component.component_type == "ground":
                lbl_x = 0.0
                lbl_y = -float(h_px) / 2.0 - 2.0 if self.rotation_deg == 180 else float(h_px) / 2.0 + 2.0
                lbl_rect = QRectF(lbl_x - 50.0, lbl_y - 9.0, 100.0, 18.0)
                val_rect = QRectF(-60.0, 0.0, 120.0, 18.0)
                return lbl_rect, val_rect, Qt.AlignmentFlag.AlignCenter

            lbl_x = self.metadata.label_offset[0] * GRID_PITCH_PX
            lbl_y = min(
                self.metadata.label_offset[1] * GRID_PITCH_PX,
                -float(h_px) / 2.0 - 14.0,
            )
            val_x = self.metadata.value_offset[0] * GRID_PITCH_PX
            val_y = max(
                self.metadata.value_offset[1] * GRID_PITCH_PX,
                float(h_px) / 2.0 + 14.0,
            )
            lbl_rect = QRectF(lbl_x - 50.0, lbl_y - 9.0, 100.0, 18.0)
            val_rect = QRectF(val_x - 60.0, val_y - 9.0, 120.0, 18.0)
            return lbl_rect, val_rect, Qt.AlignmentFlag.AlignCenter

        if pos == "below":
            y_top = eff_h / 2.0 + 6.0
            lbl_rect = QRectF(-50.0, y_top, 100.0, 16.0)
            val_rect = QRectF(-60.0, y_top + 17.0, 120.0, 16.0)
            return lbl_rect, val_rect, Qt.AlignmentFlag.AlignCenter

        if pos == "above":
            y_base = -eff_h / 2.0 - 6.0
            lbl_rect = QRectF(-50.0, y_base - 33.0, 100.0, 16.0)
            val_rect = QRectF(-60.0, y_base - 16.0, 120.0, 16.0)
            return lbl_rect, val_rect, Qt.AlignmentFlag.AlignCenter

        if pos == "right":
            x_start = eff_w / 2.0 + 8.0
            lbl_rect = QRectF(x_start, -18.0, 96.0, 17.0)
            val_rect = QRectF(x_start, 1.0, 110.0, 17.0)
            return lbl_rect, val_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        if pos == "left":
            x_end = -eff_w / 2.0 - 8.0
            lbl_rect = QRectF(x_end - 96.0, -18.0, 96.0, 17.0)
            val_rect = QRectF(x_end - 110.0, 1.0, 110.0, 17.0)
            return lbl_rect, val_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        return self._get_label_and_value_rects_for_position("default")

    def _upright_label_and_value_rects(
        self,
    ) -> tuple[QRectF, QRectF, Qt.AlignmentFlag]:
        """Compute upright (unrotated, unmirrored) label and value rectangles clear of the selection box."""
        return self._get_label_and_value_rects_for_position(self.label_position)

    def candidate_label_rects_scene(
        self, pos: str | None = None
    ) -> list[QRectF]:
        """Compute the tight visual bounding rectangles of this item's labels in scene coordinates."""
        target_pos = pos if pos is not None else self.label_position
        lbl_rect, val_rect, text_align = self._get_label_and_value_rects_for_position(target_pos)

        font = QFont("Segoe UI", 8)
        font.setBold(True)
        fm = QFontMetrics(font)

        lbl_box = fm.boundingRect(lbl_rect.toRect(), int(text_align), self.component.label)
        actual_lbl = QRectF(lbl_box).adjusted(-2.0, -1.0, 2.0, 1.0).translated(self.pos())
        rects = [actual_lbl]

        if self.component.show_value and self.component.component_type != "ground":
            if isinstance(self.component, (Voltmeter, Ammeter)):
                font.setBold(True)
            else:
                font.setBold(False)
            fm_val = QFontMetrics(font)
            val_text = (
                self.live_display_value
                if self.live_display_value is not None
                else format_component_value_summary(self.component)
            )
            val_box = fm_val.boundingRect(val_rect.toRect(), int(text_align), val_text)
            actual_val = QRectF(val_box).adjusted(-3.0, -1.0, 3.0, 1.0).translated(self.pos())
            rects.append(actual_val)

        return rects

    def scene_body_rect(self) -> QRectF:
        """Return the rotated/flipped body rectangle in scene coordinates (excluding labels)."""
        w_px, h_px = self.metadata.pixel_size
        is_vert = self.rotation_deg in (90, 270)
        bw = float(h_px if is_vert else w_px)
        bh = float(w_px if is_vert else h_px)
        return QRectF(-bw / 2.0, -bh / 2.0, bw, bh).translated(self.pos())

    def shape(self) -> QPainterPath:
        """Return precision hit-test shape matching the rotated/flipped symbol body and terminals."""
        w_px, h_px = self.metadata.pixel_size
        body_rect = QRectF(
            -float(w_px) / 2.0 - 2.0,
            -float(h_px) / 2.0 - 2.0,
            float(w_px) + 4.0,
            float(h_px) + 4.0,
        )

        t = QTransform()
        if self.flipped_h:
            t.scale(-1.0, 1.0)
        if self.rotation_deg:
            t.rotate(float(self.rotation_deg))

        raw_path = QPainterPath()
        raw_path.setFillRule(Qt.FillRule.WindingFill)
        raw_path.addRect(body_rect)
        path = t.map(raw_path)
        path.setFillRule(Qt.FillRule.WindingFill)

        for term in self.metadata.terminals:
            tx, ty = transform_terminal_position(
                term.grid_pos,
                (0.0, 0.0),
                rotation_deg=self.rotation_deg,
                flipped_h=self.flipped_h,
                grid_px=GRID_PITCH_PX,
            )
            term_path = QPainterPath()
            term_path.addEllipse(QPointF(tx, ty), 6.0, 6.0)
            path = path.united(term_path)

        path.setFillRule(Qt.FillRule.WindingFill)
        return path

    def boundingRect(self) -> QRectF:
        """Return tight bounding rectangle enclosing the rotated symbol body, terminals, and upright labels."""
        rect = self.shape().boundingRect()

        if not self.is_ghost:
            lbl_rect, val_rect, _ = self._upright_label_and_value_rects()
            rect = rect.united(lbl_rect)
            if (
                self.component.show_value
                and self.component.component_type != "ground"
            ):
                rect = rect.united(val_rect)
            if self.diagnostic_severity in ("error", "warning") or (
                isinstance(self.component, Lightbulb)
                and self.component.is_over_bright
            ):
                rect = rect.united(QRectF(11.0, -25.0, 14.0, 14.0))

        if isinstance(self.component, Lightbulb) and not self.is_ghost:
            rect = rect.united(QRectF(-36.0, -36.0, 72.0, 72.0))

        return rect.adjusted(-4.0, -4.0, 4.0, 4.0)

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: object,
    ) -> object:
        """Snap item position to the 20 px grid whenever dragged on the canvas."""
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and isinstance(value, QPointF)
        ):
            sx, sy = snap_to_grid(value.x(), value.y(), GRID_PITCH_PX)
            return QPointF(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            sc = self.scene()
            if sc is not None and hasattr(sc, "on_component_position_changed"):
                sc.on_component_position_changed(self)
        return super().itemChange(change, value)

    def _paint_lightbulb_glow(self, painter: QPainter) -> None:
        if not isinstance(self.component, Lightbulb) or self.is_ghost:
            return
        bulb = self.component
        if bulb.burned_out or bulb.brightness <= 0.005:
            return

        clamped = bulb.clamped_brightness
        radius = 16.0 + 18.0 * clamped
        grad = QRadialGradient(QPointF(0.0, 0.0), radius)

        if bulb.is_over_bright:
            # Over-bright (> 100% rated power): intense white core with fiery orange/red outer ring
            grad.setColorAt(0.0, QColor(255, 255, 240, 235))
            grad.setColorAt(0.45, QColor(255, 210, 60, 190))
            grad.setColorAt(0.8, QColor(255, 90, 30, 120))
            grad.setColorAt(1.0, QColor(255, 40, 0, 0))
        else:
            alpha_core = int(60 + 165 * clamped)
            alpha_mid = int(30 + 110 * clamped)
            grad.setColorAt(0.0, QColor(255, 248, 190, alpha_core))
            grad.setColorAt(0.55, QColor(255, 213, 79, alpha_mid))
            grad.setColorAt(1.0, QColor(255, 180, 0, 0))

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)
        painter.restore()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        _ = (option, widget)
        palette: ThemePalette = get_theme_palette(self.theme)
        w_px, h_px = self.metadata.pixel_size
        body_rect = QRectF(-w_px / 2.0, -h_px / 2.0, float(w_px), float(h_px))

        # 1. Lightbulb real-power glow (centered at 0, 0)
        self._paint_lightbulb_glow(painter)

        # 2. Rotated/flipped symbol and selection/problem frame
        painter.save()
        if self.flipped_h:
            painter.scale(-1.0, 1.0)
        if self.rotation_deg:
            painter.rotate(float(self.rotation_deg))

        if self.is_ghost:
            pen = QPen(QColor(palette.ghost_tint), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(body_rect.adjusted(-3, -3, 3, 3), 4.0, 4.0)
        elif self.diagnostic_severity == "error":
            err_col = QColor("#FF5252")
            fill_col = QColor(255, 82, 82, 32)
            painter.setPen(QPen(err_col, 2.0, Qt.PenStyle.SolidLine))
            painter.setBrush(QBrush(fill_col))
            painter.drawRoundedRect(body_rect.adjusted(-3, -3, 3, 3), 5.0, 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.diagnostic_severity == "warning":
            warn_col = QColor("#FFA726")
            fill_col = QColor(255, 167, 38, 28)
            painter.setPen(QPen(warn_col, 1.8, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(fill_col))
            painter.drawRoundedRect(body_rect.adjusted(-3, -3, 3, 3), 5.0, 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.isSelected():
            pen = QPen(QColor(palette.selection_accent), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(body_rect.adjusted(-3, -3, 3, 3), 4.0, 4.0)

        stroke_col = palette.ghost_tint if self.is_ghost else palette.symbol_stroke
        if self.diagnostic_severity == "error" and not self.is_ghost:
            stroke_col = "#FF6B6B"

        lever_arg = (
            self._lever_angle_deg
            if isinstance(self.component, Switch)
            else None
        )
        self.symbol_library.paint_symbol(
            painter,
            self.component.component_type,
            state=self.symbol_state,
            stroke_color=stroke_col,
            show_terminals=True,
            terminal_color=palette.terminal_dot,
            lever_angle_deg=lever_arg,
            rotation_deg=self.rotation_deg,
            flipped_h=self.flipped_h,
        )
        painter.restore()

        # 3. Upright component label, value/meter readout, and warning badges (never rotated/flipped)
        if not self.is_ghost:
            painter.save()
            lbl_rect, val_rect, text_align = self._upright_label_and_value_rects()

            font = QFont("Segoe UI", 8)
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()

            # Background plate for name label so intersecting wires never cut through text
            lbl_box = fm.boundingRect(lbl_rect.toRect(), int(text_align), self.component.label)
            painter.fillRect(QRectF(lbl_box).adjusted(-2.0, -1.0, 2.0, 1.0), QColor(palette.canvas_bg))
            painter.setPen(QColor(palette.symbol_text))
            painter.drawText(lbl_rect, text_align, self.component.label)

            if (
                self.component.show_value
                and self.component.component_type != "ground"
            ):
                font.setBold(isinstance(self.component, (Voltmeter, Ammeter)))
                painter.setFont(font)
                fm_val = painter.fontMetrics()
                val_text = (
                    self.live_display_value
                    if self.live_display_value is not None
                    else format_component_value_summary(self.component)
                )
                # Background plate for value readout so intersecting wires never cut through text
                val_box = fm_val.boundingRect(val_rect.toRect(), int(text_align), val_text)
                painter.fillRect(QRectF(val_box).adjusted(-3.0, -1.0, 3.0, 1.0), QColor(palette.canvas_bg))
                painter.drawText(val_rect, text_align, val_text)

            # Over-bright or problem badge in upright coordinates
            is_over_bulb = (
                isinstance(self.component, Lightbulb)
                and self.component.is_over_bright
            )
            if self.diagnostic_severity in ("error", "warning") or is_over_bulb:
                badge_col = (
                    QColor("#FF5252")
                    if self.diagnostic_severity == "error"
                    else QColor("#FFA726")
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(badge_col))
                badge_center = QPointF(18.0, -18.0)
                painter.drawEllipse(badge_center, 7.0, 7.0)
                painter.setPen(QColor("#0D1117"))
                b_font = QFont("Segoe UI", 8)
                b_font.setBold(True)
                painter.setFont(b_font)
                painter.drawText(
                    QRectF(11.0, -25.0, 14.0, 14.0),
                    Qt.AlignmentFlag.AlignCenter,
                    "!",
                )
            painter.restore()
