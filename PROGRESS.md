# Project Progress — CircuitSim

## Current Status: Milestone 2 — Step 2B Complete

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
    - Union-Find netlist extractor (`extract_connectivity`, `CircuitScene.build_circuit()`) enforcing exact schematic connectivity rules:
      1. Wire endpoints connect to component terminals only when sitting on them (or via an explicit junction dot). Crossing wires do **not** connect unless a T-junction (wire endpoint on another wire) or an explicit junction dot is present.
      2. Deleting a component automatically deletes all wires attached to its terminals; moving, rotating, or flipping a component keeps attached wires connected and re-routes them at right angles (`reroute_wires_for_updated_terminals`).
      3. Zero-length wires are discarded; duplicate and collinear overlapping wires are unified without creating phantom connections.
  - **Interactive Orthogonal Wiring & Terminal Highlighting (`src/circuitsim/canvas/wire_item.py`, `scene.py`, `view.py`)**:
    - Hovering near any component terminal highlights it with a glowing ring and switches to a crosshair cursor.
    - Clicking and dragging (or click-to-click) from any terminal or in Wire Mode (`W`) shows a dashed live right-angle route preview and highlights the target terminal or wire snap point.
    - Pressing `J` or right-clicking toggles an explicit junction dot at any grid point or wire crossing.
  - **Full `QUndoStack` Editing (`src/circuitsim/canvas/commands.py`)**:
    - Rubber-band box selection, single and group move, Rotate 90° CW (`R`), Flip Horizontal (`F`), Delete (`Del`/`Backspace`), Cut (`Ctrl+X`), Copy (`Ctrl+C`), Paste (`Ctrl+V`), and `QUndoStack` Undo/Redo (`Ctrl+Z`/`Ctrl+Y`) for every action.
  - **Usability & Palette Improvements (`src/circuitsim/app/main_window.py`, `palette_dock.py`)**:
    - Added Rotate (`R`), Flip (`F`), Wire Tool (`W`), Junction Dot (`J`), and Delete (`Del`) to the main toolbar and right-click context menu (along with Cut, Copy, Paste).
    - When nothing is selected, the Properties / Info Panel displays the full Keyboard & Mouse Shortcuts reference; when a component is selected, it shows live resolved node names (`Node 0`, `Node N1`, ...) for each terminal.
    - Compacted palette tree rows and ordered items logically (with `Voltmeter` first under `Instruments`) so all 11 Milestone 1 & 2 components are immediately visible without hiding behind a scrollbar.
- **Unit Test Suite (`tests/`)**:
  - **71 passing tests** (56 engine/physics tests + 6 symbol/SVG loader tests + 9 connectivity, netlist extraction, analytical comparison, and `QUndoStack` editing tests).

### What Is Next (Milestone 2 — Step 2C)
- **Step 2C**: Background worker simulation loop (`QThread` behind a clean process-ready interface), Run/Pause/Stop controls, live problem highlighting on the canvas, clickable animated switch, glowing lightbulb following real dissipated power, and live voltmeter/ammeter readouts on the canvas.

### How to Run the App, Preview Tool, and Tests

```powershell
# Launch the CircuitSim desktop GUI
.\.venv\Scripts\python.exe -m circuitsim.main

# Open the IEC symbol & grid alignment preview tool
.\.venv\Scripts\python.exe -m circuitsim.tools.symbol_preview

# Run the headless Milestone 1 engine demo
.\.venv\Scripts\python.exe -m circuitsim.main --demo

# Run the full test suite (71 tests)
.\.venv\Scripts\pytest.exe
```
