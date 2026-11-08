"""Canvas QGraphicsObject for schematic components and snapping ghost previews."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

from circuitsim.app.themes import ThemeMode, ThemePalette, get_theme_palette
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
        return "ON" if comp.closed else "OFF"
    if isinstance(comp, Lightbulb):
        return f"{comp.rated_power:g}W / {comp.rated_voltage:g}V"
    if isinstance(comp, (Voltmeter, Ammeter)):
        return comp.format_reading()
    return ""


class ComponentItem(QGraphicsObject):
    """Visual schematic item representing an electrical component on the canvas.

    Supports:
        - Grid snapping (20 px pitch)
        - 90-degree rotations and horizontal flip
        - SVG rendering (if file exists in `resources/symbols/iec/`) or procedural IEC fallback
        - Ghost preview mode during drag-and-drop from the Component Palette
    """

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

        if not is_ghost:
            self.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            )
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.setOpacity(0.65)
            self.setZValue(100.0)

    @property
    def symbol_state(self) -> str | None:
        """Return active symbol state name (e.g. 'open' or 'closed' for Switch)."""
        if isinstance(self.component, Switch):
            return "closed" if self.component.closed else "open"
        return None

    def set_theme(self, theme: ThemeMode) -> None:
        """Update item theme and trigger a repaint."""
        self.theme = theme
        self.update()

    def set_snapped_pos(self, x_px: float, y_px: float) -> None:
        """Snap `(x_px, y_px)` to the 20 px grid and set the item's scene position."""
        sx, sy = snap_to_grid(x_px, y_px, GRID_PITCH_PX)
        self.setPos(sx, sy)

    def rotate_90_cw(self) -> None:
        """Rotate component 90 degrees clockwise around its center `(0, 0)`."""
        self.rotation_deg = (self.rotation_deg + 90) % 360
        self._apply_local_transform()

    def flip_horizontal(self) -> None:
        """Mirror the component horizontally across its local Y axis."""
        self.flipped_h = not self.flipped_h
        self._apply_local_transform()

    def _apply_local_transform(self) -> None:
        transform = QTransform()
        if self.flipped_h:
            transform.scale(-1.0, 1.0)
        if self.rotation_deg:
            transform.rotate(float(self.rotation_deg))
        self.setTransform(transform)
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

    def boundingRect(self) -> QRectF:
        w_px, h_px = self.metadata.pixel_size
        # Include padding for component name and value labels above/below the symbol
        pad_x = 24.0
        pad_y = 26.0
        return QRectF(
            -w_px / 2.0 - pad_x,
            -h_px / 2.0 - pad_y,
            w_px + 2.0 * pad_x,
            h_px + 2.0 * pad_y,
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
        return super().itemChange(change, value)

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

        # 1. Selection or ghost highlight frame
        if self.is_ghost:
            painter.save()
            pen = QPen(QColor(palette.ghost_tint), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(body_rect.adjusted(-4, -4, 4, 4), 4.0, 4.0)
            painter.restore()
        elif self.isSelected():
            painter.save()
            pen = QPen(QColor(palette.selection_accent), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(body_rect.adjusted(-4, -4, 4, 4), 4.0, 4.0)
            painter.restore()

        # 2. Symbol stroke and terminals
        stroke_col = palette.ghost_tint if self.is_ghost else palette.symbol_stroke
        self.symbol_library.paint_symbol(
            painter,
            self.component.component_type,
            state=self.symbol_state,
            stroke_color=stroke_col,
            show_terminals=True,
            terminal_color=palette.terminal_dot,
        )

        # 3. Component label and value text (skip on ghost or ground value)
        if not self.is_ghost:
            painter.save()
            font = QFont("Segoe UI", 8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(palette.symbol_text))

            lbl_x = self.metadata.label_offset[0] * GRID_PITCH_PX
            lbl_y = self.metadata.label_offset[1] * GRID_PITCH_PX
            lbl_rect = QRectF(lbl_x - 45.0, lbl_y - 9.0, 90.0, 18.0)
            painter.drawText(
                lbl_rect, Qt.AlignmentFlag.AlignCenter, self.component.label
            )

            if (
                self.component.show_value
                and self.component.component_type != "ground"
            ):
                font.setBold(False)
                painter.setFont(font)
                val_x = self.metadata.value_offset[0] * GRID_PITCH_PX
                val_y = self.metadata.value_offset[1] * GRID_PITCH_PX
                val_rect = QRectF(val_x - 55.0, val_y - 9.0, 110.0, 18.0)
                painter.drawText(
                    val_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    format_component_value_summary(self.component),
                )
            painter.restore()
