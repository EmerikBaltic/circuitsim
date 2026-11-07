# Project Progress — CircuitSim

## Current Status: Milestone 1 Complete (Step A + Step B)

### What Is Done
- **Environment & Editable Package Installation**:
  - Local Python 3.12 virtual environment (`.venv`) with `PySide6`, `numpy`, `scipy`, and `pytest`.
  - Project is installed in editable mode (`pip install -e .`) so `python -m circuitsim.main` and `pytest` work directly without setting `PYTHONPATH`.
- **Engineering-Notation Value Parser (`src/circuitsim/dialogs/value_parser.py`)**:
  - Case-sensitive engineering prefixes (`p`, `n`, `u`/`µ`, `m` = $10^{-3}$, `k`, `M`/`meg` = $10^6$, `G`), SPICE-compatible parser (`parse_spice_value`), and auto-ranging formatter (`format_engineering_value`).
- **Component Physics Models (`src/circuitsim/components/`)**:
  - `Ground`, `Resistor`, `Capacitor` (with initial voltage and series `esr` folded into the companion stamp), `Inductor` (with series `dcr` folded into its branch equation, $\text{DCR}_{\min} = 1\text{ m}\Omega$ at DC, $X_L = 2\pi f L$, $L$ calculator helper, and $\tau = L / (R_{\text{thevenin}} + \text{DCR})$).
  - `DCVoltageSource`, `DCCurrentSource`, `ACVoltageSource` (`sine`, `square`, `triangle`, `sawtooth`, `pulse`, with phase, duty cycle, and DC offset).
  - `Switch` ($1\text{ m}\Omega$ ON, $1\text{ G}\Omega$ OFF, timed switching, $10\text{ pF}$ contact capacitance companion model), `Lightbulb` ($R_{\text{hot}} = V_{\text{rated}}^2 / P_{\text{rated}}$, optional thermal filament model, burnout tracking), `Voltmeter` ($10\text{ M}\Omega$ default), and `Ammeter` ($1\text{ m}\Omega$ default).
  - Strictly decoupled from Qt (`PySide6` is never imported in `components/` or `engine/`).
- **MNA DC & Transient Solver (`src/circuitsim/engine/`)**:
  - Topological validation for missing ground, floating/dangling nodes, ideal voltage-source loops, and parallel ammeters, plus runtime detection for inductive kickback (`"Inductive kickback, consider a flyback diode"`).
  - Exact DC Thévenin resistance calculator (`Circuit.thevenin_resistance`) with all independent sources zeroed.
  - Transient analysis (`step_transient` and `solve_transient`) using companion models, **Backward Euler** on the first step and upon any switch event, and **Trapezoidal integration** on normal steps, with cached `scipy.linalg.lu_factor` / `lu_solve` factorization reuse.
- **Unit Test Suite (`tests/`)**:
  - **55 passing tests** covering value parsing, DC resistor networks, Wheatstone bridges, 60 W / 120 V lightbulb, switch states, meter modes, matrix conditioning, RC step charging, RL current rise with Thévenin resistance, RLC series resonance, AC RMS meter verification of inductive reactance $X_L = 2\pi f L$, lossless LC oscillation (zero numerical damping), 1st-order vs 2nd-order convergence rates, switch-event ringing elimination, and inductive kickback warnings.

### What Is Next (Milestone 2 — Main Window and Canvas)
- Dockable main window layout (`QMainWindow`, `QDockWidget`).
- Component palette with categories, search box, and drag-and-drop ghost preview with grid snapping.
- Interactive schematic canvas (`QGraphicsView` / `QGraphicsScene`): grid, zoom, pan, box selection, rotate (`R`), flip (`F`), delete, copy/paste, undo/redo (`QUndoStack`), right-angle wire routing, and junction dots.
- Worker thread (`QThread`) connecting Run / Pause / Stop to the MNA engine without freezing the UI.
- Live problem highlighting on the canvas, clickable switch with animated lever, glowing lightbulb, and live voltmeter/ammeter readouts.

### Known Issues & Limitations
- Inductive kickback currently models the $10\text{ pF}$ switch contact capacitance and raises the `"Inductive kickback, consider a flyback diode"` warning, without clamping the voltage spike until an arc/breakdown clamp threshold is approved.
- No graphical UI yet (Milestone 2).

### How to Run the App and Tests

```powershell
# Run the full test suite (55 tests)
.\.venv\Scripts\pytest.exe

# Run the headless Milestone 1 engine demo (no PYTHONPATH needed)
.\.venv\Scripts\python.exe -m circuitsim.main
```
