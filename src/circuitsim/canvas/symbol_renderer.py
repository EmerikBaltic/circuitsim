"""Qt symbol renderer with SVG loading, theme recolouring, and IEC procedural fallback."""

from __future__ import annotations

from pathlib import Path
import math
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtSvg import QSvgRenderer

from circuitsim.app.themes import ThemeMode, get_theme_palette
from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    SymbolMetadata,
    load_all_iec_metadata,
    polarity_mark_positions,
    prepare_svg_for_theme,
)


class SymbolLibrary:
    """Manages IEC symbol metadata, SVG renderers per theme/state, and procedural fallback.

    Behaviour:
        1. Loads all `.json` metadata files from `src/circuitsim/resources/symbols/iec/`.
        2. When rendering a component in a given `state` (e.g. 'open'/'closed') and
           `theme` ('dark'/'light'), checks if the corresponding `.svg` file exists.
        3. If the `.svg` file exists, validates and recolours it via
           `prepare_svg_for_theme`. If valid, renders it with `QSvgRenderer`.
        4. If the `.svg` file is missing or invalid, logs a readable warning (once per
           file) and draws the built-in procedural IEC symbol with `QPainter`.
    """

    def __init__(self, symbols_dir: Path = DEFAULT_IEC_SYMBOLS_DIR) -> None:
        self.symbols_dir: Path = symbols_dir
        self._metadata: dict[str, SymbolMetadata] = load_all_iec_metadata(symbols_dir)
        self._svg_cache: dict[tuple[str, str, str], QSvgRenderer | None] = {}
        self.warnings: list[str] = []
        self._seen_warnings: set[str] = set()

    @property
    def metadata_catalog(self) -> dict[str, SymbolMetadata]:
        """Return mapping from component_id to `SymbolMetadata`."""
        return dict(self._metadata)

    def get_metadata(self, component_id: str) -> SymbolMetadata:
        """Return `SymbolMetadata` for `component_id`."""
        if component_id not in self._metadata:
            raise KeyError(f"Unknown symbol component_id {component_id!r}.")
        return self._metadata[component_id]

    def clear_cache(self) -> None:
        """Clear cached SVG renderers so modified SVG files are reloaded from disk."""
        self._svg_cache.clear()

    def _record_warning(self, message: str) -> None:
        if message not in self._seen_warnings:
            self._seen_warnings.add(message)
            self.warnings.append(message)

    def get_svg_renderer(
        self,
        component_id: str,
        *,
        state: str | None = None,
        stroke_color: str = "#E6EDF3",
        flat_color: str | None = None,
    ) -> QSvgRenderer | None:
        """Return a themed `QSvgRenderer` if a valid SVG file exists, or `None` for fallback."""
        meta = self.get_metadata(component_id)
        svg_path = meta.svg_path_for_state(state)
        cache_key = (
            component_id,
            state or "",
            stroke_color.upper(),
            (flat_color or "").upper(),
        )
        if cache_key in self._svg_cache:
            return self._svg_cache[cache_key]

        if not svg_path.exists():
            # Normal when user has not created a custom SVG yet; use procedural IEC fallback
            self._svg_cache[cache_key] = None
            return None

        prepared = prepare_svg_for_theme(
            svg_path, meta, stroke_color=stroke_color, flat_color=flat_color
        )
        if not prepared.is_valid or prepared.svg_bytes is None:
            if prepared.warning:
                self._record_warning(prepared.warning)
            self._svg_cache[cache_key] = None
            return None

        renderer = QSvgRenderer(QByteArray(prepared.svg_bytes))
        if not renderer.isValid():
            self._record_warning(
                f"Qt QSvgRenderer could not load {svg_path.name}; using procedural IEC fallback."
            )
            self._svg_cache[cache_key] = None
            return None

        self._svg_cache[cache_key] = renderer
        return renderer

    def paint_symbol(
        self,
        painter: QPainter,
        component_id: str,
        *,
        state: str | None = None,
        stroke_color: str = "#E6EDF3",
        polarity_color: str | None = None,
        show_terminals: bool = True,
        terminal_color: str = "#58A6FF",
        lever_angle_deg: float | None = None,
        rotation_deg: int = 0,
        flipped_h: bool = False,
    ) -> bool:
        """Paint the symbol centered at `(0, 0)` in `painter` coordinates.

        Returns:
            True if rendered from an SVG file on disk, False if drawn by the
            built-in procedural IEC fallback.
        """
        meta = self.get_metadata(component_id)
        w_px, h_px = meta.pixel_size
        target_rect = QRectF(-w_px / 2.0, -h_px / 2.0, float(w_px), float(h_px))

        svg_renderer = self.get_svg_renderer(
            component_id,
            state=state,
            stroke_color=stroke_color,
            flat_color=polarity_color if component_id == "led" else None,
        )
        used_svg = False
        if svg_renderer is not None and lever_angle_deg is None and state != "burned_out":
            svg_renderer.render(painter, target_rect)
            used_svg = True
        else:
            self._paint_procedural_iec(
                painter,
                component_id,
                state=state,
                stroke_color=stroke_color,
                polarity_color=polarity_color,
                lever_angle_deg=lever_angle_deg,
                rotation_deg=rotation_deg,
                flipped_h=flipped_h,
            )

        if show_terminals:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(terminal_color))
            for term in meta.terminals:
                tx, ty = term.local_px
                painter.drawEllipse(QPointF(tx, ty), 3.0, 3.0)
            painter.restore()

        return used_svg

    def create_palette_icon(
        self,
        component_id: str,
        *,
        theme: ThemeMode | str = ThemeMode.DARK,
        size: tuple[int, int] = (64, 36),
    ) -> QIcon:
        """Render a crisp `QIcon` of the symbol for the Component Palette."""
        palette = get_theme_palette(theme)
        pixmap = QPixmap(size[0], size[1])
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(size[0] / 2.0, size[1] / 2.0)

        meta = self.get_metadata(component_id)
        w_px, h_px = meta.pixel_size
        scale = min((size[0] - 8.0) / w_px, (size[1] - 6.0) / h_px)
        painter.scale(scale, scale)

        self.paint_symbol(
            painter,
            component_id,
            state="open" if component_id == "switch" else None,
            stroke_color=palette.symbol_stroke,
            show_terminals=True,
            terminal_color=palette.terminal_dot,
        )
        painter.end()
        return QIcon(pixmap)

    def _paint_procedural_iec(
        self,
        painter: QPainter,
        component_id: str,
        *,
        state: str | None = None,
        stroke_color: str = "#E6EDF3",
        polarity_color: str | None = None,
        lever_angle_deg: float | None = None,
        rotation_deg: int = 0,
        flipped_h: bool = False,
    ) -> None:
        """Built-in procedural IEC 60617 symbol drawing (stroke-width 2, no fill)."""
        painter.save()
        pen = QPen(QColor(stroke_color), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if component_id == "resistor":
            # IEC rectangular resistor: leads (-40.. -18) and (18..40), box 36x14
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-18.0, 0.0))
            painter.drawRect(QRectF(-18.0, -7.0, 36.0, 14.0))
            painter.drawLine(QPointF(18.0, 0.0), QPointF(40.0, 0.0))

        elif component_id == "capacitor":
            # Parallel plates at x = -4 and x = +4
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-4.0, 0.0))
            painter.drawLine(QPointF(-4.0, -12.0), QPointF(-4.0, 12.0))
            painter.drawLine(QPointF(4.0, -12.0), QPointF(4.0, 12.0))
            painter.drawLine(QPointF(4.0, 0.0), QPointF(40.0, 0.0))

        elif component_id == "inductor":
            # 4 semi-circular humps from x = -20 to x = +20 (each width 10, radius 5)
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-20.0, 0.0))
            path = QPainterPath(QPointF(-20.0, 0.0))
            for i in range(4):
                x0 = -20.0 + i * 10.0
                path.arcTo(QRectF(x0, -6.0, 10.0, 12.0), 180.0, -180.0)
            painter.drawPath(path)
            painter.drawLine(QPointF(20.0, 0.0), QPointF(40.0, 0.0))

        elif component_id == "dc_voltage":
            # Circle (r = 15) and leads
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-15.0, 0.0))
            painter.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
            painter.drawLine(QPointF(15.0, 0.0), QPointF(40.0, 0.0))

            marks = polarity_mark_positions(component_id, rotation_deg=rotation_deg, flipped_h=flipped_h)
            px, py = marks["plus"]
            mx, my = marks["minus"]

            painter.save()
            if rotation_deg:
                painter.rotate(-float(rotation_deg))
            if flipped_h:
                painter.scale(-1.0, 1.0)

            pen_pol = QPen(QColor(polarity_color or stroke_color), 2.0)
            pen_pol.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_pol)

            # '+' sign centered at (px, py)
            painter.drawLine(QPointF(px - 3.0, py), QPointF(px + 3.0, py))
            painter.drawLine(QPointF(px, py - 3.0), QPointF(px, py + 3.0))
            # '-' sign centered at (mx, my)
            painter.drawLine(QPointF(mx - 3.0, my), QPointF(mx + 3.0, my))
            painter.restore()

        elif component_id == "ac_voltage":
            # Circle (r = 15) with sine wave inside
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-15.0, 0.0))
            painter.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
            painter.drawLine(QPointF(15.0, 0.0), QPointF(40.0, 0.0))
            sine = QPainterPath(QPointF(-9.0, 0.0))
            sine.cubicTo(QPointF(-4.5, -10.0), QPointF(0.0, -10.0), QPointF(0.0, 0.0))
            sine.cubicTo(QPointF(0.0, 10.0), QPointF(4.5, 10.0), QPointF(9.0, 0.0))
            painter.drawPath(sine)

        elif component_id == "dc_current":
            # Circle (r = 15) with arrow pointing toward 'pos' terminal
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-15.0, 0.0))
            painter.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
            painter.drawLine(QPointF(15.0, 0.0), QPointF(40.0, 0.0))

            marks = polarity_mark_positions(component_id, rotation_deg=rotation_deg, flipped_h=flipped_h)
            tx, ty = marks["arrow_tip"]
            ax, ay = marks["arrow_tail"]

            painter.save()
            if rotation_deg:
                painter.rotate(-float(rotation_deg))
            if flipped_h:
                painter.scale(-1.0, 1.0)

            pen_pol = QPen(QColor(polarity_color or stroke_color), 2.0)
            pen_pol.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_pol)

            painter.drawLine(QPointF(ax, ay), QPointF(tx, ty))
            dx = tx - ax
            dy = ty - ay
            length = math.hypot(dx, dy)
            if length > 0.0:
                ux = dx / length
                uy = dy / length
                barb1 = QPointF(tx - 6.0 * ux - 4.5 * uy, ty - 6.0 * uy + 4.5 * ux)
                barb2 = QPointF(tx - 6.0 * ux + 4.5 * uy, ty - 6.0 * uy - 4.5 * ux)
                painter.drawLine(QPointF(tx, ty), barb1)
                painter.drawLine(QPointF(tx, ty), barb2)
            painter.restore()

        elif component_id == "ground":
            # Terminal at (0, -20), vertical stem to (0, 0), three horizontal earth bars
            painter.drawLine(QPointF(0.0, -20.0), QPointF(0.0, 0.0))
            painter.drawLine(QPointF(-12.0, 0.0), QPointF(12.0, 0.0))
            painter.drawLine(QPointF(-8.0, 5.0), QPointF(8.0, 5.0))
            painter.drawLine(QPointF(-4.0, 10.0), QPointF(4.0, 10.0))

        elif component_id == "switch":
            # Contacts at (-16, 0) and (16, 0)
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-16.0, 0.0))
            painter.drawLine(QPointF(16.0, 0.0), QPointF(40.0, 0.0))
            painter.drawEllipse(QPointF(-16.0, 0.0), 2.5, 2.5)
            painter.drawEllipse(QPointF(16.0, 0.0), 2.5, 2.5)
            angle = (
                lever_angle_deg
                if lever_angle_deg is not None
                else (0.0 if state == "closed" else 26.0)
            )
            rad = math.radians(max(0.0, min(45.0, float(angle))))
            tip_x = -13.5 + 27.0 * math.cos(rad)
            tip_y = -27.0 * math.sin(rad)
            painter.drawLine(QPointF(-13.5, 0.0), QPointF(tip_x, tip_y))

        elif component_id == "lightbulb":
            # IEC lamp symbol: circle (r = 15) with diagonal cross ('X') inside
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-15.0, 0.0))
            if state == "burned_out":
                painter.save()
                painter.setBrush(QBrush(QColor(45, 45, 45)))
                painter.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
                painter.restore()
            else:
                painter.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
            painter.drawLine(QPointF(15.0, 0.0), QPointF(40.0, 0.0))
            d = 15.0 * 0.70710678
            painter.drawLine(QPointF(-d, -d), QPointF(d, d))
            painter.drawLine(QPointF(-d, d), QPointF(d, -d))

        elif component_id == "led":
            # IEC LED symbol with cathode flat
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-14.0, 0.0))

            if state == "burned_out":
                painter.save()
                dark_brush = QBrush(QColor(45, 45, 45))
                painter.setBrush(dark_brush)
                case_fill = QPainterPath()
                case_fill.moveTo(10.0, 10.4)
                case_fill.arcTo(QRectF(-21.0, -17.0, 34.0, 34.0), 320.0, 260.0)
                case_fill.closeSubpath()
                painter.drawPath(case_fill)
                painter.restore()

            poly = QPolygonF([QPointF(-14.0, -9.0), QPointF(-14.0, 9.0), QPointF(4.0, 0.0)])
            painter.drawPolygon(poly)
            painter.drawLine(QPointF(4.0, -11.0), QPointF(4.0, 11.0))
            painter.drawLine(QPointF(4.0, 0.0), QPointF(40.0, 0.0))

            case_path = QPainterPath()
            case_path.moveTo(10.0, 10.4)
            case_path.arcTo(QRectF(-21.0, -17.0, 34.0, 34.0), 320.0, 260.0)
            painter.drawPath(case_path)

            painter.save()
            if polarity_color:
                painter.setPen(QPen(QColor(polarity_color), 2.0))
            painter.drawLine(QPointF(10.0, -10.4), QPointF(10.0, 10.4))
            painter.restore()

            if state == "burned_out":
                # Dark body with cross across the LED body
                d = 10.0
                painter.drawLine(QPointF(-d, -d), QPointF(d, d))
                painter.drawLine(QPointF(-d, d), QPointF(d, -d))
            else:
                painter.drawLine(QPointF(1.0, -9.0), QPointF(10.0, -16.0))
                painter.drawLine(QPointF(5.0, -16.0), QPointF(10.0, -16.0))
                painter.drawLine(QPointF(10.0, -11.0), QPointF(10.0, -16.0))
                painter.drawLine(QPointF(7.0, -7.0), QPointF(16.0, -14.0))
                painter.drawLine(QPointF(11.0, -14.0), QPointF(16.0, -14.0))
                painter.drawLine(QPointF(16.0, -9.0), QPointF(16.0, -14.0))

        elif component_id in ("voltmeter", "ammeter"):
            # Circle (r = 15) and leads
            painter.drawLine(QPointF(-40.0, 0.0), QPointF(-15.0, 0.0))
            painter.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
            painter.drawLine(QPointF(15.0, 0.0), QPointF(40.0, 0.0))

            # The letter ('V' or 'A') and '+' polarity mark drawn upright
            painter.save()
            if rotation_deg:
                painter.rotate(-float(rotation_deg))
            if flipped_h:
                painter.scale(-1.0, 1.0)

            if component_id == "voltmeter":
                painter.drawLine(QPointF(-5.0, -6.0), QPointF(0.0, 6.0))
                painter.drawLine(QPointF(0.0, 6.0), QPointF(5.0, -6.0))
            else:
                painter.drawLine(QPointF(-5.0, 6.0), QPointF(0.0, -6.0))
                painter.drawLine(QPointF(0.0, -6.0), QPointF(5.0, 6.0))
                painter.drawLine(QPointF(-3.2, 1.5), QPointF(3.2, 1.5))

            marks = polarity_mark_positions(component_id, rotation_deg=rotation_deg, flipped_h=flipped_h)
            if "plus" in marks:
                px, py = marks["plus"]
                pen_pol = QPen(QColor(polarity_color or stroke_color), 1.8)
                pen_pol.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen_pol)
                painter.drawLine(QPointF(px - 2.5, py), QPointF(px + 2.5, py))
                painter.drawLine(QPointF(px, py - 2.5), QPointF(px, py + 2.5))

            painter.restore()

        else:
            painter.drawRect(QRectF(-20.0, -10.0, 40.0, 20.0))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(
                QRectF(-20.0, -10.0, 40.0, 20.0),
                Qt.AlignmentFlag.AlignCenter,
                component_id[:4],
            )

        painter.restore()
