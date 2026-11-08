# Project Progress — CircuitSim

## Current Status: Milestone 1 Complete (Step A + Step B + Follow-ups)

### What Is Done
- **Environment, Licensing & Editable Package Installation**:
  - Local Python 3.12 virtual environment (`.venv`) with `PySide6`, `numpy`, `scipy`, and `pytest`.
  - Project is installed in editable mode (`pip install -e .`) and includes an MIT [`LICENSE`](LICENSE) and updated [`README.md`](README.md).
- **Engineering-Notation Value Parser (`src/circuitsim/dialogs/value_parser.py`)**:
  - Case-sensitive engineering prefixes (`p`, `n`, `u`/`µ`, `m` = $10^{-3}$, `k`, `M`/`meg` = $10^6$, `G`), SPICE-compatible parser (`parse_spice_value`), and auto-ranging formatter (`format_engineering_value`).
- **Component Physics Models (`src/circuitsim/components/`)**:
  - `Ground`, `Resistor`, `Capacitor` (with initial voltage and series `esr` folded into the companion stamp), `Inductor` (with series `dcr` folded into its branch equation, $\text{DCR}_{\min} = 1\text{ m}\Omega$ at DC, $X_L = 2\pi f L$, $L$ calculator helper, and $\tau = L / (R_{\text{thevenin}} + \text{DCR})$).
  - `DCVoltageSource`, `DCCurrentSource`, `ACVoltageSource` (`sine`, `square`, `triangle`, `sawtooth`, `pulse`, with phase, duty cycle, and DC offset).
  - `Switch` ($1\text{ m}\Omega$ ON, $1\text{ G}\Omega$ OFF, timed switching, $10\text{ pF}$ contact capacitance, and configurable $350\text{ V}$ default contact breakdown arc clamp with holding-current extinction).
  - `Lightbulb` ($R_{\text{hot}} = V_{\text{rated}}^2 / P_{\text{rated}}$, optional thermal filament model, burnout tracking), `Voltmeter` ($10\text{ M}\Omega$ default), and `Ammeter` ($1\text{ m}\Omega$ default) with exact whole-period sliding-window RMS, DC, Peak, and Instantaneous modes.
- **MNA DC & Transient Solver (`src/circuitsim/engine/`)**:
  - Topological validation for missing ground, floating/dangling nodes, ideal voltage-source loops, and parallel ammeters, plus runtime detection for inductive kickback (`"Inductive kickback, consider a flyback diode"`).
  - Exact DC Thévenin resistance calculator (`Circuit.thevenin_resistance`) with all independent sources zeroed.
  - Transient analysis (`step_transient` and `solve_transient`) using companion models, **Backward Euler** on the first step and upon any switch or arc ignition/extinction event, and **Trapezoidal integration** on normal steps, with cached `scipy.linalg.lu_factor` / `lu_solve` factorization reuse.
- **IEC Symbol Resource Directory (`src/circuitsim/resources/symbols/iec/`)**:
  - Created and documented grid/metadata/SVG conventions for Milestone 2.
- **Unit Test Suite (`tests/`)**:
  - **56 passing tests** covering all Milestone 1 requirements and analytical verification formulas.

### What Is Next (Milestone 2 — Main Window and Canvas)
- **Step 2A**: Main window (`QMainWindow`), dockable panels (`QDockWidget`), IEC symbol loader (SVG + JSON metadata with procedural IEC fallback and dark/light theme recolouring), component palette with search/categories, and interactive `QGraphicsView` canvas (grid, zoom, pan, drag-and-drop with snapping ghost preview).
- **Step 2B**: Schematic editing and wiring (rotate `R`, flip `F`, box selection, delete, copy/paste, `QUndoStack` undo/redo, terminal click-drag right-angle wire routing, junction dots).
- **Step 2C**: Background worker thread (`QThread`) simulation loop (Run / Pause / Stop), live problem highlighting on the canvas, clickable animated switch, glowing lightbulb, and live voltmeter/ammeter readouts.

### Known Issues & Limitations
- No graphical UI yet (starts in Milestone 2 Step 2A upon plan approval).

### How to Run the App and Tests

```powershell
# Run the full test suite (56 tests)
.\.venv\Scripts\pytest.exe

# Run the headless Milestone 1 engine demo
.\.venv\Scripts\python.exe -m circuitsim.main
```
