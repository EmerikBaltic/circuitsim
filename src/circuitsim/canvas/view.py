"""Interactive QGraphicsView with zoom, pan, and palette drag-and-drop."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsView

from circuitsim.canvas.component_item import ComponentItem
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_geometry import GRID_PITCH_PX, snap_to_grid

MIME_COMPONENT_ID = "application/x-circuitsim-component-id"


class CircuitView(QGraphicsView):
    """Schematic viewport supporting zoom, middle/Space pan, and ghost drop placement."""

    cursor_grid_moved = Signal(float, float, int, int)  # (x_px, y_px, gx, gy)
    zoom_changed = Signal(float)  # Zoom factor (1.0 = 100%)

    MIN_ZOOM: float = 0.25
    MAX_ZOOM: float = 4.0
    ZOOM_STEP: float = 1.15

    def __init__(self, circuit_scene: CircuitScene) -> None:
        super().__init__(circuit_scene)
        self.circuit_scene: CircuitScene = circuit_scene
        self._zoom_factor: float = 1.0
        self._is_panning: bool = False
        self._space_held: bool = False
        self._pan_start: QPoint = QPoint()

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.centerOn(0.0, 0.0)

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    def reset_zoom(self) -> None:
        """Reset viewport zoom to 100% and center on `(0, 0)`."""
        self.resetTransform()
        self._zoom_factor = 1.0
        self.zoom_changed.emit(self._zoom_factor)

    def zoom_in(self) -> None:
        self._apply_zoom(self.ZOOM_STEP)

    def zoom_out(self) -> None:
        self._apply_zoom(1.0 / self.ZOOM_STEP)

    def _apply_zoom(self, factor: float) -> None:
        new_zoom = self._zoom_factor * factor
        if new_zoom < self.MIN_ZOOM or new_zoom > self.MAX_ZOOM:
            return
        self._zoom_factor = new_zoom
        self.scale(factor, factor)
        self.zoom_changed.emit(self._zoom_factor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom smoothly around the cursor using the mouse wheel."""
        delta = event.angleDelta().y()
        if delta > 0:
            self._apply_zoom(self.ZOOM_STEP)
        elif delta < 0:
            self._apply_zoom(1.0 / self.ZOOM_STEP)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_held
        ):
            self._is_panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pt: QPointF = self.mapToScene(event.pos())
        sx, sy = snap_to_grid(scene_pt.x(), scene_pt.y(), GRID_PITCH_PX)
        gx = int(round(sx / GRID_PITCH_PX))
        gy = int(round(sy / GRID_PITCH_PX))
        self.cursor_grid_moved.emit(sx, sy, gx, gy)

        if self._is_panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_panning and event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        ):
            self._is_panning = False
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._space_held
                else Qt.CursorShape.ArrowCursor
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        if event.key() == Qt.Key.Key_R:
            for item in self.circuit_scene.selectedItems():
                if isinstance(item, ComponentItem):
                    item.rotate_90_cw()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F:
            for item in self.circuit_scene.selectedItems():
                if isinstance(item, ComponentItem):
                    item.flip_horizontal()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._is_panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(MIME_COMPONENT_ID):
            comp_id = bytes(event.mimeData().data(MIME_COMPONENT_ID)).decode("utf-8")
            scene_pos = self.mapToScene(event.position().toPoint())
            self.circuit_scene.show_ghost_preview(comp_id, scene_pos)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(MIME_COMPONENT_ID):
            comp_id = bytes(event.mimeData().data(MIME_COMPONENT_ID)).decode("utf-8")
            scene_pos = self.mapToScene(event.position().toPoint())
            self.circuit_scene.show_ghost_preview(comp_id, scene_pos)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.circuit_scene.hide_ghost_preview()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasFormat(MIME_COMPONENT_ID):
            comp_id = bytes(event.mimeData().data(MIME_COMPONENT_ID)).decode("utf-8")
            scene_pos = self.mapToScene(event.position().toPoint())
            self.circuit_scene.hide_ghost_preview()
            self.circuit_scene.place_new_component(comp_id, scene_pos)
            event.acceptProposedAction()
            self.setFocus()
            return
        super().dropEvent(event)
