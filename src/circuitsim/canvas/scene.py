"""QGraphicsScene for the schematic editor with 20 px grid and ghost preview."""

from __future__ import annotations

import math
from PySide6.QtCore import QLineF, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene

from circuitsim.app.themes import ThemeMode, get_theme_palette
from circuitsim.canvas.component_item import (
    COMPONENT_PREFIXES,
    ComponentItem,
    create_default_component_model,
)
from circuitsim.canvas.symbol_geometry import GRID_PITCH_PX, snap_to_grid
from circuitsim.canvas.symbol_renderer import SymbolLibrary


class CircuitScene(QGraphicsScene):
    """Schematic canvas scene managing components, grid rendering, and ghost placement."""

    component_placed = Signal(object)  # Emits placed ComponentItem
    selection_info_changed = Signal(object)  # Emits selected ComponentItem or None

    def __init__(
        self,
        symbol_library: SymbolLibrary,
        *,
        theme: ThemeMode = ThemeMode.DARK,
    ) -> None:
        super().__init__()
        self.symbol_library: SymbolLibrary = symbol_library
        self.theme: ThemeMode = theme
        self.show_grid: bool = True
        self._counters: dict[str, int] = {}
        self._placed_items: list[ComponentItem] = []
        self._ghost_item: ComponentItem | None = None

        self.setSceneRect(-2000.0, -2000.0, 4000.0, 4000.0)
        self.selectionChanged.connect(self._on_selection_changed)

    @property
    def placed_items(self) -> list[ComponentItem]:
        """Return list of placed `ComponentItem` objects on the canvas."""
        return list(self._placed_items)

    def set_theme(self, theme: ThemeMode) -> None:
        """Switch canvas and all placed items between Dark and Light themes."""
        self.theme = theme
        for item in self._placed_items:
            item.set_theme(theme)
        if self._ghost_item is not None:
            self._ghost_item.set_theme(theme)
        self.update()

    def set_show_grid(self, visible: bool) -> None:
        """Toggle visibility of the 20 px background grid."""
        self.show_grid = bool(visible)
        self.update()

    def next_component_name(self, component_id: str) -> str:
        """Generate the next sequential designator (e.g. 'R1', 'R2', 'C1')."""
        prefix = COMPONENT_PREFIXES.get(component_id, "U")
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}{count}"

    def show_ghost_preview(self, component_id: str, scene_pos: QPointF) -> None:
        """Create or move the snapping ghost preview item for `component_id`."""
        if (
            self._ghost_item is None
            or self._ghost_item.component.component_type != component_id
        ):
            self.hide_ghost_preview()
            temp_model = create_default_component_model(component_id, "PREVIEW")
            self._ghost_item = ComponentItem(
                temp_model,
                self.symbol_library,
                theme=self.theme,
                is_ghost=True,
            )
            self.addItem(self._ghost_item)

        self._ghost_item.set_snapped_pos(scene_pos.x(), scene_pos.y())

    def hide_ghost_preview(self) -> None:
        """Remove the ghost preview item from the scene if active."""
        if self._ghost_item is not None:
            self.removeItem(self._ghost_item)
            self._ghost_item = None

    def place_new_component(
        self,
        component_id: str,
        scene_pos: QPointF,
    ) -> ComponentItem:
        """Instantiate and place a new component snapped to the grid at `scene_pos`."""
        name = self.next_component_name(component_id)
        model = create_default_component_model(component_id, name)
        item = ComponentItem(
            model,
            self.symbol_library,
            theme=self.theme,
            is_ghost=False,
        )
        sx, sy = snap_to_grid(scene_pos.x(), scene_pos.y(), GRID_PITCH_PX)
        item.setPos(sx, sy)
        self.addItem(item)
        self._placed_items.append(item)

        self.clearSelection()
        item.setSelected(True)
        self.component_placed.emit(item)
        return item

    def clear_schematic(self) -> None:
        """Remove all placed components and reset designator counters."""
        self.hide_ghost_preview()
        for item in list(self._placed_items):
            self.removeItem(item)
        self._placed_items.clear()
        self._counters.clear()
        self.selection_info_changed.emit(None)

    def _on_selection_changed(self) -> None:
        selected = [
            it for it in self.selectedItems() if isinstance(it, ComponentItem)
        ]
        self.selection_info_changed.emit(selected[0] if selected else None)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the themed canvas background and 20 px minor / 100 px major grid."""
        palette = get_theme_palette(self.theme)
        painter.fillRect(rect, QColor(palette.canvas_bg))

        if not self.show_grid:
            return

        minor_step = GRID_PITCH_PX
        major_step = GRID_PITCH_PX * 5

        left = int(math.floor(rect.left() / minor_step) * minor_step)
        right = int(math.ceil(rect.right() / minor_step) * minor_step)
        top = int(math.floor(rect.top() / minor_step) * minor_step)
        bottom = int(math.ceil(rect.bottom() / minor_step) * minor_step)

        minor_lines: list[QLineF] = []
        major_lines: list[QLineF] = []

        for x in range(left, right + minor_step, minor_step):
            line = QLineF(float(x), rect.top(), float(x), rect.bottom())
            if x % major_step == 0:
                major_lines.append(line)
            else:
                minor_lines.append(line)

        for y in range(top, bottom + minor_step, minor_step):
            line = QLineF(rect.left(), float(y), rect.right(), float(y))
            if y % major_step == 0:
                major_lines.append(line)
            else:
                minor_lines.append(line)

        painter.save()
        painter.setPen(QPen(QColor(palette.grid_minor), 1.0))
        painter.drawLines(minor_lines)

        painter.setPen(QPen(QColor(palette.grid_major), 1.0))
        painter.drawLines(major_lines)

        # Subtle origin cross at (0, 0)
        origin_pen = QPen(QColor(palette.grid_origin), 1.2)
        painter.setPen(origin_pen)
        painter.drawLine(QLineF(-10.0, 0.0, 10.0, 0.0))
        painter.drawLine(QLineF(0.0, -10.0, 0.0, 10.0))
        painter.restore()
