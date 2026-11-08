# Project Progress — CircuitSim

## Current Status: Milestone 2 & Milestone 3 Step 3A Complete, Lettered Items A-G Done (180 Passing Tests)

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

- **Item G (Plan Only: Explicit Wires & Junctions Architecture Plan)**:
  ```text
  1. Data Model: Pure-Python NetGraph; edges are straight runs WireSegment(id, p1=(x1,y1), p2=(x2,y2)); explicit Junction(id, pos=(x,y)) for node degree >= 3. Multi-bend polylines decompose into segments.
  2. Qt-Free Logic: Core lives in circuitsim.wiring.net_graph & circuitsim.canvas.connectivity (0 Qt imports); canvas WireItem and JunctionItem are thin view projections reflecting NetGraph updates.
  3. File Format: Schema v2 stores segment list + explicit junctions; migrate_v1_to_v2() splits legacy v1 polylines, resolves T-intersections, deduplicates collinear runs, and upgrades seamlessly in-memory.
  4. Tests: Existing netlist extraction tests verify identical MNA matrices; wire drawing/moving tests adapt from polyline arrays to segment collections while preserving all coverage.
  5. Stepped Commits:
     - Commit 1 (~120 LOC): NetGraph and WireSegment pure-Python data structures with graph topology unit tests.
     - Commit 2 (~140 LOC): Schema v2 serializer, v1->v2 migration, and .circ save/load round-trip tests.
     - Commit 3 (~160 LOC): Update connectivity.py Union-Find and wire splitting to operate on NetGraph segments.
     - Commit 4 (~150 LOC): Connect canvas WireItem/JunctionItem and interactive routing tools to NetGraph.
  6. Risks & Mitigation:
     - Risk 1: Collinear overlapping segments creating micro-loops. Mitigate with 1D interval merging on orthogonal lines before graph insertion.
     - Risk 2: Dragging/rotating parts causing non-orthogonal angles. Mitigate by re-running orthogonal detour routing on move.
  ```

### What Is Next (Milestone 3)
- **Step 3C** (full properties dialog) remains. Step 3A is done, and Step 3B is cancelled by design decision.

### How to Run the App, Preview Tool, and Tests

```powershell
# Launch the CircuitSim desktop GUI
.\.venv\Scripts\python.exe -m circuitsim.main

# Open the IEC symbol & grid alignment preview tool
.\.venv\Scripts\python.exe -m circuitsim.tools.symbol_preview

# Run the headless Milestone 1 engine demo
.\.venv\Scripts\python.exe -m circuitsim.main --demo

# Run the full test suite (180 tests)
.\.venv\Scripts\pytest.exe
```
