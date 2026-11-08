# Project Progress — CircuitSim

## Current Status: Milestone 2 Complete, Milestone 3 Step 3A (Save/Load) Done

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
- **Unit Test Suite (`tests/`)**:
  - **95 passing tests** (including split analytic meter/switch/live-edit tests `6a`, value edit Undo/Redo while stopped and running `6b`, clean worker `QThread` shutdown on window close `6c`, real canvas item/wire highlight colours `6d`, and a 30-resistor ladder + RC load UI responsiveness benchmark `6e`).

- **Milestone 3 - Step 3A: Save / Load `.circ` Files (done)**:
  - [`src/circuitsim/io/circ_serializer.py`](src/circuitsim/io/circ_serializer.py) (no Qt): versioned JSON (`"format": "circuitsim"`, `"schema_version": 1`) storing components (type, name, label, show_value, position, rotation, flip, parameters, extra settings), wires, junction dots and view state (theme, zoom, pan, simulation speed). Strict validation with plain-language `CircuitFileError` messages (empty, truncated, wrong format, newer version, bad values).
  - Atomic save (temp file in the same folder, flush to disk, then `os.replace`) with one backup `name.circ.bak`.
  - `CircuitScene.load_document` builds everything first and swaps only if it all worked; `CircuitScene.to_document` snapshots the schematic. Loading clears the undo stack.
  - File > New / Open / Save / Save As (`Ctrl+N`, `Ctrl+O`, `Ctrl+S`, `Ctrl+Shift+S`), toolbar New/Open/Save, title shows `name.circ*` for unsaved changes, prompts before New / Open / closing.
  - New Qt-free [`components/factory.py`](src/circuitsim/components/factory.py) (the "make a default component" function moved out of the canvas so the loader can use it).
  - **Known limits**: clicking a switch does not mark the file as modified (not on the undo stack); only `.circ` text is saved - live meter readings and simulation time are not.
  - **123 passing tests** (24 serializer + 4 window tests added in `tests/test_circ_io.py`).

- **Milestone 3 — Design Overrides & Refinements**:
  - **Item 1: Saved Parts Bar Removed (Step 3B Cancelled)**: The 10-slot saved parts toolbar, placeholder buttons, shortcuts and package have been completely removed. Digit keys are no longer reserved for saved parts. (Design decision overrides specification and AGENT_INSTRUCTIONS.md; noted in SUGGESTIONS.md for future redesign if requested).
  - **Item 2: No Fake Oscilloscope**: The empty "Oscilloscope (4-Channel)" dock widget and unused placeholder actions/menus have been removed. Window layout restoration (`restoreState`) guarantees stale saved states cannot bring the dock back. The `circuitsim/scope/` package structure remains preserved for Milestone 4.
  - **Item 3: Lowest Free Number for Component Names**: New and pasted components now consistently receive the lowest unused number for their prefix (`R`, `C`, `L`, `V`, `VM`, `A`, `B`, `SW`, `GND`, etc.). Deleting a part frees its number for the next part added; undoing restores original names; names stay unique at all times; save/load round-trips preserve names.
  - **Item 4: Small Visual Fixes**: The internal letter in Voltmeter (`V`) and Ammeter (`A`) symbols stays upright across all rotations (`0°`, `90°`, `180°`, `270°`) and horizontal flip (`F`). Components are placed above wires (`Z = 20.0` vs `5.0`), and value readouts (e.g. `"11.11 mA"`) and name labels include a canvas background plate so wires never cut through or obscure the text.

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

# Run the full test suite (95 tests)
.\.venv\Scripts\pytest.exe
```
