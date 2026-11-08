"""QGraphicsObject for orthogonal schematic wires and live wire-routing preview."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

from circuitsim.app.themes import ThemeMode, ThemePalette, get_theme_palette
from circuitsim.canvas.connectivity import (
    PointPx,
    WireSpec,
    simplify_orthogonal_points,
)


class WireItem(QGraphicsObject):
    """Orthogonal wire polyline on the schematic canvas.

    Stores its vertices in scene pixel coordinates (`points`) while keeping
    `pos() == (0, 0)`. Supports selection, theme switching, and a dashed
    live-preview mode while the user is routing a new wire.
    """

    def __init__(
        self,
        wire_id: str,
        points: Sequence[tuple[float, float] | PointPx],
        *,
        theme: ThemeMode = ThemeMode.DARK,
        is_preview: bool = False,
    ) -> None:
        super().__init__()
        self.wire_id: str = wire_id
        self.theme: ThemeMode = theme
        self.is_preview: bool = is_preview
        self._points: tuple[PointPx, ...] = simplify_orthogonal_points(
            points, snap=True
        )
        self._path: QPainterPath = QPainterPath()
        self._hit_shape: QPainterPath = QPainterPath()
        self.diagnostic_severity: str | None = None
        self.diagnostic_message: str = ""
        self._rebuild_paths()

        if not is_preview:
            self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.setZValue(5.0)
        else:
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.setZValue(95.0)

    @property
    def points(self) -> tuple[PointPx, ...]:
        """Return the normalized orthogonal polyline points in scene coordinates."""
        return self._points

    def set_points(
        self, points: Sequence[tuple[float, float] | PointPx]
    ) -> None:
        """Update the wire's polyline points and trigger a geometry/scene repaint."""
        norm = simplify_orthogonal_points(points, snap=True)
        if norm == self._points:
            return
        self.prepareGeometryChange()
        self._points = norm
        self._rebuild_paths()
        self.update()

    def set_theme(self, theme: ThemeMode) -> None:
        """Update theme color and repaint."""
        self.theme = theme
        self.update()

    def set_diagnostic(
        self, severity: str | None, message: str = ""
    ) -> None:
        """Set or clear canvas problem highlighting on this wire."""
        if self.diagnostic_severity == severity and self.diagnostic_message == message:
            return
        self.diagnostic_severity = severity
        self.diagnostic_message = message
        self.setToolTip(message)
        self.update()

    def to_wire_spec(self) -> WireSpec:
        """Convert to a pure-Python `WireSpec` for connectivity extraction."""
        return WireSpec(wire_id=self.wire_id, points=self._points)

    def _rebuild_paths(self) -> None:
        path = QPainterPath()
        if len(self._points) >= 2:
            p0 = self._points[0]
            path.moveTo(float(p0[0]), float(p0[1]))
            for px, py in self._points[1:]:
                path.lineTo(float(px), float(py))
        self._path = path

        stroker = QPainterPathStroker()
        stroker.setWidth(10.0)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._hit_shape = stroker.createStroke(path)

    def boundingRect(self) -> QRectF:
        if self._path.isEmpty():
            return QRectF(0.0, 0.0, 1.0, 1.0)
        return self._hit_shape.boundingRect().adjusted(-4.0, -4.0, 4.0, 4.0)

    def shape(self) -> QPainterPath:
        return self._hit_shape

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        _ = (option, widget)
        if len(self._points) < 2:
            return

        palette: ThemePalette = get_theme_palette(self.theme)
        painter.save()

        if self.is_preview:
            pen = QPen(
                QColor(palette.terminal_hover),
                2.4,
                Qt.PenStyle.DashLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.MiterJoin,
            )
            painter.setPen(pen)
            painter.drawPath(self._path)
            # Draw start and end preview rings
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for ep in (self._points[0], self._points[-1]):
                painter.drawEllipse(
                    QPointF(float(ep[0]), float(ep[1])), 5.0, 5.0
                )
        elif self.isSelected():
            # Subtle outer glow + accent wire stroke
            glow_pen = QPen(
                QColor(palette.selection_accent),
                5.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            glow_col = QColor(palette.selection_accent)
            glow_col.setAlpha(90)
            glow_pen.setColor(glow_col)
            painter.setPen(glow_pen)
            painter.drawPath(self._path)

            main_pen = QPen(
                QColor(palette.selection_accent),
                2.4,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.MiterJoin,
            )
            painter.setPen(main_pen)
            painter.drawPath(self._path)
        elif self.diagnostic_severity in ("error", "warning"):
            diag_col = (
                QColor("#FF5252")
                if self.diagnostic_severity == "error"
                else QColor("#FFA726")
            )
            glow_col = QColor(diag_col)
            glow_col.setAlpha(85)
            painter.setPen(
                QPen(
                    glow_col,
                    5.5,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(self._path)
            painter.setPen(
                QPen(
                    diag_col,
                    2.4,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.MiterJoin,
                )
            )
            painter.drawPath(self._path)
        else:
            pen = QPen(
                QColor(palette.symbol_stroke),
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.MiterJoin,
            )
            painter.setPen(pen)
            painter.drawPath(self._path)

        painter.restore()
