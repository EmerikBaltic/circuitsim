# Project Progress — CircuitSim

## Current Status: Milestone 2 Complete (Step 2C Finished)

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
- **Milestone 2 — Step 2C: Live Simulation Worker, Canvas Readouts, Interactive Switch, Bulb Glow & Problem Highlighting**:
  - **Pure-Python Simulation Session & Process-Ready Protocol (`src/circuitsim/engine/simulation_session.py`, zero Qt imports)**:
    - `SimulationSession` and `SimulationBackendProtocol` handle schematic-to-solver execution (`start`, `pause`, `stop`, `step_chunk`, `toggle_switch`, `update_component_parameter`) and emit immutable, picklable `SimulationFrame`, `ComponentTelemetry`, and `ProblemDiagnostic` dataclasses.
  - **Background `QThread` Worker (`src/circuitsim/app/sim_worker.py`)**:
    - `SimulationWorkerController` runs `_SessionThreadWorker` on a dedicated background `QThread` communicating strictly via queued Qt signals so the main GUI thread never freezes during simulation.
  - **Live Meters, Upright Labels, Animated Switch, Lightbulb Glow & Quick Value Editing**:
    - Voltmeter and Ammeter display `"-- V"` and `"-- A"` before simulation starts and after `Stop` (never a fake `0`), and show auto-ranged live readings while running.
    - Component labels (`R1`, `V1`) and values (`1 kΩ`, `12 V`) stay upright (`0°`) and readable under any rotation (`90°`, `180°`, `270°`) or horizontal flip (`F`).
    - Clicking a `Switch` on the canvas smoothly animates its lever blade (`QVariantAnimation`) and toggles the live simulation state.
    - `Lightbulb` renders a warm radial glow proportional to dissipated power ($P / P_{\text{rated}}$) and displays an overload warning badge (`>100%!`) and status bar warning when overloaded.
    - Double-clicking any component opens `QuickValueDialog` (`src/circuitsim/dialogs/quick_edit_dialog.py`), built dynamically from `Component.get_editable_parameters()`, validated with the engineering-notation parser, and applied live while running (with Undo/Redo support).
    - Canvas and status bar highlight errors in red (`no_ground`, `floating_node`, `voltage_source_loop`, `singular_matrix`) and warnings in amber (`ammeter_in_parallel`, `inductive_kickback`, `over_bright`).
    - Compacted top toolbar button labels (`iconText`) so the `Speed` dropdown (`1x Real-Time`, `0.1x Slow`, `10x Fast`) is always visible without overflowing.
- **Unit Test Suite (`tests/`)**:
  - **79 passing tests** (56 engine/physics tests + 6 symbol/SVG loader tests + 9 connectivity/editing tests + 8 Step 2C simulation session, live editing, diagnostics, upright label, toolbar visibility, and non-freezing `QThread` UI responsiveness tests).

### What Is Next (Milestone 3)
- **Milestone 3**: Full multi-tab Properties Dialog (extending the `ComponentParameter` system), 10-slot Saved Parts bar persistence & keyboard shortcuts (`1`–`9`, `0`), and `.csim` JSON save/load/export.

### How to Run the App, Preview Tool, and Tests

```powershell
# Launch the CircuitSim desktop GUI
.\.venv\Scripts\python.exe -m circuitsim.main

# Open the IEC symbol & grid alignment preview tool
.\.venv\Scripts\python.exe -m circuitsim.tools.symbol_preview

# Run the headless Milestone 1 engine demo
.\.venv\Scripts\python.exe -m circuitsim.main --demo

# Run the full test suite (79 tests)
.\.venv\Scripts\pytest.exe
```
