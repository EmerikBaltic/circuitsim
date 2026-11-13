# Project Progress — CircuitSim

## FLASH QUEUE
- Phase 1 Task 1: Housekeeping (.gitignore, switch breakdown voltage hint, label collision avoidance) - [done]
- Phase 1 Task 2: Recent Files (File > Open Recent, 8 files, injected path, missing file handling) - [done]
- Phase 1 Task 3: Example Circuits (File > Examples, 5 bundled circuits, package data, analytic tests) - [done]
- Phase 1 Task 4: Zoom to fit (Ctrl+0) and shortcuts (F5, F6, Shift+F5, info panel, tests) - [done]
- Phase 1 Task 5: Hover tooltips with live values (part & terminal hover, immutable frame, tests) - [done]
- Phase 1 Task 6: Export schematic (File > Export PNG/SVG, QSvgGenerator, white/dark option, tests) - [done]
- Phase 1 Task 7: About dialog, feedback link, crash log exception hook - [done]
- Phase 1 Task 8: Bulb burn-out option (dialog UI, dark+cross drawing, amber note, tests) - [done]
- Phase 1 Task 9: Number format setting (Preferences: Auto/Dot/Comma, display only, tests) - [done]
- Phase 1 Task 10: Continuous integration (.github/workflows/ci.yml, README badge) - [done]
- Phase 2: Step 3C Full Properties Dialog (Identity, parameters, live readout, inductor helpers) - [todo]
- Phase 3: Oscilloscope Plan (measure solver step rate, plan max 50 lines, wait for approval) - [todo]

## HYDROGEN QUEUE (Last Commit: phase-1.1)
### Phase 0: Verify
- [x] Verify branch `main`, clean status, full suite baseline (`290 passed in 28.08s`), check prior work - *done*

### Phase 1: Deprecation Warnings (on `main`)
- [x] 1.1 Replace deprecated Qt calls (`event.pos()`, `globalPos()`, `x()`, `y()`, etc.) across `src/` with Qt 6 API (`position().toPoint()`, etc.) - *done*
- [ ] 1.2 Add `filterwarnings = ["error::DeprecationWarning:circuitsim.*"]` to `pyproject.toml`, list third-party warnings, add filter test - *todo*

### Phase 2: Rename to Ohmbench, Stage 1 (on `main`)
- [ ] 2.1 Rename Inventory in `PROGRESS.md` - *todo*
- [ ] 2.2 Single source of truth `src/circuitsim/app_info.py` (no Qt) and user-visible strings - *todo*
- [ ] 2.3 App Identity (`QCoreApplication` org/app = Ohmbench, one-time migration from `python`, Windows `AppUserModelID`) - *todo*
- [ ] 2.4 Stored Data (`.circ` backward compatibility and format identifier choice) - *todo*
- [ ] 2.5 Tests (verify user-visible strings use `APP_NAME`, list legitimate old-name strings) - *todo*
- [ ] 2.6 Docs (`README.md`, docs, `"Formerly CircuitSim"`, Stage 2 plan in `PROGRESS.md`) - *todo*

### Phase 3: Mutation Check (on `main`)
- [ ] 3a Component empty value plate mutation vs LED stray-background test - *todo*
- [ ] 3b Problems panel close button blank draw mutation vs blank-button test - *todo*
- [ ] 3c Light theme palette missing attribute mutation vs palette test - *todo*
- [ ] 3d Swap LED anode/cathode terminals vs LED symbol test - *todo*
- [ ] 3e Unguarded `paint()` exception vs paint safety test - *todo*

### Phase 4: Wire Redesign, Step 4A-1 (branch `wire-redesign`)
- [ ] 4.1 Scene state (`WireGraph`) and undo/redo + move merge + `add_wire` between attachments - *todo*
- [ ] 4.2 Display (`WireItem` using `route()`, `JunctionItem` degree >= 3, `FreeEnd` hollow marker, 10 px hit stroke, wire tool notice) - *todo*
- [ ] 4.3 Netlist (`circuitsim.wiring.netlist`) and diagnostics (including `FreeEnd` amber note) - *todo*
- [ ] 4.4 Moving, rotating, flipping, deleting (100 random ops + S1 + S2) - *todo*
- [ ] 4.5 Save and load schema v2 + v1 migration - *todo*
- [ ] 4.6 Existing features that touch wires (examples, export, labels, tooltips, zoom-to-fit, recent/dirty/undo) - *todo*
- [ ] CHECKPOINT 4A-1 DONE - *todo*

### Phase 5: Wire Tool, Step 4A-2 (branch `wire-redesign`)
- [ ] 5.1 Wire drawing tool re-enabled (live preview, 10 px snap, `JunctionRef`, `FreeEnd`, wire-on-wire notice) - *todo*
- [ ] 5.2 Rejections (same terminal, duplicate wire, zero-length wire) - *todo*
- [ ] 5.3 Editing wire ends (Acceptance S3: handle, detach, reattach/free-end, 1 undo step) - *todo*
- [ ] 5.4 Synthetic mouse tests (`QTest`, shared `qapp`) - *todo*
- [ ] 5.5 Performance benchmark (`route()` + 50-part drag step <= ~30 ms, configurable threshold test) - *todo*

### Phase 6: Documentation & Report (branch `wire-redesign`)
- [ ] 6.1 Update `PROGRESS.md` (built, rewritten tests, next tasks S4/S5) and `README.md` if usage changed - *todo*

## Current Status: Milestone 2 & Milestone 3 Step 3A Complete, Phase 1 Quick Wins Tasks 1-10 Done, Startup & Shutdown Fixes Done, LED Lifecycle Complete, Paint Safety & Crash Handler Hardening Complete, Meter Loading & Ideal Modes Complete (289 Passing Tests)

## Stray Background Under LED, Problems Panel Close Button & Meter Loading (Items 1–3)
- **Item 1: Stray Background Under the LED**:
  - *Root Cause*: In `ComponentItem._paint_impl()`, components with `show_value=True` but empty formatted value text (like an LED when simulation is stopped) evaluated `QFontMetrics.boundingRect(val_rect.toRect(), text_align, "")` to a 0-width rectangle located 25–43 px below the component origin. Calling `.adjusted(-3, -1, 3, 1)` expanded that zero-width bounding box into an 84-pixel rectangle `QRect(-3, 27, 6, 14)` which was painted with `painter.fillRect(val_box, palette.canvas_bg)` onto transparent scene space ~20 px below the LED.
  - *Fix*: Guarded value/label plate painting to require non-empty text after stripping, and tightened `boundingRect()` to hug the visual symbol within 2 px.
- **Item 2: Problems Panel Close Button & Glyph Fixes**:
  - Replaced native Windows "Segoe UI" U+2715 (`✕`) glyphs—which rendered as empty tofu boxes ($\square$) on Windows—with crisp vector cross rendering in both `ProblemsCloseButton.paintEvent` and `make_severity_icon("error")`.
  - Added accessible close button with focus outline, Space/Enter keyboard activation, and tooltip `"Close Problems panel (F8)"`.
- **Item 3: Meter Loading (Visible and Optional, Engine Defaults Unchanged)**:
  - *Ideal & Realistic Meter Modes*: Added `is_ideal: bool` to `Voltmeter` and `Ammeter`. Ideal voltmeters draw 0 A (infinite input resistance) without generating false floating-node warnings. Ideal ammeters model a 0 V branch constraint with 0 V drop.
  - *Dialog Presets*: Added input resistance presets to `QuickValueDialog` for Voltmeter (`Ideal`, `10 Mohm (typical multimeter)`, `1 Mohm`, `Custom`) and series resistance presets for Ammeter (`Ideal (0 V branch)`, `1 mohm`, `Custom`). Presets update live during simulation and support full undo/redo.
  - *Edit > Preferences*: Added `"New meters are: Ideal / Realistic"` setting defaulting to `"Ideal"` for newly placed palette meters, while engine constructors (`Voltmeter(...)`, `Ammeter(...)`) retain realistic defaults ($10\text{ M}\Omega$, $1\text{ m}\Omega$) so existing tests and bundled examples are unaffected.
  - *Voltmeter Loading Warnings*: Added network Thévenin resistance computation to evaluate voltmeter loading. When loading changes the measured voltage by $\ge 0.1\%$, the hover tooltip and editor dialog display: `"VM1 draws 30 uA from the 10 kohm resistor; the reading is 0.1% lower than the unloaded voltage."`
  - *Educational Notes*: Added dedicated educational section in `LEARNING_NOTES.md` with hand-calculated analysis (30 mA source into 10 kΩ giving 299.70 V vs 300 V, 30 A source current divider giving 29.97 A vs 30 A, GMIN shunt analysis at high voltages) and 3 student exercises with complete step-by-step solutions.


## Theme Palette Completeness, Crash Handler Protection & Paint Safety (Items 1–7)
- **Item 1: Reproduction Test**:
  - Added offscreen Qt reproduction test (`test_reproduce_led_paint_palette_attribute_error`) verifying that selecting and hovering an LED on canvas in dark and light themes exercises terminal tags and captures the missing `symbol_label` attribute error in both themes.
- **Item 2: ThemePalette Completeness**:
  - Added missing `symbol_label` color token to `ThemePalette` definition (`#8B949E` in `DARK_PALETTE`, `#57606A` in `LIGHT_PALETTE`).
  - Added AST-based static/dynamic test `test_every_palette_attribute_in_code_exists_in_both_themes` guaranteeing that all color tokens accessed on `palette` across the codebase exist in both dark and light palettes.
- **Item 3: Exhaustive Smoke Test**:
  - Smoke test (`test_smoke_render_every_palette_entry_all_orientations_states_and_themes`) covering all 12 palette entries across all 8 orientations, selected/unselected, hovered/unhovered, running/stopped (with all 6 LED states: off, dim, on, over, burned, reverse) across both dark and light themes (1,792 permutations in ~2.3s) with 0 exceptions reaching the exception hook.
- **Item 4: Crash Handler Loop Prevention & Modal Safety**:
  - Signature-based error deduplication `(exception_type, message, top_frame)` with 60-second throttling window.
  - Re-entrancy guard preventing duplicate or nested modal dialogs.
  - Deferred dialog execution via `QTimer.singleShot(0, ...)` ensuring errors in `paint()` never open modal event loops during a paint traversal.
  - Added "Quit" button to error dialog and report repeat counts (`Occurrences: N`).
- **Item 5: Paint Safety Fallback**:
  - Wrapped `ComponentItem.paint()`, `WireItem.paint()`, `JunctionItem.paint()`, and `CircuitScene.drawForeground()` in safety guards.
  - Caught drawing exceptions are logged once per item and replaced with a red dashed bounding rectangle with a bold "!" indicator.
  - Guarantees nothing ever propagates out of a virtual `paint()` override to cause C++ Shiboken aborts or paint loops.
- **Item 6: File Storage Location & Directory Naming Investigation**:
  - *Report*: Settings, recent files, and `crash.log` are stored under `get_default_data_dir()`. On Windows, this resolves to `C:\Users\emeri\AppData\Roaming\python` (`settings.json` and `crash.log`).
  - *Why the folder is named "python"*: `QStandardPaths.writableLocation(AppDataLocation)` checks `QCoreApplication.applicationName()`. Because neither `QCoreApplication.setApplicationName("CircuitSim")` nor `QCoreApplication.setOrganizationName("Ohmbench")` is set during initialization in `main.py`, Qt falls back to the running binary name `sys.executable` (`python.exe` -> `"python"`). No working code was modified; the upcoming rename task will set the organization and application names.

## LED Component & Problems Panel (Items 1–6)
- **Item 1: LED Symbol and Palette**:
  - Added new palette category **Semiconductors** with **LED** (`80 x 40 px`, terminals `anode` at `(0, 20)` and `cathode` at `(80, 20)`).
  - Designed IEC 60617 LED symbol with distinct cathode flat cut on the case outline (Variant A: flat vertical cut on cathode rim, clear across all 8 orientations).
  - Pure-Python geometric marks in `led_marks()` with verified cathode-flat proximity tests.
  - Preview image generated and committed at `docs/design/led_variants.png`.
- **Item 2: Colour Selection & Datasheet Forward Voltages**:
  - Integrated LED color selector into `QuickValueDialog` with 7 real-world presets + Custom: Red (2.0 V), Orange (2.0 V), Yellow (2.1 V), Green (2.2 V), Pure green (3.0 V), Blue (3.2 V), White (3.2 V).
  - Swatch icons rendered beside each colour choice in the combo box.
  - Informative datasheet label ("typical datasheet values; real LEDs vary by about +-0.3 V") that auto-switches to "Custom" on manual voltage edits.
  - Configurable `rated_current` (default 20 mA), `max_current` (default 30 mA), and optional `burnout_enabled` / `burnout_current` checkbox and threshold.
  - Full undo/redo support and `.circ` document serialization.
- **Item 3: LED Drawing & Perceptual Glow**:
  - Live brightness follows perceptual human-eye response: $I_{\text{vis}} = \sqrt{I / I_{\text{rated}}}$.
  - Realistic sharp sub-threshold cutoff below $10\,\mu\text{A}$ (off).
  - Over-current warning badge: amber exclamation mark badge rendered when $I > I_{\text{max}}$.
  - Burnout rendering: darkened case body with distinct cross when burned out ($I > I_{\text{burnout}}$).
  - Diagnostic outline coloring: amber box for warnings (reversed, over-current, missing resistor) and red box for fatal errors.
  - Live tooltip shows Name, Colour, Voltage, Current, and State (`Off`, `On`, `Over-current`, `Burned out`, `Reverse-biased`).
- **Item 4: Problems Panel (`View > Problems` / `F8`)**:
  - Bottom panel dock with fixed 120 px initial height, 'X' close button, and `F8` shortcut.
  - Diagnostics restructured into clear 3-part format: What happened, Why it happened, and How to fix it (referencing component names and numbers).
  - Tree columns: Severity (icon + "Error"/"Warning"), Message, Components affected.
  - Clicking a problem selects and centers the affected component on the canvas.
  - Status bar shows short problem count ("2 problems") with clickable action.
  - Auto-opens on simulation errors unless closed by the user during the current run.
  - Strict canvas invariance guaranteed (`NoAnchor` view prevents zoom or pan shift on panel open/close).
- **Item 5: Bundled LED Examples**:
  - `File > Examples > LED with a resistor`: 5 V DC source, 150 Ω resistor, Red LED (calculating $I = 20\text{ mA}$).
  - `File > Examples > LED colours`: 12 V rail powering 7 parallel branches showcasing all standard LED colours with calculated current-limiting resistors.
- **Item 6: Integration Tests & Documentation**:
  - Offscreen Qt integration test suite with timeout verifying palette placement, snapping, properties editing with undo/redo, reversed/no-resistor diagnostics, problems panel interaction, all 8 orientations, and `.circ` save/load round-tripping.

## Startup & Shutdown Bug Fixes (Items 1–6)
- **Bug (a) Empty Start Canvas**:
  - *Origin*: In `src/circuitsim/main.py` lines 106–111 inside `run_gui()`, hardcoded placement calls (`scene.place_new_component(...)`) created a 5-component demo circuit (`dc_voltage`, `switch`, `resistor`, `lightbulb`, `ground`) on every launch.
  - *Commit Origin*: Commit `06c2d72` ("Milestone 2 Step 2A: main window, IEC symbol loader/preview, palette, and schematic canvas").
  - *Root Cause*: Placing components via `place_new_component` pushed commands onto `scene.undo_stack`, making `undo_stack.isClean() == False`, marking the document modified with an asterisk (`*`) in the title bar, and triggering the "save changes?" prompt whenever the user closed a fresh app without touching anything.
  - *Fix*: Removed the hardcoded startup placement in `src/circuitsim/main.py`. Canvas now starts completely empty, undo stack is clean, title has no asterisk, and closing immediately exits without prompting.
  - *Test Impact*: 0 existing tests depended on startup components (all existing tests construct their own isolated circuits). Added new offscreen Qt test `test_fresh_window_starts_empty_and_clean_with_no_close_prompt` in `tests/test_circ_io.py`.

- **Bug (b) Shutdown Exception (libshiboken C++ object already deleted)**:
  - *Origin & Cause*: In `MainWindow.__init__`, `self.circuit_scene.undo_stack.cleanChanged` was connected to `lambda _clean: self._update_window_title()`. When closing the application after selecting "Discard", Qt destroys child objects during teardown. When `CircuitScene` destroys its child `QUndoStack`, the C++ destructor `QUndoStack::~QUndoStack()` cleans uncommitted commands, emitting `cleanChanged(bool)`. The connected slot invoked `self._update_window_title()` -> `has_unsaved_changes()` -> `self.circuit_scene.undo_stack.isClean()`. Because the underlying C++ `QUndoStack` was already partially destroyed, Shiboken raised `RuntimeError: libshiboken: Internal C++ object (PySide6.QtGui.QUndoStack) already deleted.`. The global unhandled exception hook (`crash_handler._excepthook`) then displayed a modal critical error dialog during application exit.
  - *Fix*:
    1. Reordered shutdown sequence in `MainWindow.closeEvent`: prompt for unsaved changes first; if cancelled, ignore event; if discarded/saved, set `self._is_closing = True`.
    2. Stop and wait for the background simulation worker thread (`self.sim_controller.shutdown()`).
    3. Explicitly disconnect `self.circuit_scene.undo_stack.cleanChanged` and worker signals before widget teardown.
    4. Guard `_update_window_title()` and `has_unsaved_changes()` with `if self._is_closing: return`.
    5. Set `set_shutting_down(True)` in `crash_handler` to suppress modal `QMessageBox` popups during shutdown while still logging any shutdown exceptions to `crash.log` and stderr.
  - *Tests*: Added `test_window_shutdown_cleanliness_all_cases` (verifying all 8 shutdown scenarios: discard, save, cancel, clean start, running simulation, loaded file, new with discard, rapid double close) and `test_quiet_shutdown_error_logging_without_dialog`.

### What Is Done
- **Environment, Licensing & Editable Package Installation**:
  - Local Python 3.12 virtual environment (`.venv`) with `PySide6`, `numpy`, `scipy`, and `pytest`.
  - Project is installed in editable mode (`pip install -e .`) and includes an MIT [`LICENSE`](LICENSE) and updated [`README.md`](README.md).
- **Milestone 1 — Core Physics & MNA Engine (`src/circuitsim/components/`, `src/circuitsim/engine/`, `src/circuitsim/dialogs/value_parser.py`)**:
  - Engineering-notation parser (`parse_spice_value`, `format_engineering_value`).
  - All 11 Milestone 1 & 2 components (`Ground`, `Resistor`, `Capacitor`, `Inductor`, `DCVoltageSource`, `DCCurrentSource`, `ACVoltageSource`, `Switch` with $350\text{ V}$ contact breakdown arc clamp, `Lightbulb`, `Voltmeter`, `Ammeter`).
  - DC and Transient MNA solver (`Circuit`, `MNASolver`) with topology validation, `thevenin_resistance`, Backward Euler switching/arc settling, and Trapezoidal integration.
- **Milestone 2 — Step 2A: Main Window, IEC Symbol System, Palette & Schematic Canvas**:
  - 11 IEC symbol JSON metadata files (`src/circuitsim/resources/symbols/iec/`), pure-Python symbol geometry & tolerant SVG loader (`src/circuitsim/canvas/symbol_geometry.py`), hybrid SVG/procedural IEC renderer (`symbol_renderer.py`), symbol preview tool (`tools/symbol_preview.py`), and dockable `MainWindow`.
- **Milestone 2 — Step 2B: Connectivity Engine, Orthogonal Wiring, Full Undo/Redo & Usability**:
  - **Pure-Python Connectivity & Netlist Extractor (`src/circuitsim/canvas/connectivity.py`, zero Qt imports)**:
    - Union-Find netlist extractor (`extract_connectivity`, `CircuitScene.build_circuit()`) enforcing exact schematic connectivity rules (wire endpoints on terminals, crossing wires do not connect without a T-junction or explicit junction dot, isolated junction dots not on any wire are ignored and never create nets or false warnings, attached wire deletion/re-routing, zero-length/duplicate/collinear wire normalization).
  - **Interactive Orthogonal Wiring & Full `QUndoStack` Editing (`src/circuitsim/canvas/wire_item.py`, `commands.py`, `scene.py`, `view.py`)**:
    - Rubber-band selection, group move, Rotate 90° CW (`R`), Flip Horizontal (`F`), Delete (`Del`/`Backspace`), Cut/Copy/Paste, and full `QUndoStack` Undo/Redo (`Ctrl+Z`/`Ctrl+Y`) including parameter edits.
- **Milestone 2 — Step 2C & Post-2C Polish: Live Simulation Worker, Canvas Readouts, Interactive Switch, Bulb Glow, Problem Highlighting & Usability Fixes**:
  - **Pure-Python Simulation Session & Process-Ready Protocol (`src/circuitsim/engine/simulation_session.py`, zero Qt imports)**:
    - `SimulationSession` and `SimulationBackendProtocol` handle schematic-to-solver execution (`start`, `pause`, `stop`, `step_chunk`, `toggle_switch`, `update_component_parameter`), transport-control state mapping (`compute_transport_controls_state`), and emit immutable, picklable `SimulationFrame`, `ComponentTelemetry`, and `ProblemDiagnostic` dataclasses.
  - **Background `QThread` Worker (`src/circuitsim/app/sim_worker.py`)**:
    - `SimulationWorkerController` runs `_SessionThreadWorker` on a dedicated background `QThread` communicating strictly via queued Qt signals so the main GUI thread never freezes during simulation, and stops cleanly when `MainWindow` closes.
  - **Value Input, Live Editing, Undo/Redo, Transport States, Unconnected Parts & Selection Outline**:
    - **Value Parser (`value_parser.py` & `quick_edit_dialog.py`)**: Accepts single decimal comma (`"5,65 G"`), spaces before prefix (`"4.7 k"`), uppercase `"K"` as kilo (`"10K"`), shows live parsed preview (`= 5.65 GΩ`) beneath each input field, and displays clear plain-language error messages.
    - **Live Editing & Undo/Redo**: Double-clicking any component opens `QuickValueDialog` with a note that changes apply immediately while running (`t = 0` note on capacitor initial voltage), and pushes an undoable `EditComponentParametersCommand` (`Ctrl+Z` / `Ctrl+Y`) that updates the component model, canvas label, and live simulation both when stopped and when running.
    - **Run / Pause / Stop Visual States**: Distinct green active Run, amber active Pause (`▶ Resume`), red Error outline, and left-hand status bar indicator (`● Running`, `❚❚ Paused`, `■ Stopped`) across Dark and Light themes.
    - **Unconnected Parts & Ground Hint**: Components with no wires attached are dimmed (`opacity = 0.45`) and ignored with an amber warning (`"B1 is not connected and is ignored"`) so the rest of the circuit runs; connected islands with no path to ground still raise a floating-node error; missing ground reports `"No ground connected — Add a Ground part and wire it to the circuit"`.
    - **Selection Outline**: Component selection and diagnostic boxes stay strictly clear of upright name (`R1`) and value (`1 kΩ`) labels across all rotations (`0°`, `90°`, `180°`, `270°`).

- **Milestone 3 - Step 3A: Save / Load `.circ` Files (done)**:
  - [`src/circuitsim/io/circ_serializer.py`](src/circuitsim/io/circ_serializer.py) (no Qt): versioned JSON (`"format": "circuitsim"`, `"schema_version": 1`) storing components (type, name, label, show_value, position, rotation, flip, parameters, extra settings), wires, junction dots and view state (theme, zoom, pan, simulation speed). Strict validation with plain-language `CircuitFileError` messages (empty, truncated, wrong format, newer version, bad values).
  - Atomic save (temp file in the same folder, flush to disk, then `os.replace`) with one backup `name.circ.bak`.
  - `CircuitScene.load_document` builds everything first and swaps only if it all worked; `CircuitScene.to_document` snapshots the schematic. Loading clears the undo stack.
  - File > New / Open / Save / Save As (`Ctrl+N`, `Ctrl+O`, `Ctrl+S`, `Ctrl+Shift+S`), toolbar New/Open/Save, title shows `name.circ*` for unsaved changes, prompts before New / Open / closing.
  - New Qt-free [`components/factory.py`](src/circuitsim/components/factory.py) (the "make a default component" function moved out of the canvas so the loader can use it).

- **Milestone 3 — Design Overrides & Refinements (Items 1–4)**:
  - **Item 1: Saved Parts Bar Removed (Step 3B Cancelled)**: The 10-slot saved parts toolbar, placeholder buttons, shortcuts and package have been completely removed. Digit keys are no longer reserved for saved parts. (Design decision overrides specification and AGENT_INSTRUCTIONS.md; noted in SUGGESTIONS.md for future redesign if requested).
  - **Item 2: No Fake Oscilloscope**: The empty "Oscilloscope (4-Channel)" dock widget and unused placeholder actions/menus have been removed. Window layout restoration (`restoreState`) guarantees stale saved states cannot bring the dock back. The `circuitsim/scope/` package structure remains preserved for Milestone 4.
  - **Item 3: Lowest Free Number for Component Names**: New and pasted components now consistently receive the lowest unused number for their prefix (`R`, `C`, `L`, `V`, `VM`, `A`, `B`, `SW`, `GND`, etc.). Deleting a part frees its number for the next part added; undoing restores original names; names stay unique at all times; save/load round-trips preserve names.
  - **Item 4: Small Visual Fixes**: The internal letter in Voltmeter (`V`) and Ammeter (`A`) symbols stays upright across all rotations (`0°`, `90°`, `180°`, `270°`) and horizontal flip (`F`). Components are placed above wires (`Z = 20.0` vs `5.0`), and value readouts (e.g. `"11.11 mA"`) and name labels include a canvas background plate so wires never cut through or obscure the text.

- **Quality & Reliability Fixes (Items A–E)**:
  - **Item A (Polarity Regressions & Transform Chain)**: Added 40 pure-Python regression tests in `tests/test_polarity.py` covering all 8 orientations (`rot` in `{0, 90, 180, 270}`, `flip` in `{False, True}`) for DC Voltage Source, DC Current Source, Voltmeter, Ammeter, and Two-source series chain. Unified `SymbolLibrary._paint_procedural_iec` transform order (`scale(-1, 1)` then `rotate(rot)`) with `transform_terminal_position` so drawing and netlist extraction use identical geometry.
  - **Item B (Hit Areas & Bounding Rectangles)**: Implemented exact `shape()` on `ComponentItem` with `QPainterPath` (using `WindingFill`) matching rotated/flipped symbol body and 6 px terminal clearance. Tightened `boundingRect()`. Excluded label plates from mouse clicks so wires behind labels remain selectable. Bound `prepareGeometryChange()` to `rotation_deg` and `flipped_h` setters. Verified via `tests/test_hitboxes.py`.
  - **Item C (Wire Re-routing & Detour on Rotate/Move)**: Implemented collision-avoidance routing in `_route_wire_avoiding_body` in `src/circuitsim/canvas/connectivity.py`. Direct routes that intersect the component body are diverted via orthogonal 40 px clear bypass paths (terminal `a` on negative side, `b` on positive side), preventing tangled overlapping shorts. Added 8 regression tests in `tests/test_rotation_and_moving_wires.py` verifying full 360° cycles, dragging, group rotation, voltage preservation, and undo/redo.
  - **Item D (Wire Terminal Snapping)**: Added `TERMINAL_SNAP_RADIUS_PX = 10.0` (half grid cell) snapping in `add_wire`, hovering terminal indicator, and nearest terminal selection. Tested in `tests/test_wire_snapping.py` across 0, 1, 5, 8, 9 px (connects) and 11 px (stays off).
  - **Item E (Save / Load Round-Trip Preservation)**: Added `test_save_load_rotated_flipped_circuit_preserves_wires_polarity_and_voltages` in `tests/test_circ_io.py`. Verified that saving and reloading circuits with rotated and flipped parts preserves exact wire connections, terminal polarities, and simulation voltages.

- **Item F (Test Suite Speed Analysis)**:
  - **Profile (`pytest --durations=10`)**: 180 passed in ~43.5 s. The top 10 slowest tests account for ~23 s (~53% of total time), with the slowest being UI tests in `tests/test_simulation_session_and_step2c.py` (2.7s–3.0s each), `test_hitboxes.py` (1.95s), and `test_circ_io.py` window tests (1.85s).
  - **Root Cause**: Tests involving Qt widgets are executed in isolated subprocesses (`_run_qt` via `sys.executable -c`) to enforce the strict architectural rule that pure-Python physics, connectivity, and serializer modules have zero Qt imports in `sys.modules`. On Windows, each subprocess invocation incurs Python startup and dynamic loading of large PySide6 DLLs (~1.5–2.5 s per process). By contrast, all 130+ pure-Python unit tests complete in under 2 seconds combined (<0.02 s each).
  - **Optimization Assessment**: Running Qt tests in-process would reduce test suite duration to <10 s, but would contaminate `sys.modules` and weaken the isolation tests that prove physics and IO code remain Qt-free. The current architecture should be left alone because 43 s is fast enough for CI/local verification while providing absolute architectural guarantees.

- **Recent Quality & Usability Tasks**:
  - **Item 1 (Commit List for Items A–E and Docs)**:
    - `eee01f6`: `Item A: Fix painter transform order to match symbol terminal geometry and add polarity regression tests`
    - `9368dd9`: `Item B: Implement precision shape and tight boundingRect matching rotated symbols, ensuring label plates do not intercept clicks`
    - `95efe4f`: `Item C: Safe orthogonal wire re-routing avoiding component body penetration and tangle shorts on rotation and dragging`
    - `36b90ea`: `Item D: Precise 10 px wire terminal snapping, hover highlighting, and connection guarantees`
    - `c5f6fcc`: `Item E: Verify save and load round-trip on rotated and flipped circuits preserves wire connections, polarity, and simulation voltages`
    - `f86a89e`: `Item E: Unify symbol rendering and terminal coordinate transforms with save/load regression tests` (Item E shared two commits)
    - `f3539df`: `Item F and G: Document test suite speed profiling analysis and explicit wiring architecture plan` (Docs for F and G shared commit f3539df)
  - **Item 2 (Canvas View & Dock Stability on Selection / Clicks)**:
    - *Root Cause*: Dock width dynamically followed `info_label.sizeHint()` across selection changes (`DEFAULT_SHORTCUTS_HELP_TEXT` vs component text), resizing the viewport. Combined with `AnchorViewCenter`, this shifted the scene under the cursor by up to 58 px and triggered unintended 20 px grid-snap dragging on click.
    - *Fix*: Locked `info_dock` to fixed width (280 px), wrapped contents inside `QScrollArea`, set `info_label` size policy to `Ignored` horizontally with `wordWrap=True`, locked `palette_dock` (240 px) and `statusBar` (height 26 px, grip disabled), switched `CircuitView` to `NoAnchor`, and introduced a 4 px drag threshold suppressing mouse move jitter on clicks. Verified via `tests/test_view_stability.py`.
  - **Item 3 (Unified Drawing & Netlist Polarity via `polarity_mark_positions`)**:
    - Implemented pure-Python `polarity_mark_positions(part_type, rotation_deg, flipped_h, center_px)` in `symbol_geometry.py` using `transform_terminal_position` as the single geometric source of truth.
    - Updated `symbol_renderer.py` to paint `+`, `-`, current arrow and meter polarity in upright coordinates directly from this function with optional `polarity_color`.
    - Added `tests/test_drawing_polarity.py` (8 pure-Python hand-worked tests + offscreen Qt test asserting `+` mark pixel centroid in rendered `QImage` is nearer `pos` than `neg` across all 8 orientations).
  - **Item 4 (Revised Plan: Attachment-Based Wires & Junctions — Plan Only, No Code)**:
    ```text
    1. Data Model: Wire has two ends. Each end is an Attachment: TerminalRef(comp_name, term_name), JunctionRef(junction_id), or FreeEnd(x, y). Junction has id and pos; created only explicitly (placed by user or splitting a wire when ending on it).
    2. Electrical Connectivity: Pure Union-Find over TerminalRefs and JunctionRefs connected through Wires (circuitsim.wiring.connectivity). Coordinates play zero part; crossing/overlapping wires never connect; moving components/junctions never alters connectivity.
    3. Route Generation: Pure function route(start_pos, end_pos, obstacles) -> tuple[PointPx, ...] (no Qt, deterministic, stable while dragging); replaces the 40 px detour heuristic. Waypoint drags stored as optional routing hints only.
    4. Visual Projection: JunctionItem drawn as dot only when degree >= 3; merges into a bend when degree drops to 2. JunctionItems are selectable and draggable, with attached wires following live. FreeEnd drawn with hollow marker; snap radius attaches to terminal.
    5. Schema v2 & Migration: Schema v2 stores explicit attachments and junction list. V1 loader runs legacy geometric extraction once to compute connectivity, generates attachments, and upgrades seamlessly; verified with identical simulation voltages.
    6. Tests Affected: test_connectivity_and_editing.py adapts from raw coordinate arrays to Wire(start_ref, end_ref); crossing-wire and collinear tests become structural assertions. V1 tests in test_circ_io.py verify migration.
    7. Replaces from C & D: Replaces _route_cuts_box detour heuristic and geometric wire endpoint mutation on move (Item C); adapts 10 px snap (Item D) to bind FreeEnd to TerminalRef.
    8. Stepped Commits & Size:
       - Step 1 (Medium): Pure-Python wiring model (TerminalRef, JunctionRef, FreeEnd, Wire, Junction, Union-Find netlist builder) with graph unit tests.
       - Step 2 (Medium): Pure-Python route(start, end, obstacles) orthogonal pathfinder replacing detour heuristic.
       - Step 3 (Small): File format schema v2 serializer and v1 migration runner with voltage-equivalence tests.
       - Step 4 (Large): Canvas integration (WireItem, JunctionItem, split-on-drop, degree-2 merge, free-end hollow markers, drag-move tracking).
    9. Risks:
       - Interactive drag oscillation/hunting between symmetrical routes. Mitigation: Route caching with H-first/V-first orientation latching.
       - V1 migration edge cases with unattached floating wire clusters. Mitigation: Cluster grouping via legacy Union-Find before attachment synthesis.
    ```

- **Explicit Wiring Redesign (Steps 0 to 4 Done)**:
  - **Item 0: Single Source of Truth for Terminals & Drag vs. Jitter**:
    - Added comprehensive regression tests in [`tests/test_terminal_source_of_truth_and_drag.py`](tests/test_terminal_source_of_truth_and_drag.py).
    - Verified all 88 combinations (11 components $\times$ 4 rotations $\times$ 2 flips) prove that `item.terminal_scene_positions()`, `spec.resolve_terminals_px()`, `shape().contains()`, terminal snapping, and rendered terminal dot pixels from `item.paint()` all take their coordinates strictly from `transform_terminal_position`.
    - Tested that deliberate 40 px drag moves a part by 2 grid cells (+40 px) and creates an undo command, while 3 px mouse jitter moves by 0 px and creates zero undo commands.
  - **Item 1: Pure-Python Wiring Model & Union-Find Netlist Builder (`src/circuitsim/wiring/`)**:
    - Built [`src/circuitsim/wiring/model.py`](src/circuitsim/wiring/model.py) with zero Qt imports: `TerminalRef(component, terminal)`, `JunctionRef(id)`, `FreeEnd(x, y)`, `Wire(id, end_a, end_b, hints)`, `Junction(id, pos)`, and `WireGraph`.
    - `WireGraph` is an immutable frozen dataclass; every operation (`add_wire`, `remove_wire`, `add_junction`, `split_wire_at`, `remove_junction`, `remove_component`) returns a new graph.
    - Automatic cascading merge rules: degree 2 junction merges 2 wires into 1 (storing junction pos in hints); degree 1 junction converts wire end to `FreeEnd`; degree 0 junction is deleted; duplicate wires are deduplicated.
    - Built [`src/circuitsim/wiring/netlist.py`](src/circuitsim/wiring/netlist.py): Union-Find over explicit attachments producing solver-ready `Circuit` with deterministic node names ("0", "N1", ...).
    - Added 20 unit and equivalence tests in [`tests/test_wiring_model_and_netlist.py`](tests/test_wiring_model_and_netlist.py) verifying immutability, merge rules, crossing wires remaining separate, 200 random operations maintaining validity, diagnostics (`NoGroundError`, `FloatingNodeError`, `VoltageSourceLoopError`), and exact voltage divider, RC, 12V+12V, and switch-bulb equivalence against analytic calculations.
  - **Item 2: Pure-Python Orthogonal Wire Router with Latching (`src/circuitsim/wiring/router.py`)**:
    - Built `route(start, end, start_dir, end_dir, obstacles, previous=None)` with zero Qt imports.
    - Enforces orthogonal paths, outward departure in `start_dir`, inward arrival in `-end_dir`, obstacle collision avoidance (inflated bounding boxes, exempting attached terminals), deterministic <= 2 bend candidates, minimal-bend A* grid search fallback, and orientation latching from `previous` routes.
    - Added 10 unit tests in [`tests/test_wiring_router.py`](tests/test_wiring_router.py) covering straight, L-shape, Z-shape, facing/opposed terminals, obstacle avoidance, collinear simplification, and latching.
  - **Item 3: Schema v2 File Format & v1-to-v2 Migration (`src/circuitsim/wiring/serializer.py`)**:
    - Defined Schema v2 storing explicit attachments (`terminal`, `junction`, `free`), explicit junctions, and view state.
    - Implemented `migrate_v1_to_v2` running geometric extraction once, slicing wires at internal vertices and segments, preserving separation of crossing wires without dots, and cleaning stray dots.
    - Added 9 unit tests in [`tests/test_wiring_v2_migration.py`](tests/test_wiring_v2_migration.py) verifying voltage divider, RC circuit, 12V+12V chain, rotated/flipped parts, crossing wire separation, v2 save/load round-tripping, and error handling.
  - **Item 4: Small Usability & Geometry Fixes**:
    - Switch toggle marks file modified: Clicking a switch on the canvas marks the document modified (`has_unsaved_changes() = True`, window title asterisk `*`), but does NOT push to `QUndoStack` (not undoable). Saving clears the modified state.
    - Selection outline clearance: Adjusted Ground label positioning below the earth bars (`label_offset[1] >= 0`), providing 30 px clearance and ensuring Voltage Source selection outline never touches `GND2` label.
    - Added offscreen Qt tests in [`tests/test_switch_dirty_and_ground_label_clearance.py`](tests/test_switch_dirty_and_ground_label_clearance.py).

## STEP 4 REQUIREMENTS (not built yet)

Everything Step 4 needs to do to integrate the wire redesign with the schematic canvas:

1. **Canvas `WireGraph` Integration**:
   - Replace raw `_wire_items` list and `_explicit_junctions` coordinate set in `CircuitScene` with `WireGraph` as the single source of truth for all schematic connections.
   - Replace coordinate-coincidence netlist extraction in `CircuitScene.build_circuit()` with `build_circuit(self.wire_graph, [item.component for item in self.placed_items])`.

2. **Visual `WireItem` and `JunctionItem`**:
   - Update `WireItem` to store a `Wire` reference (`id`, `end_a`, `end_b`, `hints`).
   - Dynamically compute polyline points from `route(start_pos, end_pos, start_dir, end_dir, obstacles, previous=self.points)`.
   - Implement `JunctionItem` representing a `Junction` object:
     - Drawn as a solid dot only when degree $\ge 3$.
     - When degree drops to 2 (e.g. wire removed), automatically merges into a simple bend (stored as a hint in the combined wire) and the dot disappears.
     - `JunctionItem` is selectable, draggable, and deletable.
   - Draw `FreeEnd` attachments with a distinct hollow circular marker indicating an open-circuit wire end.

3. **Interactive Wiring & Terminal Snapping**:
   - When drawing a wire, hovering within `TERMINAL_SNAP_RADIUS_PX = 10 px` of a terminal snaps to that terminal; releasing binds that end as a `TerminalRef(comp_name, term_name)`.
   - Releasing a wire endpoint onto the interior of an existing wire automatically calls `graph.split_wire_at()`, creating a `Junction` and binding the new wire end to `JunctionRef(jid)`.
   - Releasing a wire in empty space creates a `FreeEnd(x, y)`.
   - Dragging a `FreeEnd` onto a terminal converts it to a `TerminalRef`.

4. **Component Dragging & Wire Tracking**:
   - When one or more components are moved, rotated (`R`), or flipped (`F`), attached wire endpoints follow their terminals automatically.
   - Update wire routes live using `route(...)` with orientation latching, preserving user-created waypoints where applicable.
   - Completely remove the legacy 40 px detour heuristic (`_route_wire_avoiding_body`) and coordinate-based endpoint mutation.

5. **`QUndoStack` Editing Commands with Immutability**:
   - Because `WireGraph` is immutable, each wire editing command (`AddWireCommand`, `RemoveWireCommand`, `MoveComponentCommand`, `SplitWireCommand`, `DeleteSelectionCommand`) simply stores the `old_graph` and `new_graph` instances, making undo and redo trivial and 100% reliable.

6. **Schema v2 Canvas Save / Load**:
   - Update `CircuitScene.to_document()` to output `CircuitDocumentV2` and `CircuitScene.load_document()` to accept `CircuitDocumentV2` (auto-migrating legacy v1 files on load).

### What Is Next (Milestone 3)
- **Step 4** (Canvas Integration of Explicit Wiring Model).
- **Step 3C** (Full properties dialog) follows Step 4. Step 3A is done, and Step 3B is cancelled by design decision.

## FLASH QUEUE

### Phase 1: Quick Wins
- [x] Task 1: Housekeeping (`.gitignore` `*.circ.bak`, `*.corrupt`; switch breakdown voltage contact arc hint; deterministic label collision avoidance) - *done (commit d67da36)*
- [x] Task 2: Recent Files (`File > Open Recent`, 8 items, injected path, atomic persistence, missing file handling, Clear List) - *done (commit 1710f48)*
- [x] Task 3: Example Circuits (`File > Examples` with 5 bundled circuits, package data, analytic tests) - *done (commit 7e29c9f)*
- [x] Task 4: Zoom to fit (`View > Zoom to fit` `Ctrl+0`, shortcuts `F5`/`F6`/`Shift+F5`, info panel, invariant canvas) - *done (commit fb23c5b)*
- [x] Task 5: Hover tooltips with live values (parts & terminals, stopped vs running, canvas invariance) - *done (commit 9c05b72)*
- [x] Task 6: Export schematic (`File > Export as PNG...` and `Export as SVG...`, white/theme options, tests) - *done (commit 7700a43)*
- [x] Task 7: About dialog (`Help > About`), feedback link (`Help > Report a problem / suggest a feature`), crash log exception hook - *done (commit f338754)*
- [x] Task 8: Bulb burn-out option (expose in dialog, dark+cross drawing, amber status note, open circuit) - *done (commit 47ee8e9)*
- [x] Task 9: Number format setting (`Edit > Preferences`, Auto/Dot/Comma display-only, persistence) - *done (commit 3bbc0fe)*
- [x] Task 10: CI (`.github/workflows/ci.yml`, README status badge) - *done*

### Phase 2: Step 3C Full Properties Dialog
- [ ] Step 3C: Full Properties Dialog (Identity, parameters, live readout, inductor helpers R_th, tau, 5tau, X_L, L calc) - *todo*

### Phase 3: Oscilloscope Plan
- [ ] Oscilloscope Plan (Step rate benchmarks, decoupled architecture, 3-chat split, risks; plan only, max 50 lines, await approval) - *todo*

### How to Run the App, Preview Tool, and Tests

```powershell
# Launch the CircuitSim desktop GUI
.\.venv\Scripts\python.exe -m circuitsim.main

# Open the IEC symbol & grid alignment preview tool
.\.venv\Scripts\python.exe -m circuitsim.tools.symbol_preview

# Run the headless Milestone 1 engine demo
.\.venv\Scripts\python.exe -m circuitsim.main --demo

# Run the full test suite (290 tests)
.\.venv\Scripts\python.exe -m pytest

# Run the fast test subset (excludes @pytest.mark.slow tests > 3s)
.\.venv\Scripts\python.exe -m pytest -m "not slow"
```

### Test Suite Speedup & Widget Audit (290 Tests)
- **Widget & Icon Scan**: Added `test_no_blank_buttons_or_icons_in_both_themes` in [`tests/test_problems_panel.py`](tests/test_problems_panel.py) scanning `MainWindow` buttons, `ProblemsPanel`, `make_severity_icon`, menu icons, `QuickValueDialog`, `PreferencesDialog`, and `ExportOptionsDialog` in both Dark and Light themes.
- **In-Process Shared Offscreen `QApplication` (`tests/conftest.py`)**: Replaced ~50 per-test Qt subprocess launches with one session-scoped `qapp` fixture (`QT_QPA_PLATFORM=offscreen`), per-test widget/timer/worker/`crash_handler` teardown, and a 30 s hang watchdog (`faulthandler.dump_traceback_later` + `threading.Timer`). Switched pixel-by-pixel `QImage.pixelColor()` loops to vectorized NumPy buffer checks.
- **Why Subprocesses Remain Where Used**:
  - Qt-free module import checks (`circuitsim.engine`, `circuitsim.components`, `circuitsim.canvas.connectivity`, `circuitsim.wiring`, `circuitsim.io.circ_serializer`, `circuitsim.engine.simulation_session`) run in clean subprocesses via `assert_module_has_no_qt_imports` so `PySide6` is guaranteed absent from `sys.modules`.
  - The `1024x768` toolbar `speed_combo` visibility check in `test_qt_step2c_ui_responsiveness_upright_labels_speed_dropdown_and_quick_edit` runs in a clean native-QPA subprocess because Qt's `offscreen` fallback font inflates the toolbar `sizeHint` width (~1748 px vs ~1042 px on Windows).
- **Runtime**: Full suite reduced from **150.86s** to **35.01s** (`290 passed`); fast subset `pytest -m "not slow"` runs in **23.22s** (`289 passed, 1 deselected`).
