# Project Progress — CircuitSim

## Current Status: Milestone 1 — Step A Complete

### What Is Done (Milestone 1 — Step A)
- **Environment & Project Skeleton**:
  - Local Python 3.12 virtual environment (`.venv`) with `PySide6`, `numpy`, `scipy`, and `pytest`.
  - Standard package layout under `src/circuitsim/` and `tests/`, plus `.gitignore`, `pyproject.toml`, `requirements.txt`, and `README.md`.
- **Engineering-Notation Value Parser (`src/circuitsim/dialogs/value_parser.py`)**:
  - Case-sensitive engineering prefixes (`p`, `n`, `u`/`µ`, `m` = $10^{-3}$, `k`, `M`/`meg` = $10^6$, `G`) with unit stripping (`Ohm`, `Ω`, `V`, `A`, `W`, `F`, `H`, `Hz`, `s`).
  - SPICE-compatible case-insensitive value parser (`parse_spice_value`) and auto-ranging formatter (`format_engineering_value`).
- **Component Physics Models (`src/circuitsim/components/`)**:
  - `Ground`, `Resistor`, `DCVoltageSource` (with optional internal resistance), `DCCurrentSource`, `Switch` ($1\text{ m}\Omega$ ON, $1\text{ G}\Omega$ OFF, timed switching), `Lightbulb` ($R_{\text{hot}} = V_{\text{rated}}^2 / P_{\text{rated}}$, optional thermal filament model, burnout tracking, brightness calculation), `Voltmeter` ($10\text{ M}\Omega$ default), and `Ammeter` ($1\text{ m}\Omega$ default).
  - Strictly decoupled from Qt (`PySide6` is never imported in `components/` or `engine/`).
- **DC Modified Nodal Analysis (MNA) Solver & Topology Validator (`src/circuitsim/engine/`)**:
  - Pre-solve topological validation for `"No ground connected"`, `"Node X is floating"` (both disconnected islands and single-terminal dangling nodes), `"Voltage sources in a loop"`, and `"Ammeter X is connected in parallel across a voltage source or short circuit"`.
  - MNA matrix builder with `GMIN = 1e-12 S` from every node to ground and cached LU factorization via `scipy.linalg.lu_factor` / `lu_solve`.
- **Unit Tests (`tests/`)**:
  - 46 passing tests covering value parsing, voltage dividers, Wheatstone bridges, parallel current dividers, 60 W / 120 V lightbulb specification, thermal filament inrush, switch state & LU cache reuse, meter polarity/ranging, extreme matrix conditioning ($1\text{ m}\Omega$ + $1\text{ G}\Omega$ + `GMIN`), and topology error detection.

### What Is Next (Milestone 1 — Step B)
- `Capacitor` (with initial voltage and optional ESR) and `Inductor` (with winding resistance DCR folded directly into the branch equation and minimum DC resistance $\approx 1\text{ m}\Omega$, plus $X_L = 2\pi f L$, $L$ helper, and $\tau = L / R_{\text{total}}$).
- `ACVoltageSource` (sine, square, triangle, sawtooth, pulse with duty cycle, frequency, phase, and DC offset).
- Transient MNA solver (`solve_transient` / step-by-step execution) using **Trapezoidal integration** on normal steps and **Backward Euler** on the first step and immediately after any switch event.
- Analytical transient unit tests: RC charging curve, RL current rise, RLC resonance, and AC inductive reactance ($X_L = 2\pi f L$) verified against AC RMS voltmeter and ammeter readings.

### Known Issues & Limitations
- Only DC analysis and Step A components are active so far; reactive components (`Capacitor`, `Inductor`), `ACVoltageSource`, and transient integration are scheduled for Milestone 1 Step B.
- No graphical user interface yet (scheduled for Milestone 2).

### How to Run the App and Tests

```powershell
# Run the full test suite (46 tests)
.\.venv\Scripts\pytest.exe

# Run the headless Step A engine demo
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m circuitsim.main
```
