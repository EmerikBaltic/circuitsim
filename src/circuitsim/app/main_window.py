"""Main application window implementing the dockable layout from Section 2."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from circuitsim.app.palette_dock import ComponentPaletteWidget
from circuitsim.app.themes import ThemeMode, build_stylesheet, get_theme_palette
from circuitsim.canvas.component_item import (
    ComponentItem,
    format_component_value_summary,
)
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.view import CircuitView

DEFAULT_SHORTCUTS_HELP_TEXT: str = (
    "No component selected.\n\n"
    "KEYBOARD & MOUSE SHORTCUTS:\n"
    "• Place part: Drag from Palette (or double-click)\n"
    "• Draw wire: Drag from any terminal (or press W)\n"
    "• Cancel wire / Deselect: Esc (or Right-click)\n"
    "• Toggle junction dot: J (at cursor) or Right-click\n"
    "• Rotate 90° CW: R\n"
    "• Flip horizontal: F\n"
    "• Delete selection: Del or Backspace\n"
    "• Cut / Copy / Paste: Ctrl+X / Ctrl+C / Ctrl+V\n"
    "• Undo / Redo: Ctrl+Z / Ctrl+Y\n"
    "• Box select: Left-drag on empty canvas\n"
    "• Zoom: Mouse wheel (Ctrl++ / Ctrl+-)\n"
    "• Pan canvas: Middle-drag or Space + Left-drag\n"
    "• Toggle Dark/Light theme: Ctrl+T"
)


class MainWindow(QMainWindow):
    """Dockable main window for CircuitSim (Section 2 of specification)."""

    def __init__(self, *, initial_theme: ThemeMode = ThemeMode.DARK) -> None:
        super().__init__()
        self.setWindowTitle("CircuitSim — Electrical Circuit Simulator")
        self.resize(1360, 840)

        self.theme: ThemeMode = initial_theme
        self.symbol_library = SymbolLibrary()
        self.circuit_scene = CircuitScene(self.symbol_library, theme=self.theme)
        self.circuit_view = CircuitView(self.circuit_scene)
        self.setCentralWidget(self.circuit_view)

        self._build_menus_and_toolbars()
        self._build_saved_parts_bar()
        self._build_docks()
        self._build_status_bar()
        self._connect_signals()
        self.apply_theme(self.theme)

    def _build_menus_and_toolbars(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")
        self.act_new = QAction("&New Circuit", self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self.circuit_scene.clear_schematic)
        file_menu.addAction(self.act_new)

        self.act_open = QAction("&Open...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        file_menu.addAction(self.act_open)

        self.act_save = QAction("&Save...", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        file_menu.addAction(self.act_save)

        file_menu.addSeparator()
        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Edit menu (backed by QUndoStack)
        edit_menu = menu_bar.addMenu("&Edit")
        self.act_undo = self.circuit_scene.undo_stack.createUndoAction(
            self, "&Undo"
        )
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_redo = self.circuit_scene.undo_stack.createRedoAction(
            self, "&Redo"
        )
        self.act_redo.setShortcuts(
            [QKeySequence.StandardKey.Redo, QKeySequence("Ctrl+Y")]
        )
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()

        self.act_cut = QAction("Cu&t", self)
        self.act_cut.setShortcut(QKeySequence.StandardKey.Cut)
        self.act_cut.triggered.connect(self.circuit_scene.cut_selected)
        edit_menu.addAction(self.act_cut)

        self.act_copy = QAction("&Copy", self)
        self.act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.act_copy.triggered.connect(self.circuit_scene.copy_selected)
        edit_menu.addAction(self.act_copy)

        self.act_paste = QAction("&Paste", self)
        self.act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.act_paste.triggered.connect(self.circuit_scene.paste_clipboard)
        edit_menu.addAction(self.act_paste)

        self.act_delete = QAction("&Delete", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.triggered.connect(self.circuit_scene.delete_selected)
        edit_menu.addAction(self.act_delete)

        edit_menu.addSeparator()
        self.act_rotate = QAction("&Rotate (R)", self)
        self.act_rotate.setToolTip("Rotate selected component(s) 90° clockwise (Shortcut: R)")
        self.act_rotate.triggered.connect(self._rotate_selected)
        edit_menu.addAction(self.act_rotate)

        self.act_flip = QAction("&Flip (F)", self)
        self.act_flip.setToolTip("Flip selected component(s) horizontally (Shortcut: F)")
        self.act_flip.triggered.connect(self._flip_selected)
        edit_menu.addAction(self.act_flip)

        self.act_wire_mode = QAction("&Wire Tool (W)", self, checkable=True)
        self.act_wire_mode.setToolTip(
            "Toggle Wire Drawing mode (Shortcut: W). You can also drag directly from any terminal."
        )
        self.act_wire_mode.toggled.connect(self.circuit_view.set_wire_mode)
        edit_menu.addAction(self.act_wire_mode)

        self.act_junction = QAction("Toggle &Junction Dot (J)", self)
        self.act_junction.setToolTip(
            "Place or remove an explicit junction dot at the cursor (Shortcut: J)"
        )
        self.act_junction.triggered.connect(
            lambda: self.circuit_scene.toggle_junction_at(
                self.circuit_view._last_scene_pos
            )
        )
        edit_menu.addAction(self.act_junction)

        # View menu
        view_menu = menu_bar.addMenu("&View")
        self.act_toggle_grid = QAction("Show &Grid (20 px)", self, checkable=True)
        self.act_toggle_grid.setChecked(True)
        self.act_toggle_grid.toggled.connect(self.circuit_scene.set_show_grid)
        view_menu.addAction(self.act_toggle_grid)

        self.act_toggle_theme = QAction("Switch to &Light Theme", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+T"))
        self.act_toggle_theme.triggered.connect(self.toggle_theme)
        view_menu.addAction(self.act_toggle_theme)

        view_menu.addSeparator()
        act_zoom_in = QAction("Zoom &In", self)
        act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        act_zoom_in.triggered.connect(self.circuit_view.zoom_in)
        view_menu.addAction(act_zoom_in)

        act_zoom_out = QAction("Zoom &Out", self)
        act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        act_zoom_out.triggered.connect(self.circuit_view.zoom_out)
        view_menu.addAction(act_zoom_out)

        act_zoom_reset = QAction("&Reset Zoom (100%)", self)
        act_zoom_reset.triggered.connect(self.circuit_view.reset_zoom)
        view_menu.addAction(act_zoom_reset)

        # Simulation menu
        sim_menu = menu_bar.addMenu("&Simulation")
        self.act_run = QAction("&Run", self)
        self.act_pause = QAction("&Pause", self)
        self.act_stop = QAction("&Stop", self)
        sim_menu.addAction(self.act_run)
        sim_menu.addAction(self.act_pause)
        sim_menu.addAction(self.act_stop)

        # Instruments & Help menus
        self.instruments_menu = menu_bar.addMenu("&Instruments")
        help_menu = menu_bar.addMenu("&Help")
        act_reload_svg = QAction("&Reload Custom SVGs", self)
        act_reload_svg.triggered.connect(self._reload_custom_svgs)
        help_menu.addAction(act_reload_svg)

        # Main Toolbar (with Undo/Redo, Rotate (R), Flip (F), Delete, Run/Pause/Stop)
        main_tb = QToolBar("Main Toolbar", self)
        main_tb.setMovable(False)
        main_tb.addAction(self.act_new)
        main_tb.addAction(self.act_open)
        main_tb.addAction(self.act_save)
        main_tb.addSeparator()
        main_tb.addAction(self.act_undo)
        main_tb.addAction(self.act_redo)
        main_tb.addSeparator()
        main_tb.addAction(self.act_rotate)
        main_tb.addAction(self.act_flip)
        main_tb.addAction(self.act_wire_mode)
        main_tb.addAction(self.act_junction)
        main_tb.addAction(self.act_delete)
        main_tb.addSeparator()
        main_tb.addAction(self.act_run)
        main_tb.addAction(self.act_pause)
        main_tb.addAction(self.act_stop)
        main_tb.addSeparator()

        main_tb.addWidget(QLabel("  Speed: "))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["Real-Time (1x)", "Slow Motion (0.1x)", "Fast (Max)"])
        main_tb.addWidget(self.speed_combo)
        main_tb.addSeparator()
        main_tb.addAction(self.act_toggle_theme)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, main_tb)

    def _build_saved_parts_bar(self) -> None:
        """Create the 10-slot Saved Parts bar at the top (full persistence in Milestone 3)."""
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        saved_tb = QToolBar("Saved Parts Bar", self)
        saved_tb.setMovable(False)
        saved_tb.addWidget(QLabel(" SAVED PARTS: "))
        self.saved_slot_buttons: list[QPushButton] = []
        for slot_idx in range(1, 11):
            key_label = "0" if slot_idx == 10 else str(slot_idx)
            btn = QPushButton(f"[{slot_idx}] Empty")
            btn.setToolTip(
                f"Saved Part Slot {slot_idx} (Shortcut key '{key_label}')\n"
                "Full save/load configuration will be activated in Milestone 3."
            )
            btn.setMinimumWidth(92)
            saved_tb.addWidget(btn)
            self.saved_slot_buttons.append(btn)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, saved_tb)

    def _build_docks(self) -> None:
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )

        # 1. Left Dock: Component Palette
        self.palette_dock = QDockWidget("Component Palette", self)
        self.palette_widget = ComponentPaletteWidget(
            self.symbol_library, theme=self.theme, parent=self.palette_dock
        )
        self.palette_dock.setWidget(self.palette_widget)
        self.palette_dock.setMinimumWidth(240)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.palette_dock)

        # 2. Right Dock: Properties / Info Panel
        self.info_dock = QDockWidget("Properties / Info Panel", self)
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(10, 10, 10, 10)
        self.info_label = QLabel(DEFAULT_SHORTCUTS_HELP_TEXT)
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.info_label)
        self.info_dock.setWidget(info_container)
        self.info_dock.setMinimumWidth(275)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.info_dock)

        # 3. Bottom Dock: Oscilloscope Panel Placeholder
        self.scope_dock = QDockWidget("Oscilloscope (4-Channel)", self)
        scope_container = QWidget()
        scope_layout = QHBoxLayout(scope_container)
        scope_label = QLabel(
            "4-Channel Oscilloscope Dock (Detachable / Multi-Monitor Ready — Milestone 4)"
        )
        scope_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scope_layout.addWidget(scope_label)
        scope_container.setMinimumHeight(90)
        self.scope_dock.setWidget(scope_container)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.scope_dock)

        self.instruments_menu.addAction(self.scope_dock.toggleViewAction())
        self.instruments_menu.addAction(self.palette_dock.toggleViewAction())
        self.instruments_menu.addAction(self.info_dock.toggleViewAction())

    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        self.status_coords = QLabel("Grid: (0, 0) | Pos: (0, 0) px")
        self.status_zoom = QLabel("Zoom: 100%")
        self.status_counts = QLabel("Components: 0 | Wires: 0")
        self.status_warnings = QLabel("Ready")

        sb.addWidget(self.status_coords)
        sb.addPermanentWidget(self.status_counts)
        sb.addPermanentWidget(self.status_zoom)
        sb.addPermanentWidget(self.status_warnings)

    def _connect_signals(self) -> None:
        self.palette_widget.component_activated.connect(
            self._place_component_at_view_center
        )
        self.circuit_view.cursor_grid_moved.connect(self._on_cursor_moved)
        self.circuit_view.zoom_changed.connect(self._on_zoom_changed)
        self.circuit_scene.component_placed.connect(self._on_component_placed)
        self.circuit_scene.selection_info_changed.connect(self._update_info_panel)
        self.circuit_scene.circuit_modified.connect(self._on_circuit_modified)

    def apply_theme(self, theme: ThemeMode) -> None:
        """Apply `theme` ('dark' or 'light') across window, palette, and canvas."""
        self.theme = theme
        palette = get_theme_palette(theme)
        self.setStyleSheet(build_stylesheet(palette))
        self.circuit_scene.set_theme(theme)
        self.palette_widget.set_theme(theme)

        if theme == ThemeMode.DARK:
            self.act_toggle_theme.setText("Switch to &Light Theme")
        else:
            self.act_toggle_theme.setText("Switch to &Dark Theme")

        self._refresh_warnings_display()

    def toggle_theme(self) -> None:
        """Toggle between Dark and Light themes."""
        next_theme = (
            ThemeMode.LIGHT if self.theme == ThemeMode.DARK else ThemeMode.DARK
        )
        self.apply_theme(next_theme)

    def _reload_custom_svgs(self) -> None:
        self.symbol_library.clear_cache()
        self.apply_theme(self.theme)

    def _place_component_at_view_center(self, component_id: str) -> None:
        center_pt = self.circuit_view.mapToScene(
            self.circuit_view.viewport().rect().center()
        )
        self.circuit_scene.place_new_component(component_id, QPointF(center_pt))

    def _rotate_selected(self) -> None:
        if self.circuit_scene.rotate_selected():
            selected = [
                it
                for it in self.circuit_scene.selectedItems()
                if isinstance(it, ComponentItem)
            ]
            self._update_info_panel(selected[0] if selected else None)

    def _flip_selected(self) -> None:
        if self.circuit_scene.flip_selected():
            selected = [
                it
                for it in self.circuit_scene.selectedItems()
                if isinstance(it, ComponentItem)
            ]
            self._update_info_panel(selected[0] if selected else None)

    def _on_cursor_moved(self, x_px: float, y_px: float, gx: int, gy: int) -> None:
        self.status_coords.setText(
            f"Grid: ({gx}, {gy}) | Pos: ({int(x_px)}, {int(y_px)}) px"
        )

    def _on_zoom_changed(self, zoom: float) -> None:
        self.status_zoom.setText(f"Zoom: {int(round(zoom * 100.0))}%")

    def _on_component_placed(self, item: ComponentItem) -> None:
        self._update_status_counts()
        self._update_info_panel(item)
        self._refresh_warnings_display()

    def _on_circuit_modified(self) -> None:
        self._update_status_counts()
        selected = [
            it
            for it in self.circuit_scene.selectedItems()
            if isinstance(it, ComponentItem)
        ]
        self._update_info_panel(selected[0] if selected else None)

    def _update_status_counts(self) -> None:
        n_comp = len(self.circuit_scene.placed_items)
        n_wire = len(self.circuit_scene.placed_wires)
        self.status_counts.setText(f"Components: {n_comp} | Wires: {n_wire}")

    def _refresh_warnings_display(self) -> None:
        if self.symbol_library.warnings:
            latest = self.symbol_library.warnings[-1]
            self.status_warnings.setText(f"SVG Warning: {latest}")
        else:
            self.status_warnings.setText("Ready (IEC Symbols)")

    def _update_info_panel(self, item: ComponentItem | None) -> None:
        self._update_status_counts()
        if item is None:
            self.info_label.setText(DEFAULT_SHORTCUTS_HELP_TEXT)
            return

        comp = item.component
        meta = item.metadata
        val_str = format_component_value_summary(comp) or "—"
        terms = item.terminal_scene_positions()
        conn_res = self.circuit_scene.extract_connectivity_result()
        node_map = conn_res.component_nodes.get(comp.name, {})
        term_lines = "\n".join(
            f"  • {t_name}: ({int(pos[0])}, {int(pos[1])}) px  →  Node {node_map.get(t_name, '?')}"
            for t_name, pos in terms.items()
        )
        svg_path = meta.svg_path_for_state(item.symbol_state)
        source_kind = (
            f"Custom SVG ({svg_path.name})"
            if svg_path.exists()
            else "Procedural IEC Fallback"
        )

        self.info_label.setText(
            f"Name: {comp.name}\n"
            f"Type: {meta.display_name} ({comp.component_type})\n"
            f"Category: {meta.category}\n"
            f"Value: {val_str}\n"
            f"Position: ({int(item.pos().x())}, {int(item.pos().y())}) px\n"
            f"Rotation: {item.rotation_deg}° | Flipped: {item.flipped_h}\n"
            f"Footprint: {meta.grid_size[0]}x{meta.grid_size[1]} grid ({meta.pixel_size[0]}x{meta.pixel_size[1]} px)\n"
            f"Symbol Source: {source_kind}\n\n"
            f"Terminals & Nets:\n{term_lines}"
        )
