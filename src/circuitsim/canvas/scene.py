"""QGraphicsScene for the schematic editor with 20 px grid, wiring, undo/redo, and netlist extraction."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from typing import Sequence

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from circuitsim.app.themes import ThemeMode, get_theme_palette
from circuitsim.canvas.commands import (
    AddComponentCommand,
    AddWireCommand,
    DeleteItemsCommand,
    EditComponentParametersCommand,
    FlipComponentsCommand,
    MoveComponentsCommand,
    PasteItemsCommand,
    RotateComponentsCommand,
    ToggleJunctionCommand,
)
from circuitsim.canvas.component_item import (
    COMPONENT_PREFIXES,
    ComponentItem,
    create_default_component_model,
)
from circuitsim.canvas.connectivity import (
    ConnectivityResult,
    PlacedComponentSpec,
    PointPx,
    WireSpec,
    extract_connectivity,
    find_wires_attached_to_components,
    normalize_point_px,
    point_on_wire,
    reroute_wires_for_updated_terminals,
    route_orthogonal_wire,
    simplify_orthogonal_points,
)
from circuitsim.canvas.symbol_geometry import GRID_PITCH_PX, snap_to_grid
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.wire_item import WireItem
from circuitsim.components.base import Component
from circuitsim.components.switch import Switch
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.simulation_session import (
    SimulationFrame,
    SimulationState,
)


@dataclass(frozen=True)
class _ClipboardComponentEntry:
    component_snapshot: Component
    pos_px: tuple[float, float]
    rotation_deg: int
    flipped_h: bool


@dataclass(frozen=True)
class _ClipboardData:
    components: tuple[_ClipboardComponentEntry, ...]
    wires: tuple[tuple[PointPx, ...], ...]
    junctions: tuple[PointPx, ...]


class CircuitScene(QGraphicsScene):
    """Schematic canvas scene managing components, orthogonal wires, junctions, and undo/redo."""

    component_placed = Signal(object)  # Emits placed ComponentItem
    selection_info_changed = Signal(object)  # Emits selected ComponentItem or None
    circuit_modified = Signal()  # Emits whenever components, wires, or junctions change
    switch_toggled_by_user = Signal(str, bool)  # (switch_name, closed)
    component_parameters_edited = Signal(str, object)  # (comp_name, dict[str, float])

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
        self.undo_stack: QUndoStack = QUndoStack(self)

        self._counters: dict[str, int] = {}
        self._wire_counter: int = 0
        self._placed_items: list[ComponentItem] = []
        self._wire_items: list[WireItem] = []
        self._explicit_junctions: set[PointPx] = set()
        self._active_junction_dots: set[PointPx] = set()

        # Ghost component preview during palette drag
        self._ghost_item: ComponentItem | None = None

        # Interactive wire routing preview & terminal hover
        self._hovered_terminal_pt: PointPx | None = None
        self._wire_start_pt: PointPx | None = None
        self._wire_prefer_horiz: bool = True
        self._preview_wire_item: WireItem | None = None

        # Component drag-move tracking for live attached-wire re-routing & QUndoStack
        self._move_tracking_active: bool = False
        self._suppress_live_reroute: bool = False
        self._move_start_positions: dict[ComponentItem, tuple[float, float]] = {}
        self._move_start_terminals: dict[str, dict[str, PointPx]] = {}
        self._move_start_wires: dict[WireItem, tuple[PointPx, ...]] = {}

        # Internal clipboard for Copy / Cut / Paste
        self._clipboard: _ClipboardData | None = None
        self._paste_serial: int = 0

        self.setSceneRect(-2000.0, -2000.0, 4000.0, 4000.0)
        self.selectionChanged.connect(self._on_selection_changed)

    @property
    def placed_items(self) -> list[ComponentItem]:
        """Return list of placed `ComponentItem` objects on the canvas."""
        return list(self._placed_items)

    @property
    def placed_wires(self) -> list[WireItem]:
        """Return list of placed `WireItem` objects on the canvas."""
        return list(self._wire_items)

    @property
    def explicit_junctions(self) -> set[PointPx]:
        """Return copy of user-placed explicit junction dot coordinates."""
        return set(self._explicit_junctions)

    @property
    def active_junction_dots(self) -> set[PointPx]:
        """Return copy of all visual junction dots (T-junctions + explicit junctions)."""
        return set(self._active_junction_dots)

    @property
    def is_drawing_wire(self) -> bool:
        """Return True if an interactive wire route is currently in progress."""
        return self._wire_start_pt is not None

    def set_theme(self, theme: ThemeMode) -> None:
        """Switch canvas and all placed items/wires between Dark and Light themes."""
        self.theme = theme
        for item in self._placed_items:
            item.set_theme(theme)
        for wire in self._wire_items:
            wire.set_theme(theme)
        if self._ghost_item is not None:
            self. _ghost_item.set_theme(theme)
        if self._preview_wire_item is not None:
            self._preview_wire_item.set_theme(theme)
        self.update()

    def set_show_grid(self, visible: bool) -> None:
        """Toggle visibility of the 20 px background grid."""
        self.show_grid = bool(visible)
        self.update()

    def next_component_name(self, component_id: str) -> str:
        """Generate the next sequential designator (e.g. 'R1', 'R2', 'C1')."""
        prefix = COMPONENT_PREFIXES.get(component_id, "U")
        existing_names = {it.component.name for it in self._placed_items}
        count = self._counters.get(prefix, 0) + 1
        while f"{prefix}{count}" in existing_names:
            count += 1
        self._counters[prefix] = count
        return f"{prefix}{count}"

    def next_wire_id(self) -> str:
        """Generate the next sequential wire identifier ('W1', 'W2', ...)."""
        self._wire_counter += 1
        return f"W{self._wire_counter}"

    # ------------------------------------------------------------------
    # Low-level item registration (called by QUndoCommand redo/undo)
    # ------------------------------------------------------------------

    def _insert_component_item(
        self,
        item: ComponentItem,
        *,
        select: bool = True,
        refresh: bool = True,
    ) -> None:
        if item not in self._placed_items:
            self._placed_items.append(item)
        if item.scene() is not self:
            self.addItem(item)
        if select:
            self.clearSelection()
            item.setSelected(True)
        if refresh:
            self.refresh_connectivity_visuals()
            self.component_placed.emit(item)

    def _remove_component_item(
        self,
        item: ComponentItem,
        *,
        refresh: bool = True,
    ) -> None:
        if item in self._placed_items:
            self._placed_items.remove(item)
        if item.scene() is self:
            self.removeItem(item)
        if refresh:
            self.refresh_connectivity_visuals()

    def _insert_wire_item(
        self,
        wire: WireItem,
        *,
        select: bool = False,
        refresh: bool = True,
    ) -> None:
        if wire not in self._wire_items:
            self._wire_items.append(wire)
        if wire.scene() is not self:
            self.addItem(wire)
        if select:
            wire.setSelected(True)
        if refresh:
            self.refresh_connectivity_visuals()

    def _remove_wire_item(
        self,
        wire: WireItem,
        *,
        refresh: bool = True,
    ) -> None:
        if wire in self._wire_items:
            self._wire_items.remove(wire)
        if wire.scene() is self:
            self.removeItem(wire)
        if refresh:
            self.refresh_connectivity_visuals()

    def _set_explicit_junction(
        self,
        pt: PointPx,
        *,
        present: bool,
        refresh: bool = True,
    ) -> None:
        norm = normalize_point_px(pt, snap=True)
        if present:
            self._explicit_junctions.add(norm)
        else:
            self._explicit_junctions.discard(norm)
        if refresh:
            self.refresh_connectivity_visuals()

    def refresh_connectivity_visuals(self) -> None:
        """Recompute active junction dots (T-junctions + explicit junctions) and repaint."""
        res = self.extract_connectivity_result()
        self._active_junction_dots = res.junction_dots
        self.circuit_modified.emit()
        self.update()

    # ------------------------------------------------------------------
    # Palette Ghost Preview & Component Placement
    # ------------------------------------------------------------------

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
        *,
        rotation_deg: int = 0,
        flipped_h: bool = False,
    ) -> ComponentItem:
        """Instantiate and place a new component snapped to the grid via `QUndoStack`."""
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
        if rotation_deg:
            item.set_rotation_deg(rotation_deg)
        if flipped_h:
            item.set_flipped_h(flipped_h)

        self.undo_stack.push(AddComponentCommand(self, item))
        return item

    # ------------------------------------------------------------------
    # Wiring, Terminal Hit-Testing, Live Wire Preview & Junction Dots
    # ------------------------------------------------------------------

    def all_component_terminals_px(self) -> dict[str, dict[str, PointPx]]:
        """Return `{comp_name: {term_name: (x_px, y_px)}}` for all placed components."""
        return {
            item.component.name: item.terminal_scene_positions_px()
            for item in self._placed_items
        }

    def find_terminal_near(
        self,
        scene_pos: QPointF | tuple[float, float],
        *,
        tolerance_px: float = 13.0,
    ) -> tuple[ComponentItem, str, PointPx] | None:
        """Find the closest component terminal within `tolerance_px` of `scene_pos`."""
        sx = scene_pos.x() if isinstance(scene_pos, QPointF) else float(scene_pos[0])
        sy = scene_pos.y() if isinstance(scene_pos, QPointF) else float(scene_pos[1])
        best_dist = tolerance_px
        best_match: tuple[ComponentItem, str, PointPx] | None = None

        for item in self._placed_items:
            for tname, pt in item.terminal_scene_positions_px().items():
                dist = math.hypot(sx - pt[0], sy - pt[1])
                if dist <= best_dist:
                    best_dist = dist
                    best_match = (item, tname, pt)
        return best_match

    def find_wire_point_near(
        self,
        scene_pos: QPointF | tuple[float, float],
        *,
        tolerance_px: float = 10.0,
    ) -> PointPx | None:
        """Return the snapped grid point on an existing wire if within `tolerance_px`."""
        sx = scene_pos.x() if isinstance(scene_pos, QPointF) else float(scene_pos[0])
        sy = scene_pos.y() if isinstance(scene_pos, QPointF) else float(scene_pos[1])
        snapped = normalize_point_px((sx, sy), snap=True)
        if math.hypot(sx - snapped[0], sy - snapped[1]) > tolerance_px:
            return None
        for wire in self._wire_items:
            if point_on_wire(snapped, wire.points):
                return snapped
        return None

    def update_hover_highlight(self, scene_pos: QPointF) -> PointPx | None:
        """Update the highlighted terminal (or wire snap target) under `scene_pos`."""
        term_hit = self.find_terminal_near(scene_pos)
        new_hover: PointPx | None = None
        if term_hit is not None:
            new_hover = term_hit[2]
        elif self.is_drawing_wire:
            wire_hit = self.find_wire_point_near(scene_pos)
            if wire_hit is not None:
                new_hover = wire_hit

        if new_hover != self._hovered_terminal_pt:
            self._hovered_terminal_pt = new_hover
            self.update()
        return self._hovered_terminal_pt

    def start_wire_preview(
        self, start_pos: QPointF | tuple[float, float]
    ) -> PointPx:
        """Begin interactive right-angle wire drawing from `start_pos`."""
        term_hit = self.find_terminal_near(start_pos)
        if term_hit is not None:
            start_pt = term_hit[2]
        else:
            start_pt = normalize_point_px(
                (
                    start_pos.x()
                    if isinstance(start_pos, QPointF)
                    else float(start_pos[0]),
                    start_pos.y()
                    if isinstance(start_pos, QPointF)
                    else float(start_pos[1]),
                ),
                snap=True,
            )
        self._wire_start_pt = start_pt
        self._wire_prefer_horiz = True
        if self._preview_wire_item is None:
            self._preview_wire_item = WireItem(
                "PREVIEW_WIRE",
                (start_pt, start_pt),
                theme=self.theme,
                is_preview=True,
            )
            self.addItem(self._preview_wire_item)
        else:
            self._preview_wire_item.set_points((start_pt, start_pt))
        self.update()
        return start_pt

    def update_wire_preview(
        self, cursor_pos: QPointF | tuple[float, float]
    ) -> tuple[PointPx, ...]:
        """Update the live right-angle preview wire from `_wire_start_pt` to `cursor_pos`."""
        if self._wire_start_pt is None:
            return ()

        cx = cursor_pos.x() if isinstance(cursor_pos, QPointF) else float(cursor_pos[0])
        cy = cursor_pos.y() if isinstance(cursor_pos, QPointF) else float(cursor_pos[1])
        term_hit = self.find_terminal_near((cx, cy))
        end_pt = (
            term_hit[2]
            if term_hit is not None
            else normalize_point_px((cx, cy), snap=True)
        )

        # Infer initial horizontal/vertical preference when leaving the start point
        dx = abs(end_pt[0] - self._wire_start_pt[0])
        dy = abs(end_pt[1] - self._wire_start_pt[1])
        if dx == 0 and dy > 0:
            self._wire_prefer_horiz = False
        elif dy == 0 and dx > 0:
            self._wire_prefer_horiz = True

        pts = route_orthogonal_wire(
            self._wire_start_pt,
            end_pt,
            prefer_horizontal_first=self._wire_prefer_horiz,
        )
        if self._preview_wire_item is not None:
            self._preview_wire_item.set_points(pts)
        self.update_hover_highlight(QPointF(float(cx), float(cy)))
        self.update()
        return pts

    def finish_wire_preview(
        self, end_pos: QPointF | tuple[float, float]
    ) -> WireItem | None:
        """Commit the previewed wire onto the canvas via `QUndoStack` and clear preview."""
        if self._wire_start_pt is None:
            return None
        pts = self.update_wire_preview(end_pos)
        self.cancel_wire_preview()
        if len(pts) < 2:
            return None
        return self.add_wire(pts)

    def cancel_wire_preview(self) -> None:
        """Cancel any active wire preview without creating a wire."""
        self._wire_start_pt = None
        if self._preview_wire_item is not None:
            self.removeItem(self._preview_wire_item)
            self._preview_wire_item = None
        self.update()

    def add_wire(
        self,
        points: Sequence[tuple[float, float] | PointPx],
    ) -> WireItem | None:
        """Add an orthogonal wire polyline via `QUndoStack` (ignoring zero-length/duplicate)."""
        pts = simplify_orthogonal_points(points, snap=True)
        if len(pts) < 2:
            return None

        # Rule 3: Ignore exact duplicate wire polylines (forward or reversed)
        rev_pts = tuple(reversed(pts))
        for existing in self._wire_items:
            if existing.points == pts or existing.points == rev_pts:
                return existing

        wire = WireItem(self.next_wire_id(), pts, theme=self.theme)
        self.undo_stack.push(AddWireCommand(self, wire))
        return wire

    def add_routed_wire(
        self,
        start_px: tuple[float, float] | PointPx,
        end_px: tuple[float, float] | PointPx,
        *,
        prefer_horizontal_first: bool = True,
    ) -> WireItem | None:
        """Route a right-angle wire between `start_px` and `end_px` and add it via `QUndoStack`."""
        pts = route_orthogonal_wire(
            start_px,
            end_px,
            prefer_horizontal_first=prefer_horizontal_first,
        )
        return self.add_wire(pts)

    def toggle_junction_at(
        self, pos: QPointF | tuple[float, float] | PointPx
    ) -> bool:
        """Toggle an explicit junction dot at the snapped grid position via `QUndoStack`."""
        raw = (
            (pos.x(), pos.y())
            if isinstance(pos, QPointF)
            else (float(pos[0]), float(pos[1]))
        )
        pt = normalize_point_px(raw, snap=True)
        adding = pt not in self._explicit_junctions
        self.undo_stack.push(ToggleJunctionCommand(self, pt, adding=adding))
        return adding

    # ------------------------------------------------------------------
    # Component Move Tracking, Rotate, Flip, Delete, Copy/Cut/Paste
    # ------------------------------------------------------------------

    def begin_component_move_tracking(self) -> None:
        """Snapshot component positions, terminal positions, and wire polylines before drag."""
        self._move_tracking_active = True
        self._move_start_positions = {
            item: (item.pos().x(), item.pos().y())
            for item in self._placed_items
        }
        self._move_start_terminals = self.all_component_terminals_px()
        self._move_start_wires = {
            wire: wire.points for wire in self._wire_items
        }

    def on_component_position_changed(self, item: ComponentItem) -> None:
        """Re-route wires attached to moved components in real time during mouse drag."""
        _ = item
        if self._suppress_live_reroute or not self._move_tracking_active:
            return
        new_terminals = self.all_component_terminals_px()
        wire_specs = [
            WireSpec(wire_id=w.wire_id, points=pts)
            for w, pts in self._move_start_wires.items()
        ]
        updated_map = reroute_wires_for_updated_terminals(
            self._move_start_terminals, new_terminals, wire_specs
        )
        for wire in self._wire_items:
            if wire.wire_id in updated_map:
                new_pts = updated_map[wire.wire_id]
                if len(new_pts) >= 2:
                    wire.set_points(new_pts)
            elif wire in self._move_start_wires:
                wire.set_points(self._move_start_wires[wire])
        self.refresh_connectivity_visuals()

    def commit_component_move_tracking(self) -> bool:
        """Finalize a mouse drag-move and push `MoveComponentsCommand` if anything moved."""
        if not self._move_tracking_active:
            return False
        self._move_tracking_active = False

        moved_old: dict[ComponentItem, tuple[float, float]] = {}
        moved_new: dict[ComponentItem, tuple[float, float]] = {}
        for item, old_pos in self._move_start_positions.items():
            cur_pos = (item.pos().x(), item.pos().y())
            if cur_pos != old_pos:
                moved_old[item] = old_pos
                moved_new[item] = cur_pos

        if not moved_new:
            return False

        old_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        new_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        for wire, old_pts in self._move_start_wires.items():
            if wire.points != old_pts:
                old_wires[wire] = old_pts
                new_wires[wire] = wire.points

        self.undo_stack.push(
            MoveComponentsCommand(
                self, moved_old, moved_new, old_wires, new_wires
            )
        )
        return True

    def move_components_by(
        self,
        items: Sequence[ComponentItem],
        dx_px: float,
        dy_px: float,
    ) -> bool:
        """Programmatically move `items` by `(dx_px, dy_px)` and re-route attached wires via `QUndoStack`."""
        target_items = [it for it in items if it in self._placed_items]
        if not target_items:
            return False

        old_terminals = self.all_component_terminals_px()
        old_wire_map = {w: w.points for w in self._wire_items}
        old_positions: dict[ComponentItem, tuple[float, float]] = {}
        new_positions: dict[ComponentItem, tuple[float, float]] = {}

        self._suppress_live_reroute = True
        try:
            for item in target_items:
                ox, oy = item.pos().x(), item.pos().y()
                nx, ny = snap_to_grid(ox + dx_px, oy + dy_px, GRID_PITCH_PX)
                if (nx, ny) != (ox, oy):
                    old_positions[item] = (ox, oy)
                    new_positions[item] = (nx, ny)
                    item.setPos(QPointF(nx, ny))
        finally:
            self._suppress_live_reroute = False

        if not new_positions:
            return False

        new_terminals = self.all_component_terminals_px()
        wire_specs = [
            WireSpec(wire_id=w.wire_id, points=pts)
            for w, pts in old_wire_map.items()
        ]
        updated_map = reroute_wires_for_updated_terminals(
            old_terminals, new_terminals, wire_specs
        )
        old_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        new_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        for w in self._wire_items:
            if w.wire_id in updated_map and len(updated_map[w.wire_id]) >= 2:
                old_wires[w] = old_wire_map[w]
                new_wires[w] = updated_map[w.wire_id]

        self.undo_stack.push(
            MoveComponentsCommand(
                self, old_positions, new_positions, old_wires, new_wires
            )
        )
        return True

    def rotate_selected(self) -> bool:
        """Rotate selected `ComponentItem`s by 90° CW and re-route attached wires via `QUndoStack`."""
        selected = [
            it for it in self.selectedItems() if isinstance(it, ComponentItem)
        ]
        if not selected:
            return False

        old_terminals = self.all_component_terminals_px()
        old_wire_map = {w: w.points for w in self._wire_items}
        old_rotations = {it: it.rotation_deg for it in selected}
        new_rotations = {it: (it.rotation_deg + 90) % 360 for it in selected}

        for it, deg in new_rotations.items():
            it.set_rotation_deg(deg)

        new_terminals = self.all_component_terminals_px()
        wire_specs = [
            WireSpec(wire_id=w.wire_id, points=pts)
            for w, pts in old_wire_map.items()
        ]
        updated_map = reroute_wires_for_updated_terminals(
            old_terminals, new_terminals, wire_specs
        )
        old_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        new_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        for w in self._wire_items:
            if w.wire_id in updated_map and len(updated_map[w.wire_id]) >= 2:
                old_wires[w] = old_wire_map[w]
                new_wires[w] = updated_map[w.wire_id]

        self.undo_stack.push(
            RotateComponentsCommand(
                self, selected, old_rotations, new_rotations, old_wires, new_wires
            )
        )
        return True

    def flip_selected(self) -> bool:
        """Flip selected `ComponentItem`s horizontally and re-route attached wires via `QUndoStack`."""
        selected = [
            it for it in self.selectedItems() if isinstance(it, ComponentItem)
        ]
        if not selected:
            return False

        old_terminals = self.all_component_terminals_px()
        old_wire_map = {w: w.points for w in self._wire_items}
        old_flips = {it: it.flipped_h for it in selected}
        new_flips = {it: not it.flipped_h for it in selected}

        for it, flipped in new_flips.items():
            it.set_flipped_h(flipped)

        new_terminals = self.all_component_terminals_px()
        wire_specs = [
            WireSpec(wire_id=w.wire_id, points=pts)
            for w, pts in old_wire_map.items()
        ]
        updated_map = reroute_wires_for_updated_terminals(
            old_terminals, new_terminals, wire_specs
        )
        old_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        new_wires: dict[WireItem, tuple[PointPx, ...]] = {}
        for w in self._wire_items:
            if w.wire_id in updated_map and len(updated_map[w.wire_id]) >= 2:
                old_wires[w] = old_wire_map[w]
                new_wires[w] = updated_map[w.wire_id]

        self.undo_stack.push(
            FlipComponentsCommand(
                self, selected, old_flips, new_flips, old_wires, new_wires
            )
        )
        return True

    def delete_selected(self, *, description: str = "Delete Selection") -> bool:
        """Delete selected components and wires (plus all wires attached to deleted components)."""
        selected_comps = [
            it for it in self.selectedItems() if isinstance(it, ComponentItem)
        ]
        selected_wires = [
            it for it in self.selectedItems() if isinstance(it, WireItem)
        ]
        if not selected_comps and not selected_wires:
            return False

        # Rule 2: Deleting a component also deletes all wires attached to its terminals
        comp_terminals = self.all_component_terminals_px()
        deleted_names = {it.component.name for it in selected_comps}
        attached_wire_ids = set(
            find_wires_attached_to_components(
                comp_terminals,
                deleted_names,
                [w.to_wire_spec() for w in self._wire_items],
            )
        )
        wires_to_delete: list[WireItem] = []
        seen_wires: set[str] = set()
        for w in self._wire_items:
            if w in selected_wires or w.wire_id in attached_wire_ids:
                if w.wire_id not in seen_wires:
                    wires_to_delete.append(w)
                    seen_wires.add(w.wire_id)

        self.undo_stack.push(
            DeleteItemsCommand(
                self,
                selected_comps,
                wires_to_delete,
                description=description,
            )
        )
        return True

    def copy_selected(self) -> bool:
        """Copy selected components and wires to the internal clipboard."""
        selected_comps = [
            it for it in self.selectedItems() if isinstance(it, ComponentItem)
        ]
        selected_wires = [
            it for it in self.selectedItems() if isinstance(it, WireItem)
        ]
        if not selected_comps and not selected_wires:
            return False

        # Also include wires whose both endpoints sit on terminals of selected_comps
        selected_term_pts: set[PointPx] = set()
        for comp in selected_comps:
            selected_term_pts.update(comp.terminal_scene_positions_px().values())

        wires_to_copy: list[tuple[PointPx, ...]] = []
        seen_ids: set[str] = set()
        for w in self._wire_items:
            pts = w.points
            both_on_selected = (
                len(pts) >= 2
                and pts[0] in selected_term_pts
                and pts[-1] in selected_term_pts
            )
            if w in selected_wires or both_on_selected:
                if w.wire_id not in seen_ids:
                    wires_to_copy.append(pts)
                    seen_ids.add(w.wire_id)

        comp_entries = tuple(
            _ClipboardComponentEntry(
                component_snapshot=copy.deepcopy(it.component),
                pos_px=(it.pos().x(), it.pos().y()),
                rotation_deg=it.rotation_deg,
                flipped_h=it.flipped_h,
            )
            for it in selected_comps
        )
        self._clipboard = _ClipboardData(
            components=comp_entries,
            wires=tuple(wires_to_copy),
            junctions=(),
        )
        self._paste_serial = 0
        return True

    def cut_selected(self) -> bool:
        """Copy selected items to clipboard and delete them via `QUndoStack`."""
        if not self.copy_selected():
            return False
        return self.delete_selected(description="Cut Selection")

    def paste_clipboard(
        self, offset_px: tuple[float, float] | None = None
    ) -> bool:
        """Paste clipboard contents onto the canvas with a grid-aligned offset via `QUndoStack`."""
        if self._clipboard is None:
            return False

        self._paste_serial += 1
        if offset_px is None:
            step = float(GRID_PITCH_PX * 2 * self._paste_serial)
            dx, dy = step, step
        else:
            dx, dy = snap_to_grid(offset_px[0], offset_px[1], GRID_PITCH_PX)

        new_comps: list[ComponentItem] = []
        for entry in self._clipboard.components:
            cloned = copy.deepcopy(entry.component_snapshot)
            new_name = self.next_component_name(cloned.component_type)
            cloned.name = new_name
            cloned.label = new_name
            item = ComponentItem(
                cloned,
                self.symbol_library,
                theme=self.theme,
                is_ghost=False,
            )
            nx, ny = snap_to_grid(
                entry.pos_px[0] + dx, entry.pos_px[1] + dy, GRID_PITCH_PX
            )
            item.setPos(QPointF(nx, ny))
            item.set_rotation_deg(entry.rotation_deg)
            item.set_flipped_h(entry.flipped_h)
            new_comps.append(item)

        new_wires: list[WireItem] = []
        id_x = int(round(dx))
        id_y = int(round(dy))
        for pts in self._clipboard.wires:
            shifted_pts = tuple((px + id_x, py + id_y) for px, py in pts)
            new_wires.append(
                WireItem(self.next_wire_id(), shifted_pts, theme=self.theme)
            )

        self.undo_stack.push(
            PasteItemsCommand(self, new_comps, new_wires)
        )
        return True

    # ------------------------------------------------------------------
    # Netlist Extraction (CircuitScene.build_circuit)
    # ------------------------------------------------------------------

    def extract_connectivity_result(self) -> ConnectivityResult:
        """Run the pure-Python Union-Find connectivity extractor on the current scene."""
        placed_specs = [item.to_placed_spec() for item in self._placed_items]
        wire_specs = [wire.to_wire_spec() for wire in self._wire_items]
        return extract_connectivity(
            placed_specs,
            wire_specs,
            self._explicit_junctions,
            symbol_catalog=self.symbol_library.metadata_catalog,
        )

    def build_circuit(self) -> Circuit:
        """Build and return a solver-ready `Circuit` from the schematic's components and wires."""
        return self.extract_connectivity_result().circuit

    def toggle_switch_item(self, item: ComponentItem) -> bool:
        """Toggle a `Switch` `ComponentItem` with lever animation and notify listeners."""
        if not isinstance(item.component, Switch):
            return False
        new_closed = not item.component.closed
        item.animate_switch_state(new_closed)
        self.switch_toggled_by_user.emit(item.component.name, new_closed)
        self.selection_info_changed.emit(item if item.isSelected() else None)
        return new_closed

    def edit_component_parameters(
        self,
        item: ComponentItem,
        new_params: dict[str, float | str],
        *,
        show_value: bool | None = None,
    ) -> bool:
        """Apply parameter changes to `item` via `QUndoStack` (`EditComponentParametersCommand`)."""
        comp = item.component
        old_params: dict[str, float] = {}
        parsed_new: dict[str, float] = {}
        for k, raw_val in new_params.items():
            old_params[k] = comp.get_parameter_value(k)
            parsed_new[k] = comp.set_parameter_value(k, raw_val)
            # Restore old value before pushing undo command so redo() performs the transition cleanly
            comp.set_parameter_value(k, old_params[k])

        old_show = comp.show_value
        new_show = old_show if show_value is None else bool(show_value)
        if old_params == parsed_new and old_show == new_show:
            return False

        self.undo_stack.push(
            EditComponentParametersCommand(
                self,
                item,
                old_params,
                parsed_new,
                old_show_value=old_show,
                new_show_value=new_show,
            )
        )
        return True

    def clear_diagnostics(self) -> None:
        """Clear all problem highlighting on components and wires."""
        for item in self._placed_items:
            item.set_diagnostic(None, "")
        for wire in self._wire_items:
            wire.set_diagnostic(None, "")

    def apply_simulation_frame(self, frame: SimulationFrame) -> None:
        """Apply telemetry and problem diagnostics from a `SimulationFrame` to canvas items."""
        if frame.state in (SimulationState.STOPPED, SimulationState.ERROR):
            for item in self._placed_items:
                item.reset_live_telemetry()
        else:
            for item in self._placed_items:
                telem = frame.components.get(item.component.name)
                if telem is not None:
                    item.apply_telemetry(telem)

        # Map diagnostics to components and wires (error takes precedence over warning)
        comp_diag: dict[str, tuple[str, str]] = {}
        wire_diag: dict[str, tuple[str, str]] = {}
        for diag in frame.diagnostics:
            for cname in diag.component_names:
                prev = comp_diag.get(cname)
                if prev is None or prev[0] != "error":
                    comp_diag[cname] = (diag.severity, diag.message)
            for wid in diag.wire_ids:
                prev_w = wire_diag.get(wid)
                if prev_w is None or prev_w[0] != "error":
                    wire_diag[wid] = (diag.severity, diag.message)

        for item in self._placed_items:
            d = comp_diag.get(item.component.name)
            if d is not None:
                item.set_diagnostic(d[0], d[1])
            else:
                item.set_diagnostic(None, "")

        for wire in self._wire_items:
            dw = wire_diag.get(wire.wire_id)
            if dw is not None:
                wire.set_diagnostic(dw[0], dw[1])
            else:
                wire.set_diagnostic(None, "")

        selected = [
            it for it in self.selectedItems() if isinstance(it, ComponentItem)
        ]
        if selected:
            self.selection_info_changed.emit(selected[0])

    def clear_schematic(self) -> None:
        """Remove all placed components, wires, junctions, and clear the undo stack."""
        self.hide_ghost_preview()
        self.cancel_wire_preview()
        for wire in list(self._wire_items):
            self.removeItem(wire)
        for item in list(self._placed_items):
            self.removeItem(item)
        self._wire_items.clear()
        self._placed_items.clear()
        self._explicit_junctions.clear()
        self._active_junction_dots.clear()
        self._counters.clear()
        self._wire_counter = 0
        self.undo_stack.clear()
        self.selection_info_changed.emit(None)
        self.circuit_modified.emit()
        self.update()

    def _on_selection_changed(self) -> None:
        selected = [
            it for it in self.selectedItems() if isinstance(it, ComponentItem)
        ]
        self.selection_info_changed.emit(selected[0] if selected else None)

    # ------------------------------------------------------------------
    # Background Grid & Foreground Junction / Terminal Highlight Drawing
    # ------------------------------------------------------------------

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

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw filled junction dots (T-junctions + explicit junctions) and terminal hover rings."""
        _ = rect
        palette = get_theme_palette(self.theme)
        painter.save()

        # 1. Draw all active junction dots (T-junctions + explicit junctions on wires)
        junc_color = QColor(palette.symbol_stroke)
        painter.setPen(QPen(junc_color, 1.2))
        painter.setBrush(QBrush(junc_color))
        for jx, jy in self._active_junction_dots:
            painter.drawEllipse(QPointF(float(jx), float(jy)), 4.2, 4.2)

        # 2. Draw glowing highlight ring around hovered terminal or wire snap target
        if self._hovered_terminal_pt is not None:
            hx, hy = self._hovered_terminal_pt
            hover_col = QColor(palette.terminal_hover)
            fill_col = QColor(palette.terminal_hover)
            fill_col.setAlpha(65)
            painter.setPen(QPen(hover_col, 2.0))
            painter.setBrush(QBrush(fill_col))
            painter.drawEllipse(QPointF(float(hx), float(hy)), 7.0, 7.0)

        painter.restore()
