# CircuitSim — Desktop Electrical Circuit Simulator

[![CI](https://github.com/EmerikBaltic/circuitsim/actions/workflows/ci.yml/badge.svg)](https://github.com/EmerikBaltic/circuitsim/actions/workflows/ci.yml)

**CircuitSim** is an open-source, educational desktop electrical circuit simulator built with **Python 3.11+**, **NumPy / SciPy** (Modified Nodal Analysis physics engine), and **PySide6 (Qt 6 Widgets)**.

It is designed for electrical engineering students and hobbyists who want both an interactive schematic capture + virtual instrument bench and a clean, readable Python codebase that demonstrates how real circuit simulators (like SPICE) work under the hood.

---

## Current Project Status: Milestone 2 Complete

- **Milestone 1 (Simulation Engine — Complete)**:
  - Pure-Python/NumPy/SciPy **Modified Nodal Analysis (MNA)** solver with cached LU factorization (`scipy.linalg.lu_factor` / `lu_solve`), strictly decoupled from Qt.
  - **DC Operating Point** and **Transient Analysis** using **Trapezoidal integration** (second-order accurate, lossless on undamped $LC$ tanks) with automatic **Backward Euler** startup and switch-event damping to eliminate numerical ringing.
  - **Components**: Resistor, Capacitor (with initial voltage & ESR), Inductor (with winding resistance DCR, reactance $X_L = 2\pi f L$, and automatic Thévenin time constant $\tau = L / (R_{\text{th}} + \text{DCR})$), DC Voltage & Current Sources, AC Voltage Source (sine, square, triangle, sawtooth, pulse, DC offset), SPST Switch ($1\text{ m}\Omega$ ON, $1\text{ G}\Omega$ OFF, timed switching, $10\text{ pF}$ contact capacitance, and $350\text{ V}$ contact breakdown arc model), Incandescent Lightbulb ($R_{\text{hot}} = V^2/P$ and optional thermal filament inrush model), Light-Emitting Diode (LED) with real-world colour presets and forward voltages, perceptual glow, over-current warnings, and burnout modeling, and polarity-aware Voltmeter ($10\text{ M}\Omega$) & Ammeter ($1\text{ m}\Omega$) with DC, AC RMS, Peak, and Instantaneous modes.
  - **Topological & Component Diagnostics**: Structured what/why/how detection of missing ground, floating/dangling nodes, ideal voltage-source loops, ammeters connected in parallel across voltage sources, reversed LEDs, missing current-limiting resistors, LED over-current, and inductive kickback warnings in the dedicated Problems Panel (`F8`).
- **Milestone 2 (Main Window, Interactive Schematic Canvas & Live Simulation — Complete)**:
  - Dockable **PySide6 (Qt 6)** Main Window with Dark & Light themes (`Ctrl+T`), searchable Component Palette, and IEC 60617 symbol library (hybrid custom SVG + procedural renderer).
  - Grid-snapped ($20\text{ px}$) schematic canvas with right-angle wire routing, Union-Find netlist extraction (`CircuitScene.build_circuit()`), explicit junction dots (`J`), attached wire re-routing on move/rotate/flip, and full `QUndoStack` Undo/Redo (`Ctrl+Z` / `Ctrl+Y`).
  - Background `QThread` simulation worker (`SimulationWorkerController` + pure-Python `SimulationSession`) with live auto-ranged Voltmeter/Ammeter readouts, animated clickable Switch, real-power Lightbulb glow, double-click live value editing (supporting both dot and single-comma decimals like `5,65 G`), and red/amber canvas problem highlighting.
  - **277 automated unit and UI tests** passing (`pytest`), including polarity geometry across all 8 orientations, precision hitboxes and click clearance, collision-avoiding wire rerouting, half-grid (10 px) wire snapping, view stability on selection/clicks, unified drawing/netlist polarity marks, full LED lifecycle and perceptual glow, Problems Panel (`F8`), paint safety guards and loop-free crash handling, and save/load of `.circ` files (Milestone 3, Step 3A).
- **Milestone 3 (Save/Load `.circ` & Full Properties Dialog — In Progress)**

---

## How to Use

1. **Place Parts**: Click or drag a part from the left **Component Palette** onto the schematic canvas (or double-click a palette item to place it at the center). Always include a **Ground** part wired to your circuit.
2. **Rotate & Flip**: Select one or more parts and press **`R`** to rotate $90^\circ$ clockwise or **`F`** to flip horizontally. Labels and values stay upright and readable at any angle.
3. **Draw Wires**: Click directly on any component terminal dot to start a right-angle wire, or press **`W`** to enter Wire Mode (`Esc` returns to Select Mode). Crossing wires do *not* connect unless they form a T-junction or you place a **Junction Dot** (**`J`**).
4. **Edit Component Values**: **Double-click** any component on the canvas to open its value editor. Type values using engineering prefixes (`4.7k`, `5,65 G`, `100n`, `10K`)—a live preview (`= 4.7 kΩ`) appears below the input, and changes apply immediately even while the simulation is running (and can be undone with **`Ctrl+Z`**).
5. **Run / Pause / Stop**: Use the top toolbar or keyboard shortcuts—**Run (`F5`)**, **Pause / Resume (`F6` or `Space`)**, and **Stop (`F7`)**—and choose simulation speed (`1x Real-Time`, `0.1x Slow`, `10x Fast`).
6. **Toggle Switches Live**: Click directly on any **Switch** on the canvas while running to animate its lever open/closed and watch meter readings and lightbulb brightness respond in real time.

---

## Saving and Opening Circuits

Circuits are stored as `.circ` files (plain JSON text that you can open in any editor).

- **Save**: `Ctrl+S` (or the toolbar **Save** button). The first time you are asked for a name; `Ctrl+Shift+S` (**Save As**) always asks.
- **Open**: `Ctrl+O`. **New**: `Ctrl+N`.
- **Open Recent**: `File > Open Recent` preserves the last 8 opened circuits.
- **Example Circuits**: `File > Examples` loads bundled reference schematics (Voltage Divider, RC Low-Pass Filter, Lightbulb & Switch, Series Sources, Wheatstone Bridge).
- **Export Schematic**: `File > Export as PNG...` and `File > Export as SVG...` export clean high-resolution schematics with White or Theme canvas backgrounds.
- **Zoom to Fit**: `View > Zoom to fit` (`Ctrl+0`) frames the whole circuit cleanly.
- **Preferences**: `Edit > Preferences` configures regional decimal number formatting (Auto, Dot, Comma).
- **Help & Diagnostics**: `Help > About` displays software and platform versions, while unhandled crashes are logged safely to the user app-data folder.
- The window title shows the file name and an asterisk (`*`) when there are unsaved changes. CircuitSim asks before New, Open or closing if you would lose changes.
- Saving is safe: the file is written to a temporary file first and only then swapped in, and the previous version is kept as `yourfile.circ.bak`.
- A damaged, empty or unknown file (or one made by a newer CircuitSim) shows a friendly message and leaves your current circuit untouched.
- Saved with the file: parts, values, labels, rotation/flip, wires, junction dots, theme, zoom, view position and simulation speed.

---

## Screenshots

> *Placeholder — drop screenshots of the schematic canvas, live simulation, and theme views into `docs/screenshots/` and link them here:*
>
> - `[Screenshot: Dark Theme Schematic & Live Meters]`
> - `[Screenshot: Lightbulb Glow & Double-Click Value Editor]`
> - `[Screenshot: Light Theme & Canvas Problem Highlighting]`

---

## Quick Start & Installation

### 1. Clone the Repository and Create a Virtual Environment

```powershell
git clone https://github.com/<your-username>/circuitsim.git
cd circuitsim
python -m venv .venv
```

### 2. Install Dependencies and `circuitsim` in Editable Mode

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pip.exe install -e .
```

### 3. Run the Unit Test Suite

```powershell
.\.venv\Scripts\pytest.exe
```

### 4. Run the Application / Engine Demo

```powershell
.\.venv\Scripts\python.exe -m circuitsim.main
```

---

## Development Roadmap

| Milestone | Scope | Status |
|-----------|-------|--------|
| **Milestone 1** | Core MNA DC & Transient Engine, R/L/C, Sources, Switch, Bulb, Meters, Parser, Analytical Tests | **Done** |
| **Milestone 2** | Dockable Main Window, Component Palette, Interactive IEC Schematic Canvas, Worker Thread, Live Meters/Switch/Bulb | **Done** |
| **Milestone 3** | Double-Click Live Properties Dialog, Inductor $X_L / \tau$ Calculator, `.circ` JSON Save/Load (Saved Parts bar cancelled) | **In Progress** |
| **Milestone 4** | 4-Channel Oscilloscope (Probes, Trigger, Cursors, Automatic Measurements, X-Y Mode, Math & FFT, PNG/CSV Export) | Planned |
| **Milestone 5** | Semiconductors (Diode, Zener, LED, BJT, MOSFET, Op-Amp via Newton-Raphson), Current Animation, Themes, SPICE Import/Export, Packaging | Planned |

---

## Project Structure

```text
CircuitSim/
├── LICENSE
├── README.md
├── PROGRESS.md
├── LEARNING_NOTES.md
├── SUGGESTIONS.md
├── AGENT_INSTRUCTIONS.md
├── circuit_simulator_specification.txt
├── requirements.txt
├── pyproject.toml
├── src/circuitsim/
│   ├── main.py
│   ├── app/            main window, docks, menus, settings
│   ├── canvas/         scene, view, wire item, component item
│   ├── components/     resistor, capacitor, inductor, bulb, switch, meters...
│   ├── dialogs/        properties dialog, engineering-notation value parser
│   ├── scope/          scope widget, trigger, measurements, FFT
│   ├── engine/         netlist builder, MNA matrix, integrators, Newton solver
│   ├── io/             JSON save/load, SPICE import/export, image export
│   └── resources/      icons, themes (QSS), example circuits, symbols/iec/
└── tests/              solver tests, parser tests, transient & reactive tests
```

---

## Licensing & Third-Party Libraries

- **CircuitSim** is released under the [MIT License](LICENSE).
- **PySide6 (Qt for Python)** is licensed under the **LGPLv3**.
- **NumPy** and **SciPy** are licensed under the **BSD 3-Clause License**.
