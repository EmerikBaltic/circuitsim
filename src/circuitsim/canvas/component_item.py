"""Canvas QGraphicsObject for schematic components, upright labels, switch animation, and bulb glow."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QRadialGradient,
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


def create_default_component_model(component_id: str, name: str) -> Component:
    """Create a default physics `Component` instance for `component_id`."""
    n0, n1 = f"{name}_a", f"{name}_b"
    if component_id == "resistor":
        return Resistor(name, n0, n1, resistance=1000.0)
    if component_id == "capacitor":
        return Capacitor(name, n0, n1, capacitance=1e-6)
    if component_id == "inductor":
        return Inductor(name, n0, n1, inductance=10e-3, dcr=1.0)
    if component_id == "dc_voltage":
        return DCVoltageSource(name, n0, n1, voltage=12.0)
    if component_id == "ac_voltage":
        return ACVoltageSource(name, n0, n1, amplitude=10.0, frequency=1000.0)
    if component_id == "dc_current":
        return DCCurrentSource(name, n0, n1, current=0.01)
    if component_id == "ground":
        return Ground(name, "0")
    if component_id == "switch":
        return Switch(name, n0, n1, closed=False)
    if component_id == "lightbulb":
        return Lightbulb(name, n0, n1, rated_power=60.0, rated_voltage=120.0)
    if component_id == "voltmeter":
        return Voltmeter(name, n0, n1)
    if component_id == "ammeter":
        return Ammeter(name, n0, n1)
    raise ValueError(f"Unknown component_id {component_id!r}.")


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
    ) -> None:
        super().__init__()
        self.component: Component = component
        self.symbol_library: SymbolLibrary = symbol_library
        self.metadata: SymbolMetadata = symbol_library.get_metadata(
            component.component_type
        )
        self.theme: ThemeMode = theme
        self.is_ghost: bool = is_ghost
        self.rotation_deg: int = 0
        self.flipped_h: bool = False

        # Live simulation visual states
        self.live_display_value: str | None = None
        self.diagnostic_severity: str | None = None  # "error", "warning", or None
        self.diagnostic_message: str = ""
        self.diagnostic_code: str = ""
        self.is_unconnected: bool = False

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

    def rotate_90_cw(self) -> None:
        """Rotate component 90 degrees clockwise around its center `(0, 0)`."""
        self.rotation_deg = (self.rotation_deg + 90) % 360
        self._apply_local_transform()

    def rotate_90_ccw(self) -> None:
        """Rotate component 90 degrees counter-clockwise around its center `(0, 0)`."""
        self.rotation_deg = (self.rotation_deg - 90) % 360
        self._apply_local_transform()

    def set_rotation_deg(self, rotation_deg: int) -> None:
        """Set explicit rotation angle in `{0, 90, 180, 270}`."""
        self.rotation_deg = int(rotation_deg) % 360
        self._apply_local_transform()

    def flip_horizontal(self) -> None:
        """Mirror the component horizontally across its local Y axis."""
        self.flipped_h = not self.flipped_h
        self._apply_local_transform()

    def set_flipped_h(self, flipped: bool) -> None:
        """Set explicit horizontal mirror state."""
        self.flipped_h = bool(flipped)
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

    def _upright_label_and_value_rects(
        self,
    ) -> tuple[QRectF, QRectF, Qt.AlignmentFlag]:
        """Compute upright (unrotated, unmirrored) label and value rectangles."""
        if self.rotation_deg in (90, 270):
            # Symbol is vertical (40x80 px): place label and value upright to the right
            lbl_rect = QRectF(18.0, -18.0, 96.0, 17.0)
            val_rect = QRectF(18.0, 1.0, 110.0, 17.0)
            align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            return lbl_rect, val_rect, align

        lbl_x = self.metadata.label_offset[0] * GRID_PITCH_PX
        lbl_y = self.metadata.label_offset[1] * GRID_PITCH_PX
        val_x = self.metadata.value_offset[0] * GRID_PITCH_PX
        val_y = self.metadata.value_offset[1] * GRID_PITCH_PX
        lbl_rect = QRectF(lbl_x - 50.0, lbl_y - 9.0, 100.0, 18.0)
        val_rect = QRectF(val_x - 60.0, val_y - 9.0, 120.0, 18.0)
        return lbl_rect, val_rect, Qt.AlignmentFlag.AlignCenter

    def boundingRect(self) -> QRectF:
        w_px, h_px = self.metadata.pixel_size
        max_dim = float(max(w_px, h_px))
        # Generous bounding box covering horizontal/vertical orientations and upright labels
        return QRectF(
            -max_dim / 2.0 - 28.0,
            -max_dim / 2.0 - 28.0,
            max_dim + 150.0,
            max_dim + 56.0,
        )

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
            painter.drawRoundedRect(body_rect.adjusted(-4, -4, 4, 4), 4.0, 4.0)
        elif self.diagnostic_severity == "error":
            err_col = QColor("#FF5252")
            fill_col = QColor(255, 82, 82, 32)
            painter.setPen(QPen(err_col, 2.0, Qt.PenStyle.SolidLine))
            painter.setBrush(QBrush(fill_col))
            painter.drawRoundedRect(body_rect.adjusted(-5, -5, 5, 5), 5.0, 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.diagnostic_severity == "warning":
            warn_col = QColor("#FFA726")
            fill_col = QColor(255, 167, 38, 28)
            painter.setPen(QPen(warn_col, 1.8, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(fill_col))
            painter.drawRoundedRect(body_rect.adjusted(-5, -5, 5, 5), 5.0, 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.isSelected():
            pen = QPen(QColor(palette.selection_accent), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(body_rect.adjusted(-4, -4, 4, 4), 4.0, 4.0)

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
        )
        painter.restore()

        # 3. Upright component label, value/meter readout, and warning badges (never rotated/flipped)
        if not self.is_ghost:
            painter.save()
            lbl_rect, val_rect, text_align = self._upright_label_and_value_rects()

            font = QFont("Segoe UI", 8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(palette.symbol_text))
            painter.drawText(lbl_rect, text_align, self.component.label)

            if (
                self.component.show_value
                and self.component.component_type != "ground"
            ):
                font.setBold(isinstance(self.component, (Voltmeter, Ammeter)))
                painter.setFont(font)
                val_text = (
                    self.live_display_value
                    if self.live_display_value is not None
                    else format_component_value_summary(self.component)
                )
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
