# CircuitSim — Desktop Electrical Circuit Simulator

An educational desktop electrical circuit simulator built with **Python 3.11+**, **NumPy / SciPy** (Modified Nodal Analysis solver), and **PySide6 (Qt 6 Widgets)**.

## Quick Start

### 1. Create and Activate the Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### 2. Run the Unit Tests

```powershell
.\.venv\Scripts\pytest.exe
```

### 3. Run the Application

```powershell
.\.venv\Scripts\python.exe -m circuitsim.main
```

## Project Structure

```text
CircuitSim/
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
│   ├── savedparts/     saved parts bar (10 slots, JSON persistence)
│   ├── scope/          scope widget, trigger, measurements, FFT
│   ├── engine/         netlist builder, MNA matrix, integrators, Newton solver
│   ├── io/             JSON save/load, SPICE import/export, image export
│   └── resources/      icons, themes (QSS), example circuits
└── tests/              solver tests, parser tests, saved-parts tests
```

## Licensing & Third-Party Libraries

- **PySide6 (Qt for Python)** is licensed under the **LGPLv3**.
- **NumPy** and **SciPy** are licensed under the **BSD 3-Clause License**.
