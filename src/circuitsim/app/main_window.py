"""Main application window implementing the dockable layout, live simulation worker, and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from circuitsim.app.crash_handler import (
    ISSUES_URL,
    REPO_URL,
    get_app_version,
)
from circuitsim.app.palette_dock import ComponentPaletteWidget
from circuitsim.app.problems_panel import ProblemsDock
from circuitsim.app.settings import AppSettings
from circuitsim.app.sim_worker import SimulationWorkerController
from circuitsim.app.themes import ThemeMode, build_stylesheet, get_theme_palette
from circuitsim.canvas.component_item import (
    ComponentItem,
    format_component_value_summary,
)
from circuitsim.canvas.export import (
    ExportOptionsDialog,
    export_schematic_to_image,
    export_schematic_to_svg,
)
from circuitsim.canvas.scene import CircuitScene
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.view import CircuitView
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.dialogs.preferences_dialog import PreferencesDialog
from circuitsim.dialogs.value_parser import (
    format_engineering_value,
    set_global_number_format,
)
from circuitsim.io.circ_serializer import (
    CircuitFileError,
    ViewState,
    load_document,
    save_document,
)
from circuitsim.engine.simulation_session import (
    SimulationFrame,
    SimulationSpeed,
    SimulationState,
    TransportControlsViewState,
    compute_transport_controls_state,
)

DEFAULT_SHORTCUTS_HELP_TEXT: str = (
    "No component selected.\n\n"
    "KEYBOARD & MOUSE SHORTCUTS:\n"
    "• Place part: Drag from Palette (or double-click)\n"
    "• Edit values live: Double-click any component\n"
    "• Toggle switch: Click switch on canvas\n"
    "• Draw wire: Drag from any terminal (or press W)\n"
    "• Cancel wire / Deselect: Esc (or Right-click)\n"
    "• Toggle junction dot: J (at cursor) or Right-click\n"
    "• Rotate 90° CW: R\n"
    "• Flip horizontal: F\n"
    "• Delete selection: Del or Backspace\n"
    "• Cut / Copy / Paste: Ctrl+X / Ctrl+C / Ctrl+V\n"
    "• Undo / Redo: Ctrl+Z / Ctrl+Y\n"
    "• Run / Resume: F5\n"
    "• Pause: F6\n"
    "• Stop: Shift+F5\n"
    "• Zoom to fit: Ctrl+0\n"
    "• Zoom: Mouse wheel (Ctrl++ / Ctrl+-)\n"
    "• Pan canvas: Middle-drag or Space + Left-drag\n"
    "• Toggle Dark/Light theme: Ctrl+T"
)


class MainWindow(QMainWindow):
    """Dockable main window for CircuitSim (Section 2 of specification)."""

    def __init__(
        self,
        *,
        initial_theme: ThemeMode = ThemeMode.DARK,
        settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("CircuitSim — Electrical Circuit Simulator")
        self.resize(1360, 840)

        self.settings: AppSettings = (
            settings if settings is not None else AppSettings()
        )
        set_global_number_format(self.settings.get_number_format())
        self.theme: ThemeMode = initial_theme
        self.symbol_library = SymbolLibrary()
        self.circuit_scene = CircuitScene(self.symbol_library, theme=self.theme)
        self.circuit_view = CircuitView(self.circuit_scene)
        self.setCentralWidget(self.circuit_view)

        self.sim_controller = SimulationWorkerController(self)
        self._sim_state: SimulationState = SimulationState.STOPPED
        self._last_error_reason: str = ""
        self._current_path: Path | None = None
        self._switch_modified: bool = False
        self._is_closing: bool = False
        self._user_closed_problems_panel: bool = False
        self._prev_error_count: int = 0

        self._build_menus_and_toolbars()
        self._build_docks()
        self._build_status_bar()
        self._connect_signals()
        self.circuit_scene.undo_stack.cleanChanged.connect(
            lambda _clean: self._update_window_title()
        )
        self.apply_theme(self.theme)
        self._update_window_title()

    def restoreState(self, state: QByteArray | bytes, version: int = 0) -> bool:
        """Restore window state while ensuring any stale Oscilloscope dock cannot be brought back."""
        res = super().restoreState(state, version)
        for dock in self.findChildren(QDockWidget):
            title = dock.windowTitle().lower()
            obj_name = dock.objectName().lower()
            if "oscilloscope" in title or "oscilloscope" in obj_name:
                self.removeDockWidget(dock)
                dock.setParent(None)
                dock.deleteLater()
        return res

    def _build_menus_and_toolbars(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")
        self.act_new = QAction("&New", self)
        self.act_new.setToolTip("Clear schematic and start a new circuit (Ctrl+N)")
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self._on_new_circuit)
        file_menu.addAction(self.act_new)

        self.act_open = QAction("&Open...", self)
        self.act_open.setIconText("Open")
        self.act_open.setToolTip("Open a saved circuit file (Ctrl+O)")
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self._on_open_circuit)
        file_menu.addAction(self.act_open)

        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._update_recent_files_menu()

        self.examples_menu = file_menu.addMenu("&Examples")
        self._build_examples_menu()

        self.act_save = QAction("&Save", self)
        self.act_save.setIconText("Save")
        self.act_save.setToolTip("Save current circuit to file (Ctrl+S)")
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._on_save_circuit)
        file_menu.addAction(self.act_save)

        self.act_save_as = QAction("Save &As...", self)
        self.act_save_as.setToolTip("Save the circuit under a new name (Ctrl+Shift+S)")
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self._on_save_circuit_as)
        file_menu.addAction(self.act_save_as)

        file_menu.addSeparator()
        self.act_export_png = QAction("Export as &PNG...", self)
        self.act_export_png.setToolTip("Export schematic as a PNG image")
        self.act_export_png.triggered.connect(self._on_export_png)
        file_menu.addAction(self.act_export_png)

        self.act_export_svg = QAction("Export as &SVG...", self)
        self.act_export_svg.setToolTip(
            "Export schematic as scalable vector graphics (SVG)"
        )
        self.act_export_svg.triggered.connect(self._on_export_svg)
        file_menu.addAction(self.act_export_svg)

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
        self.act_undo.setToolTip("Undo last action (Shortcut: Ctrl+Z)")
        self.act_redo = self.circuit_scene.undo_stack.createRedoAction(
            self, "&Redo"
        )
        redo_shortcuts = [QKeySequence.StandardKey.Redo]
        if QKeySequence("Ctrl+Y") not in redo_shortcuts:
            redo_shortcuts.append(QKeySequence("Ctrl+Y"))
        self.act_redo.setShortcuts(redo_shortcuts)
        self.act_redo.setToolTip("Redo last undone action (Shortcut: Ctrl+Y)")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()

        self.act_cut = QAction("Cu&t", self)
        self.act_cut.setShortcut(QKeySequence.StandardKey.Cut)
        self.act_cut.setToolTip("Cut selected items (Shortcut: Ctrl+X)")
        self.act_cut.triggered.connect(self.circuit_scene.cut_selected)
        edit_menu.addAction(self.act_cut)

        self.act_copy = QAction("&Copy", self)
        self.act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.act_copy.setToolTip("Copy selected items (Shortcut: Ctrl+C)")
        self.act_copy.triggered.connect(self.circuit_scene.copy_selected)
        edit_menu.addAction(self.act_copy)

        self.act_paste = QAction("&Paste", self)
        self.act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.act_paste.setToolTip("Paste copied items (Shortcut: Ctrl+V)")
        self.act_paste.triggered.connect(self.circuit_scene.paste_clipboard)
        edit_menu.addAction(self.act_paste)

        self.act_delete = QAction("&Delete", self)
        self.act_delete.setIconText("Del")
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.setToolTip("Delete selected items and attached wires (Shortcut: Del)")
        self.act_delete.triggered.connect(self.circuit_scene.delete_selected)
        edit_menu.addAction(self.act_delete)

        edit_menu.addSeparator()
        self.act_rotate = QAction("&Rotate (R)", self)
        self.act_rotate.setIconText("Rot")
        self.act_rotate.setToolTip(
            "Rotate selected component(s) 90° clockwise (Shortcut: R)"
        )
        self.act_rotate.triggered.connect(self._rotate_selected)
        edit_menu.addAction(self.act_rotate)

        self.act_flip = QAction("&Flip (F)", self)
        self.act_flip.setIconText("Flip")
        self.act_flip.setToolTip(
            "Flip selected component(s) horizontally (Shortcut: F)"
        )
        self.act_flip.triggered.connect(self._flip_selected)
        edit_menu.addAction(self.act_flip)

        self.act_wire_mode = QAction("&Wire (W)", self, checkable=True)
        self.act_wire_mode.setIconText("Wire")
        self.act_wire_mode.setToolTip(
            "Toggle Wire Drawing mode (Shortcut: W). You can also drag directly from any terminal."
        )
        self.act_wire_mode.toggled.connect(self.circuit_view.set_wire_mode)
        edit_menu.addAction(self.act_wire_mode)

        self.act_junction = QAction("&Junction (J)", self)
        self.act_junction.setIconText("Junc")
        self.act_junction.setToolTip(
            "Place or remove an explicit junction dot at the cursor (Shortcut: J)"
        )
        self.act_junction.triggered.connect(
            lambda: self.circuit_scene.toggle_junction_at(
                self.circuit_view._last_scene_pos
            )
        )
        edit_menu.addAction(self.act_junction)

        edit_menu.addSeparator()
        self.act_preferences = QAction("&Preferences...", self)
        self.act_preferences.setToolTip("Application preferences (number format, etc.)")
        self.act_preferences.triggered.connect(self._open_preferences_dialog)
        edit_menu.addAction(self.act_preferences)

        # View menu
        self.view_menu = menu_bar.addMenu("&View")
        self.act_toggle_grid = QAction(
            "Show &Grid (20 px)", self, checkable=True
        )
        self.act_toggle_grid.setChecked(True)
        self.act_toggle_grid.toggled.connect(self.circuit_scene.set_show_grid)
        self.view_menu.addAction(self.act_toggle_grid)

        self.act_toggle_theme = QAction("Light &Theme", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+T"))
        self.act_toggle_theme.setToolTip("Toggle between Dark and Light themes (Shortcut: Ctrl+T)")
        self.act_toggle_theme.triggered.connect(self.toggle_theme)
        self.view_menu.addAction(self.act_toggle_theme)

        self.view_menu.addSeparator()
        act_zoom_in = QAction("Zoom &In", self)
        act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        act_zoom_in.triggered.connect(self.circuit_view.zoom_in)
        self.view_menu.addAction(act_zoom_in)

        act_zoom_out = QAction("Zoom &Out", self)
        act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        act_zoom_out.triggered.connect(self.circuit_view.zoom_out)
        self.view_menu.addAction(act_zoom_out)

        act_zoom_reset = QAction("&Reset Zoom (100%)", self)
        act_zoom_reset.triggered.connect(self.circuit_view.reset_zoom)
        self.view_menu.addAction(act_zoom_reset)

        self.act_zoom_fit = QAction("Zoom to &Fit", self)
        self.act_zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.act_zoom_fit.setToolTip("Fit all components to window (Shortcut: Ctrl+0)")
        self.act_zoom_fit.triggered.connect(self.circuit_view.zoom_to_fit)
        self.view_menu.addAction(self.act_zoom_fit)

        # Simulation menu
        sim_menu = menu_bar.addMenu("&Simulation")
        self.act_run = QAction("▶ &Run / Resume", self)
        self.act_run.setShortcut(QKeySequence("F5"))
        self.act_run.setToolTip("Start or resume simulation (Shortcut: F5)")
        self.act_run.triggered.connect(self.start_simulation)

        self.act_pause = QAction("⏸ &Pause", self)
        self.act_pause.setShortcut(QKeySequence("F6"))
        self.act_pause.setToolTip("Pause circuit simulation (Shortcut: F6)")
        self.act_pause.triggered.connect(self.pause_simulation)

        self.act_stop = QAction("⏹ &Stop", self)
        self.act_stop.setShortcut(QKeySequence("Shift+F5"))
        self.act_stop.setToolTip("Stop simulation and reset meters/states (Shortcut: Shift+F5 / F7)")
        self.act_stop.triggered.connect(self.stop_simulation)

        sim_menu.addAction(self.act_run)
        sim_menu.addAction(self.act_pause)
        sim_menu.addAction(self.act_stop)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        act_reload_svg = QAction("&Reload Custom SVGs", self)
        act_reload_svg.triggered.connect(self._reload_custom_svgs)
        help_menu.addAction(act_reload_svg)

        help_menu.addSeparator()
        self.act_report_issue = QAction(
            "&Report a problem / suggest a feature", self
        )
        self.act_report_issue.setToolTip(
            "Open GitHub issue tracker in your web browser"
        )
        self.act_report_issue.triggered.connect(self._on_report_issue)
        help_menu.addAction(self.act_report_issue)

        help_menu.addSeparator()
        self.act_about = QAction("&About CircuitSim", self)
        self.act_about.setToolTip("About CircuitSim")
        self.act_about.triggered.connect(self._show_about_dialog)
        help_menu.addAction(self.act_about)

        # Compact Top Toolbar (sized so Speed dropdown is always visible without overflow)
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
        self.btn_run = main_tb.widgetForAction(self.act_run)
        self.btn_pause = main_tb.widgetForAction(self.act_pause)
        self.btn_stop = main_tb.widgetForAction(self.act_stop)
        main_tb.addWidget(QLabel(" Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.setToolTip("Select simulation speed relative to real time")
        self.speed_combo.addItem("1x Real-Time", SimulationSpeed.REAL_TIME.value)
        self.speed_combo.addItem("0.1x Slow", SimulationSpeed.SLOW_MOTION.value)
        self.speed_combo.addItem("10x Fast", SimulationSpeed.FAST.value)
        self.speed_combo.setMinimumWidth(115)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_combo_changed)
        main_tb.addWidget(self.speed_combo)
        main_tb.addSeparator()
        main_tb.addAction(self.act_toggle_theme)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, main_tb)

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
        self.palette_dock.setFixedWidth(240)
        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.palette_dock
        )

        # 2. Right Dock: Properties / Info Panel
        self.info_dock = QDockWidget("Properties / Info Panel", self)
        self.info_dock.setFixedWidth(280)

        self.info_scroll = QScrollArea(self.info_dock)
        self.info_scroll.setWidgetResizable(True)
        self.info_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.info_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(10, 10, 10, 10)
        self.info_label = QLabel(DEFAULT_SHORTCUTS_HELP_TEXT)
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.info_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        info_layout.addWidget(self.info_label)
        self.info_scroll.setWidget(info_container)
        self.info_dock.setWidget(self.info_scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.info_dock)

        # 3. Bottom Dock: Problems Panel
        self.problems_dock = ProblemsDock(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.problems_dock)
        self.resizeDocks([self.problems_dock], [120], Qt.Orientation.Vertical)
        self.problems_dock.hide()

        self.problems_dock.user_closed.connect(self._on_problems_panel_closed)
        self.problems_dock.visibilityChanged.connect(self._on_problems_visibility_changed)
        self.problems_dock.panel.problem_activated.connect(self._on_problem_part_selected)

        # Add dock panel visibility actions to View menu
        if hasattr(self, "view_menu"):
            self.view_menu.addSeparator()
            self.view_menu.addAction(self.palette_dock.toggleViewAction())
            self.view_menu.addAction(self.info_dock.toggleViewAction())
            self.action_view_problems = QAction("&Problems", self)
            self.action_view_problems.setShortcut("F8")
            self.action_view_problems.setCheckable(True)
            self.action_view_problems.setChecked(False)
            self.action_view_problems.triggered.connect(self._toggle_problems_panel)
            self.view_menu.addAction(self.action_view_problems)

    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        sb.setFixedHeight(26)
        self.status_state_indicator = QLabel("■ Stopped")
        self.status_coords = QLabel("Grid: (0, 0) | Pos: (0, 0) px")
        self.status_sim = QLabel("Sim: Stopped (t = 0 s)")
        self.status_counts = QLabel("Components: 0 | Wires: 0")
        self.status_zoom = QLabel("Zoom: 100%")
        self.status_warnings = QLabel("Ready")

        sb.addWidget(self.status_state_indicator)
        sb.addWidget(self.status_coords)
        sb.addPermanentWidget(self.status_sim)
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
        self.circuit_scene.selection_info_changed.connect(
            self._update_info_panel
        )
        self.circuit_scene.circuit_modified.connect(self._on_circuit_modified)
        self.circuit_scene.switch_toggled_by_user.connect(
            self._on_user_switch_toggled
        )
        self.circuit_scene.component_parameters_edited.connect(
            self._on_user_parameters_edited
        )
        self.sim_controller.frame_ready.connect(self._on_simulation_frame)

    # ------------------------------------------------------------------
    # Simulation Controls (Run / Pause / Stop / Speed / Live Edits)
    # ------------------------------------------------------------------

    def _sync_schematic_to_worker(self) -> None:
        placed_specs = [
            item.to_placed_spec() for item in self.circuit_scene.placed_items
        ]
        wire_specs = [
            wire.to_wire_spec() for wire in self.circuit_scene.placed_wires
        ]
        self.sim_controller.load_schematic(
            placed_specs, wire_specs, self.circuit_scene.explicit_junctions
        )

    def start_simulation(self) -> None:
        """Send current schematic to the worker thread and start simulation."""
        if self._sim_state != SimulationState.PAUSED:
            self._user_closed_problems_panel = False
            self._prev_error_count = 0
            self._sync_schematic_to_worker()
        self.sim_controller.start()

    def pause_simulation(self) -> None:
        """Pause the running simulation."""
        self.sim_controller.pause()

    def _apply_transport_controls_ui(
        self,
        state: SimulationState,
        *,
        error_reason: str = "",
    ) -> TransportControlsViewState:
        """Apply pure-Python `TransportControlsViewState` to toolbar actions, buttons, and status bar."""
        ui = compute_transport_controls_state(state, error_reason=error_reason)
        self._last_error_reason = error_reason

        self.act_run.setEnabled(ui.run_enabled)
        self.act_run.setText(ui.run_label)
        self.act_run.setIconText(ui.run_icon_text)
        self.act_run.setToolTip(ui.run_tooltip)

        self.act_pause.setEnabled(ui.pause_enabled)
        self.act_pause.setText(ui.pause_label)
        self.act_pause.setIconText(ui.pause_icon_text)
        self.act_pause.setToolTip(ui.pause_tooltip)

        self.act_stop.setEnabled(ui.stop_enabled)
        self.act_stop.setText(ui.stop_label)
        self.act_stop.setIconText(ui.stop_icon_text)
        self.act_stop.setToolTip(ui.stop_tooltip)

        is_dark = self.theme == ThemeMode.DARK
        green_fg = "#3FB950" if is_dark else "#1A7F37"
        amber_fg = "#D29922" if is_dark else "#9A6700"
        red_fg = "#FF6B6B" if is_dark else "#CF222E"
        muted_fg = "#8B949E" if is_dark else "#57606A"

        if self.btn_run is not None:
            if ui.run_visual_role == "active_green":
                self.btn_run.setStyleSheet(
                    f"background-color: rgba(46, 160, 67, 0.22); "
                    f"border: 2px solid {green_fg}; color: {green_fg}; font-weight: 700;"
                )
            elif ui.run_visual_role == "error_red":
                self.btn_run.setStyleSheet(
                    f"border: 2px solid {red_fg}; color: {red_fg}; font-weight: 700;"
                )
            else:
                self.btn_run.setStyleSheet("")

        if self.btn_pause is not None:
            if ui.pause_visual_role == "active_amber":
                self.btn_pause.setStyleSheet(
                    f"background-color: rgba(210, 153, 34, 0.22); "
                    f"border: 2px solid {amber_fg}; color: {amber_fg}; font-weight: 700;"
                )
            else:
                self.btn_pause.setStyleSheet("")

        self.status_state_indicator.setText(ui.status_indicator_text)
        if ui.status_indicator_role == "running":
            self.status_state_indicator.setStyleSheet(
                f"color: {green_fg}; font-weight: 700; padding: 0 6px;"
            )
        elif ui.status_indicator_role == "paused":
            self.status_state_indicator.setStyleSheet(
                f"color: {amber_fg}; font-weight: 700; padding: 0 6px;"
            )
        elif ui.status_indicator_role == "error":
            self.status_state_indicator.setStyleSheet(
                f"color: {red_fg}; font-weight: 700; padding: 0 6px;"
            )
        else:
            self.status_state_indicator.setStyleSheet(
                f"color: {muted_fg}; font-weight: 600; padding: 0 6px;"
            )

        return ui

    def stop_simulation(self) -> None:
        """Stop simulation and reset meters/states back to t = 0."""
        self._user_closed_problems_panel = False
        self._prev_error_count = 0
        self.sim_controller.stop()
        self.circuit_scene.clear_diagnostics()
        for item in self.circuit_scene.placed_items:
            item.reset_live_telemetry()
        self._sim_state = SimulationState.STOPPED
        self._apply_transport_controls_ui(SimulationState.STOPPED)
        self.status_sim.setText("Sim: Stopped (t = 0 s)")
        self._refresh_warnings_display()

    # ------------------------------------------------------------------
    # File handling: New / Open / Save / Save As (.circ)
    # ------------------------------------------------------------------

    def _update_window_title(self) -> None:
        """Show '<file name>*' (asterisk = unsaved changes) in the title bar."""
        if self._is_closing:
            return
        name = self._current_path.name if self._current_path else "Untitled"
        star = "*" if self.has_unsaved_changes() else ""
        self.setWindowTitle(f"{name}{star} — CircuitSim")

    def has_unsaved_changes(self) -> bool:
        if self._is_closing:
            return False
        return not self.circuit_scene.undo_stack.isClean() or self._switch_modified

    def _show_error(self, title: str, text: str) -> None:
        """Friendly error box (separate method so tests can replace it)."""
        QMessageBox.warning(self, title, text)

    def _ask_save_discard_cancel(self, what: str) -> QMessageBox.StandardButton:
        """Ask the user what to do with unsaved changes (separate method for tests)."""
        return QMessageBox.question(
            self,
            "Unsaved changes",
            f"The circuit has unsaved changes.\nSave them before {what}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

    def _confirm_discard_changes(self, what: str) -> bool:
        """Return True if it is fine to continue (nothing to lose, saved, or discarded)."""
        if not self.has_unsaved_changes():
            return True
        answer = self._ask_save_discard_cancel(what)
        if answer == QMessageBox.StandardButton.Save:
            return self._on_save_circuit()
        return answer == QMessageBox.StandardButton.Discard

    def _current_view_state(self) -> ViewState:
        speed = self.speed_combo.currentData()
        return ViewState(
            theme=self.theme.value,
            zoom=self.circuit_view.zoom_factor,
            pan=self.circuit_view.view_center(),
            simulation_speed=str(speed) if speed else SimulationSpeed.REAL_TIME.value,
        )

    def _on_new_circuit(self) -> None:
        if not self._confirm_discard_changes("starting a new circuit"):
            return
        self.stop_simulation()
        self.circuit_scene.clear_schematic()
        self._current_path = None
        self._switch_modified = False
        self._update_window_title()

    def _on_open_circuit(self) -> None:
        if not self._confirm_discard_changes("opening another file"):
            return
        start_dir = str(self._current_path.parent) if self._current_path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open circuit", start_dir, "CircuitSim circuits (*.circ);;All files (*)"
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> bool:
        """Load a `.circ` file. On any problem show a message and change nothing."""
        p = Path(path)
        try:
            doc = load_document(p)  # reads + validates; builds new objects only
            self.circuit_scene.load_document(doc)  # all-or-nothing swap
        except CircuitFileError as exc:
            self._show_error("Could not open file", str(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - never crash on a bad file
            self._show_error(
                "Could not open file",
                f"Something unexpected went wrong while opening '{p.name}' ({exc}). "
                "Your current circuit was not changed.",
            )
            return False

        self.stop_simulation()
        if doc.view.theme != self.theme.value:
            self.apply_theme(ThemeMode(doc.view.theme))
        idx = self.speed_combo.findData(doc.view.simulation_speed)
        if idx >= 0:
            self.speed_combo.setCurrentIndex(idx)
        self.circuit_view.set_view_state(doc.view.zoom, doc.view.pan)
        self._current_path = p
        self._switch_modified = False
        self.settings.add_recent_file(p)
        self._update_recent_files_menu()
        self._update_window_title()
        self.statusBar().showMessage(f"Opened {p.name}", 4000)
        return True

    def save_to_path(self, path: str | Path) -> bool:
        """Save the circuit to `path`; show a message and return False on failure."""
        p = Path(path)
        try:
            save_document(p, self.circuit_scene.to_document(self._current_view_state()))
        except CircuitFileError as exc:
            self._show_error("Could not save file", str(exc))
            return False
        self.circuit_scene.undo_stack.setClean()
        self._current_path = p
        self._switch_modified = False
        self._update_window_title()
        self.statusBar().showMessage(f"Saved {p.name}", 4000)
        return True

    def _on_save_circuit(self) -> bool:
        if self._current_path is None:
            return self._on_save_circuit_as()
        return self.save_to_path(self._current_path)

    def _on_save_circuit_as(self) -> bool:
        start = str(self._current_path) if self._current_path else "circuit.circ"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save circuit as", start, "CircuitSim circuits (*.circ)"
        )
        if not path:
            return False
        if not path.lower().endswith(".circ"):
            path += ".circ"
        saved = self.save_to_path(path)
        if saved:
            self.settings.add_recent_file(path)
            self._update_recent_files_menu()
        return saved

    def _on_export_png(self) -> None:
        if not self.circuit_scene.placed_items and not self.circuit_scene.placed_wires:
            QMessageBox.information(
                self, "Export as PNG", "Circuit is empty. Nothing to export."
            )
            return
        dlg = ExportOptionsDialog(self._theme, self)
        if dlg.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return
        theme_mode = dlg.selected_theme_mode()

        default_name = "schematic.png"
        if self._current_path:
            default_name = f"{self._current_path.stem}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Schematic as PNG", default_name, "PNG Images (*.png)"
        )
        if not path:
            return
        try:
            img = export_schematic_to_image(
                self.circuit_scene, theme_mode=theme_mode
            )
            if img is None or not img.save(path):
                raise OSError(f"Could not save PNG to {path}")
            self.statusBar().showMessage(f"Exported PNG: {path}", 3000)
        except Exception as exc:
            QMessageBox.critical(
                self, "Export Error", f"Failed to export PNG:\n{exc}"
            )

    def _on_export_svg(self) -> None:
        if not self.circuit_scene.placed_items and not self.circuit_scene.placed_wires:
            QMessageBox.information(
                self, "Export as SVG", "Circuit is empty. Nothing to export."
            )
            return
        dlg = ExportOptionsDialog(self._theme, self)
        if dlg.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return
        theme_mode = dlg.selected_theme_mode()

        default_name = "schematic.svg"
        if self._current_path:
            default_name = f"{self._current_path.stem}.svg"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Schematic as SVG", default_name, "SVG Images (*.svg)"
        )
        if not path:
            return
        try:
            ok = export_schematic_to_svg(
                self.circuit_scene, path, theme_mode=theme_mode
            )
            if not ok:
                raise OSError(f"Could not save SVG to {path}")
            self.statusBar().showMessage(f"Exported SVG: {path}", 3000)
        except Exception as exc:
            QMessageBox.critical(
                self, "Export Error", f"Failed to export SVG:\n{exc}"
            )

    def _on_report_issue(self) -> None:
        QDesktopServices.openUrl(QUrl(ISSUES_URL))

    def _show_about_dialog(self) -> None:
        version = get_app_version()
        text = (
            f"<h3>CircuitSim v{version}</h3>"
            f"<p>Educational desktop electrical circuit simulator built with Python, NumPy/SciPy, and PySide6.</p>"
            f"<p><b>License:</b> MIT License</p>"
            f"<p><b>Source Code:</b> <a href='{REPO_URL}'>{REPO_URL}</a></p>"
            f"<p><b>Report Issues / Feedback:</b> <a href='{ISSUES_URL}'>{ISSUES_URL}</a></p>"
        )
        QMessageBox.about(self, "About CircuitSim", text)

    def _open_preferences_dialog(self) -> None:
        dlg = PreferencesDialog(self.settings, self)
        if dlg.exec() == PreferencesDialog.DialogCode.Accepted:
            self.circuit_scene.update()
            self.statusBar().showMessage(
                f"Preferences saved (number format: {self.settings.get_number_format()})",
                3000,
            )

    def _update_recent_files_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.settings.get_recent_files()
        if not recent:
            empty_act = QAction("No Recent Files", self)
            empty_act.setEnabled(False)
            self.recent_menu.addAction(empty_act)
            return

        for path_str in recent:
            p = Path(path_str)
            act = QAction(p.name, self)
            act.setToolTip(path_str)
            act.setStatusTip(path_str)
            act.triggered.connect(
                lambda _checked=False, ps=path_str: self._on_open_recent_file(ps)
            )
            self.recent_menu.addAction(act)

        self.recent_menu.addSeparator()
        clear_act = QAction("Clear list", self)
        clear_act.triggered.connect(self._on_clear_recent_files)
        self.recent_menu.addAction(clear_act)

    def _on_clear_recent_files(self) -> None:
        self.settings.clear_recent_files()
        self._update_recent_files_menu()

    def _on_open_recent_file(self, path_str: str) -> None:
        p = Path(path_str)
        if not p.is_file():
            self.settings.remove_recent_file(path_str)
            self._update_recent_files_menu()
            self._show_error(
                "File Not Found",
                f"The file '{p.name}' could not be found:\n{path_str}\n\nIt has been removed from the recent files list.",
            )
            return

        if not self._confirm_discard_changes("opening another file"):
            return

        self.open_path(p)

    def _build_examples_menu(self) -> None:
        self.examples_menu.clear()
        ex_dir = Path(__file__).resolve().parent.parent / "resources" / "examples"
        index_file = ex_dir / "index.json"
        if not index_file.exists():
            return
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except Exception:
            return

        for item in catalog:
            title = item.get("title", "Example")
            desc = item.get("description", "")
            fname = item.get("filename", "")
            act = QAction(title, self)
            act.setToolTip(desc)
            act.setStatusTip(desc)
            act.triggered.connect(
                lambda _checked=False, p=ex_dir / fname, t=title: self._on_open_example(p, t)
            )
            self.examples_menu.addAction(act)

    def _on_open_example(self, path: Path, title: str) -> None:
        if not self._confirm_discard_changes("opening an example circuit"):
            return

        try:
            doc = load_document(path)
            self.circuit_scene.load_document(doc)
        except Exception as exc:
            self._show_error("Could not load example", f"Failed to load example circuit: {exc}")
            return

        self.stop_simulation()
        if doc.view.theme != self.theme.value:
            self.apply_theme(ThemeMode(doc.view.theme))
        idx = self.speed_combo.findData(doc.view.simulation_speed)
        if idx >= 0:
            self.speed_combo.setCurrentIndex(idx)
        self.circuit_view.set_view_state(doc.view.zoom, doc.view.pan)

        # Open as a NEW untitled circuit so bundled files cannot be overwritten
        self._current_path = None
        self._switch_modified = False
        self._update_window_title()
        self.statusBar().showMessage(f"Loaded example: {title}", 4000)

    def _on_speed_combo_changed(self, index: int) -> None:
        raw = self.speed_combo.itemData(index)
        if raw:
            self.sim_controller.set_speed(SimulationSpeed(str(raw)))

    def _on_user_switch_toggled(self, switch_name: str, _closed: bool) -> None:
        self._switch_modified = True
        self._update_window_title()
        if self._sim_state in (SimulationState.RUNNING, SimulationState.PAUSED):
            self.sim_controller.toggle_switch(switch_name)

    def _on_user_parameters_edited(
        self, comp_name: str, param_map: object
    ) -> None:
        if (
            isinstance(param_map, dict)
            and self._sim_state in (SimulationState.RUNNING, SimulationState.PAUSED)
        ):
            for k, v in param_map.items():
                self.sim_controller.update_component_parameter(comp_name, k, v)

    def _on_simulation_frame(self, frame: SimulationFrame) -> None:
        self._sim_state = frame.state
        self.circuit_scene.apply_simulation_frame(frame)

        errors = [d for d in frame.diagnostics if d.severity == "error"]
        err_msg = errors[0].message if errors else ""
        self._apply_transport_controls_ui(frame.state, error_reason=err_msg)

        t_str = format_engineering_value(frame.sim_time, "s", sig_figs=3)
        dt_str = format_engineering_value(frame.dt, "s", sig_figs=3)
        if frame.state == SimulationState.RUNNING:
            self.status_sim.setText(
                f"Sim: Running | t = {t_str} | dt = {dt_str} | Speed: {frame.speed_ratio:.2f}x"
            )
        elif frame.state == SimulationState.PAUSED:
            self.status_sim.setText(
                f"Sim: Paused | t = {t_str} | dt = {dt_str}"
            )
        elif frame.state == SimulationState.ERROR:
            self.status_sim.setText("Sim: Stopped (Topology Error)")
        else:
            self.status_sim.setText("Sim: Stopped (t = 0 s)")

        if frame.diagnostics:
            n_prob = len(frame.diagnostics)
            prob_str = "1 problem" if n_prob == 1 else f"{n_prob} problems"
            if errors:
                self.status_warnings.setStyleSheet(
                    "color: #FF6B6B; font-weight: 600;"
                )
            else:
                self.status_warnings.setStyleSheet(
                    "color: #FFA726; font-weight: 600;"
                )
            self.status_warnings.setText(prob_str)
        else:
            self.status_warnings.setStyleSheet("")
            if frame.state == SimulationState.RUNNING:
                self.status_warnings.setText("0 problems")
            else:
                self._refresh_warnings_display()

        # Update Problems Panel diagnostics
        if hasattr(self, "problems_dock"):
            self.problems_dock.panel.update_diagnostics(frame.diagnostics)

        # Auto-open Problems panel on new error unless closed during current run
        curr_error_count = len(errors)
        if curr_error_count > self._prev_error_count:
            if not self._user_closed_problems_panel and hasattr(self, "problems_dock"):
                self.problems_dock.show()
                if hasattr(self, "action_view_problems"):
                    self.action_view_problems.setChecked(True)
        self._prev_error_count = curr_error_count

    def _toggle_problems_panel(self, checked: bool | None = None) -> None:
        if checked is None:
            new_visible = not self.problems_dock.isVisible()
        else:
            new_visible = bool(checked)
        if not new_visible and self._sim_state == SimulationState.RUNNING:
            self._user_closed_problems_panel = True
        self.problems_dock.setVisible(new_visible)
        if hasattr(self, "action_view_problems"):
            self.action_view_problems.setChecked(new_visible)

    def _on_problems_panel_closed(self) -> None:
        if self._sim_state == SimulationState.RUNNING:
            self._user_closed_problems_panel = True
        if hasattr(self, "action_view_problems"):
            self.action_view_problems.setChecked(False)

    def _on_problems_visibility_changed(self, visible: bool) -> None:
        if not visible and self._sim_state == SimulationState.RUNNING:
            self._user_closed_problems_panel = True
        if hasattr(self, "action_view_problems"):
            self.action_view_problems.setChecked(visible)

    def _on_problem_part_selected(self, part_name: str) -> None:
        for item in self.circuit_scene.items():
            if isinstance(item, ComponentItem) and item.component.name == part_name:
                self.circuit_scene.clearSelection()
                item.setSelected(True)
                self.circuit_view.centerOn(item)
                break

    # ------------------------------------------------------------------
    # Theme & UI Updates
    # ------------------------------------------------------------------

    def apply_theme(self, theme: ThemeMode) -> None:
        """Apply `theme` ('dark' or 'light') across window, palette, and canvas."""
        self.theme = theme
        palette = get_theme_palette(theme)
        self.setStyleSheet(build_stylesheet(palette))
        self.circuit_scene.set_theme(theme)
        self.palette_widget.set_theme(theme)

        if theme == ThemeMode.DARK:
            self.act_toggle_theme.setText("Light &Theme")
        else:
            self.act_toggle_theme.setText("Dark &Theme")
        self.act_toggle_theme.setIconText("Theme")

        self._apply_transport_controls_ui(
            self._sim_state, error_reason=self._last_error_reason
        )
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

    def _on_cursor_moved(
        self, x_px: float, y_px: float, gx: int, gy: int
    ) -> None:
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
        if self._sim_state == SimulationState.RUNNING:
            self._sync_schematic_to_worker()

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
        val_str = (
            item.live_display_value
            if item.live_display_value is not None
            else (format_component_value_summary(comp) or "—")
        )
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

        v_live = format_engineering_value(comp.voltage, "V")
        i_live = format_engineering_value(comp.current, "A")
        p_live = format_engineering_value(comp.power, "W")
        extra_live = ""
        if isinstance(comp, Lightbulb):
            extra_live = f"\n  • Brightness: {comp.brightness_percent:.1f}%"
            if comp.is_over_bright:
                extra_live += " (OVER-BRIGHT!)"
        if item.diagnostic_message:
            extra_live += f"\n  • Diagnostic: {item.diagnostic_message}"

        self.info_label.setText(
            f"Name: {comp.name}\n"
            f"Type: {meta.display_name} ({comp.component_type})\n"
            f"Category: {meta.category}\n"
            f"Value: {val_str}\n"
            f"Position: ({int(item.pos().x())}, {int(item.pos().y())}) px\n"
            f"Rotation: {item.rotation_deg}° | Flipped: {item.flipped_h}\n"
            f"Symbol Source: {source_kind}\n\n"
            f"Live Operating State:\n"
            f"  • Voltage: {v_live}\n"
            f"  • Current: {i_live}\n"
            f"  • Power: {p_live}{extra_live}\n\n"
            f"Terminals & Nets:\n{term_lines}\n\n"
            f"(Double-click {comp.name} on canvas to edit values)"
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Orderly window shutdown sequence:

        1. If already closing, accept immediately.
        2. Ask about unsaved changes first; if the user cancels, change nothing.
        3. Mark window as closing so handlers never touch the undo stack.
        4. Stop the simulation worker thread and wait for it.
        5. Disconnect listeners from the undo stack and worker before destruction.
        6. Proceed with base window close.
        """
        if self._is_closing:
            event.accept()
            return

        # 1. Ask about unsaved changes first; if user cancels, change nothing
        if not self._confirm_discard_changes("closing the window"):
            event.ignore()
            return

        # 2. Mark window as closing
        self._is_closing = True
        try:
            from circuitsim.app.crash_handler import set_shutting_down

            set_shutting_down(True)
        except Exception:
            pass

        # 3. Stop the simulation worker thread and wait for it
        self.sim_controller.shutdown()

        # 4. Disconnect handlers from the undo stack and worker before destruction
        try:
            self.circuit_scene.undo_stack.cleanChanged.disconnect()
        except (RuntimeError, TypeError):
            pass

        try:
            self.sim_controller.frame_ready.disconnect(self._on_simulation_frame)
        except (RuntimeError, TypeError):
            pass

        super().closeEvent(event)
