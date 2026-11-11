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

## Current Status: Milestone 2 & Milestone 3 Step 3A Complete, Phase 1 Quick Wins Tasks 1-10 Done (244 Passing Tests)

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

# Run the full test suite (190 tests)
.\.venv\Scripts\pytest.exe
```
