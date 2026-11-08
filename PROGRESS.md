# Project Progress — CircuitSim

## Current Status: Milestone 2 — Step 2A Complete

### What Is Done
- **Environment, Licensing & Editable Package Installation**:
  - Local Python 3.12 virtual environment (`.venv`) with `PySide6`, `numpy`, `scipy`, and `pytest`.
  - Project is installed in editable mode (`pip install -e .`) and includes an MIT [`LICENSE`](LICENSE) and updated [`README.md`](README.md).
- **Milestone 1 — Core Physics & MNA Engine (`src/circuitsim/components/`, `src/circuitsim/engine/`, `src/circuitsim/dialogs/value_parser.py`)**:
  - Engineering-notation parser (`parse_spice_value`, `format_engineering_value`).
  - All 11 Milestone 1 & 2 components (`Ground`, `Resistor`, `Capacitor`, `Inductor`, `DCVoltageSource`, `DCCurrentSource`, `ACVoltageSource`, `Switch` with $350\text{ V}$ contact breakdown arc clamp, `Lightbulb`, `Voltmeter`, `Ammeter`).
  - DC and Transient MNA solver (`Circuit`, `MNASolver`) with topology validation, `thevenin_resistance`, Backward Euler switching/arc settling, and Trapezoidal integration.
- **Milestone 2 — Step 2A: Main Window, IEC Symbol System, Palette & Schematic Canvas**:
  - **IEC Symbol Metadata & Convention (`src/circuitsim/resources/symbols/iec/`)**:
    - 11 JSON metadata files defining `4x2` grid footprints (`80x40 px`, terminals at `[-2, 0]` and `[+2, 0]`) for 2-terminal components and `2x2` (`40x40 px`, terminal at `[0, -1]`) for Ground, plus multi-state definitions for Switch (`open`, `closed`) and Lightbulb (`normal`, `lit`, `burned_out`).
    - Documented SVG convention in [`src/circuitsim/resources/symbols/iec/README.md`](src/circuitsim/resources/symbols/iec/README.md) supporting both `viewBox="0 0 80 40"` and centered `viewBox="-40 -20 80 40"`.
  - **Pure-Python Symbol Geometry & Tolerant SVG Loader (`src/circuitsim/canvas/symbol_geometry.py`)**:
    - Grid snapping (`snap_to_grid`), terminal world-coordinate math under 90° rotations and horizontal flips (`transform_terminal_px`), and tolerant XML/SVG validation and theme recolouring (`validate_and_prepare_svg`) that strips Inkscape/Figma metadata and background rects, recolours `#000000`/`currentColor`, and falls back to procedural IEC symbols with a readable warning on malformed or mismatched SVGs.
  - **Hybrid SVG / Procedural IEC Renderer (`src/circuitsim/canvas/symbol_renderer.py`)**:
    - Renders custom SVGs via `QSvgRenderer` when present, or clean IEC 60617 procedural graphics via `QPainter` when absent, in both Dark and Light themes.
  - **Interactive Schematic Canvas (`src/circuitsim/canvas/scene.py`, `view.py`, `component_item.py`)**:
    - `CircuitScene` and `CircuitView` with 20 px minor / 100 px major grid, mouse-wheel zoom around cursor (`0.25x` to `4.0x`), middle-click or `Space`+drag pan, drag-and-drop placement with a translucent grid-snapping ghost preview, movable components, `R` to rotate 90° CW, and `F` to flip horizontally.
  - **Dockable Main Window & Palette (`src/circuitsim/app/main_window.py`, `palette_dock.py`, `themes.py`)**:
    - Full Section 2 layout: menus, simulation toolbar, Saved Parts quick bar, left Component Palette dock with live search filter and collapsible categories, right Inspector dock, bottom Oscilloscope & Formulas dock, status bar with cursor grid coordinates, and instant Dark/Light theme switching (`Ctrl+T`).
  - **Symbol Preview Tool (`src/circuitsim/tools/symbol_preview.py`)**:
    - Standalone viewer (`python -m circuitsim.tools.symbol_preview`) and PNG exporter (`--export`) showing every symbol and state in both Dark and Light themes with the 20 px grid and terminal alignment dots overlaid.
- **Unit Test Suite (`tests/`)**:
  - **62 passing tests** (56 engine/physics tests + 6 symbol metadata, geometry, snapping, and tolerant SVG loader tests).

### What Is Next (Milestone 2 — Remaining Steps)
- **Step 2B**: Schematic editing and wiring — rubber-band box selection, Delete (`Del`/`Backspace`), Copy/Paste (`Ctrl+C`/`Ctrl+V`), `QUndoStack` Undo/Redo (`Ctrl+Z`/`Ctrl+Y`), click-and-drag right-angle wire routing between terminals, junction dots, and netlist extraction.
- **Step 2C**: Live simulation loop (`QThread` worker behind a clean process-ready interface), Run/Pause/Stop controls, problem highlighting on canvas, clickable animated switch, glowing lightbulb, and live voltmeter/ammeter readouts.

### Known Issues & Limitations
- Wires cannot be drawn yet and the Run/Pause/Stop toolbar buttons are placeholders until Steps 2B and 2C.

### How to Run the App, Preview Tool, and Tests

```powershell
# Launch the CircuitSim desktop GUI
.\.venv\Scripts\python.exe -m circuitsim.main

# Open the IEC symbol & grid alignment preview tool
.\.venv\Scripts\python.exe -m circuitsim.tools.symbol_preview

# Run the headless Milestone 1 engine demo
.\.venv\Scripts\python.exe -m circuitsim.main --demo

# Run the full test suite (62 tests)
.\.venv\Scripts\pytest.exe
```
