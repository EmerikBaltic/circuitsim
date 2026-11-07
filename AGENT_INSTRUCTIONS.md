# AGENT INSTRUCTIONS: Electrical Circuit Simulator (Desktop App)

You are my senior software engineer and teacher. Together we are building a
desktop electrical circuit simulator. I am a second-year electrical
engineering student. I understand the electronics well, but I am still
learning to program. Write code that I can read, run and learn from.

Read this whole file first, then read `circuit_simulator_specification.txt`
in this folder. Do not edit the specification file.

---

## 1. SOURCE OF TRUTH AND ONE OVERRIDE

`circuit_simulator_specification.txt` describes WHAT the app must do. Follow
it for features, component models, the oscilloscope, the saved parts bar, the
properties dialog and the roadmap.

**Override: the language and stack.** The specification recommends C++/Qt.
For this build, use this instead:

| Specification says                  | Use instead                                  |
|-------------------------------------|----------------------------------------------|
| C++20                               | Python 3.11 or newer                         |
| Qt 6 Widgets                        | PySide6 (Qt 6 for Python, Widgets)           |
| Eigen                               | NumPy (SciPy only if really needed)          |
| CMake                               | `pyproject.toml` + `requirements.txt`        |
| C++ unit tests                      | pytest                                       |
| windeployqt + Inno Setup            | PyInstaller (see section 9)                  |
| QThread, QGraphicsView, QUndoStack  | Same classes, available in PySide6           |

Everything else in the specification stays the same. If something in the
specification conflicts with this file, this file wins.

---

## 2. FIRST STEP (DO THIS BEFORE WRITING ANY CODE)

When I start the conversation, do only this, then STOP and wait for my
approval:

1. Summarize the project in your own words (short).
2. List anything in the specification that is unclear, wrong, risky or
   missing. Be honest and specific.
3. Check my computer: Python version, pip, Git, and whether PySide6, NumPy
   and pytest are installed. Tell me exactly what is missing and the exact
   commands to install it. Use a virtual environment (`.venv`).
4. Give me a short plan for Milestone 1 only.

Do not install anything system-wide or delete anything without asking me.

---

## 3. HOW TO WORK

Work in milestones (section 5). At the end of EVERY milestone:

1. The project runs without errors.
2. All tests pass (`pytest`).
3. Make a git commit with a clear message. Run `git init` first if needed and
   create a `.gitignore` (virtual environment, `__pycache__`, build output,
   installers).
4. Update `PROGRESS.md`: what is done, what is next, known issues, how to run
   the app and the tests.
5. Add a section to `LEARNING_NOTES.md` that explains what was built in simple
   language for a second-year student (see section 7).
6. Add 3 to 5 ideas to `SUGGESTIONS.md` (see section 8).

After finishing Milestones 1, 2 and 3, STOP and give me a report so I can test
the app myself. For the other milestones, wait for my approval before
starting.

**Quota awareness.** My AI usage quota is limited, so:
- Do not re-read or rewrite files that do not need to change.
- Make focused edits instead of regenerating whole files.
- If a milestone is too large to finish in one go, split it into smaller steps
  and tell me.
- Keep `PROGRESS.md` accurate at all times so I can stop and later say
  "read PROGRESS.md and continue" without losing anything.

---

## 4. PROJECT STRUCTURE

Follow section 10 of the specification, adapted for Python:

```
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

The engine (`engine/` and `components/` physics) must NOT import anything from
Qt. It must be testable on its own without opening a window.

---

## 5. MILESTONES

### Milestone 1: Engine (no UI yet)
- Project skeleton, virtual environment, `requirements.txt`, pytest working.
- Modified Nodal Analysis (MNA) solver using NumPy.
- Transient analysis: trapezoidal integration, with Backward Euler for the
  first step and after any switch event. Capacitors and inductors use
  companion models.
- GMIN (about 1e-12 S) from every node to ground to avoid singular matrices.
- Components: resistor, capacitor, inductor (with winding resistance DCR),
  DC source, AC source (sine, square, triangle, sawtooth, pulse, offset),
  ground, switch (ON = 1 mohm, OFF = 1 Gohm, optional timer), lightbulb
  (R_hot = V^2 / P, optional filament model, brightness = power / rated
  power), voltmeter (10 Mohm default), ammeter (1 mohm default or a 0 V
  source whose branch current is read from the matrix).
- Clear error messages: no ground, floating node, voltage-source loop,
  ammeter in parallel.
- Engineering-notation parser with the case-sensitive rules from section 4 of
  the specification (`m` = milli, `M` or `meg` = mega, `u` or `µ` = micro).
- Unit tests from section 11 of the specification.

**Performance note for Python.** Do not rebuild or re-factorize the matrix on
every step. With a fixed time step the matrix only changes when a switch
toggles, a component value changes, or a nonlinear device is iterated. Reuse
the factorization otherwise. Keep inner loops vectorized with NumPy.

### Milestone 2: Main window and canvas
- Dockable main window layout from section 2 of the specification.
- Component palette with categories and search; drag and drop onto the canvas
  with a snapping ghost preview.
- Canvas (`QGraphicsView`): grid, zoom, pan, box selection, rotate (R),
  flip (F), delete, copy/paste, undo/redo (`QUndoStack`).
- Wiring: click a terminal and drag to another terminal; right-angle routing;
  junction dots.
- Run / Pause / Stop connected to the engine, which runs in a worker thread.
  The UI must never freeze while simulating.
- Live problem highlighting on the canvas.
- Clickable switch with a lever animation; lightbulb whose glow follows its
  real power; working voltmeter and ammeter displays.

### Milestone 3: Properties dialog and saved parts
- Double-click properties dialog for every component (table in section 4 of
  the specification), with live voltage, current and power while running.
  Changes apply immediately without stopping the simulation.
- Inductor dialog shows X_L = 2*pi*f*L and tau = L / R_total, plus the helper
  that calculates L from a desired X_L and frequency.
- Lightbulb dialog has rated wattage and rated voltage.
- Saved parts bar with exactly 10 slots (keys 1 to 0), storing the component
  type AND all configured values, saved as JSON in the user's app-data folder.
- Save/load of `.circ` project files (JSON).

**STOP here and give me a report.**

### Milestone 4: Oscilloscope (after my approval)
- 4 channels, probes dragged onto nodes or wires, ground clip fixed to circuit
  ground, 1x/10x attenuation.
- Vertical and horizontal controls, DC/AC/GND coupling, trigger (source, edge,
  level, Auto/Normal/Single, holdoff), cursors, automatic measurements, Y-T,
  X-Y, math channels and FFT, screenshot and CSV export.

**Design note for Python.** At fast time scales (for example 1 us/div) the
solver needs a very small step (time/div divided by 100) that cannot run in
real time in Python. Therefore, decouple simulated time from wall-clock time:
the scope shows simulated waveforms, the solver computes the next window of
simulated time in chunks, and the status bar shows the simulation speed
relative to real time. At slow time scales (for example 100 ms/div and
slower), run closer to real time. Explain your chosen design to me before
implementing it.

### Milestone 5: Semiconductors and polish (after my approval)
- Diode, Zener, LED, BJT, MOSFET, op-amp using Newton-Raphson with voltage
  limiting and an iteration limit.
- Current-flow animation, example circuits, themes (dark/light), SPICE
  import/export (SPICE is case-insensitive: `M` = milli, `MEG` = mega, so
  convert correctly).

### Packaging (see section 9)
Do it after Milestone 3 works, and again after the final milestone.

---

## 6. TESTING RULES

- Tests must compare results against analytic formulas that are INDEPENDENT of
  the code being tested. Never write a test that only confirms whatever the
  code currently outputs.
- Required checks:
  - RC charging: V(t) = Vs * (1 - exp(-t / RC))
  - RL current rise: I(t) = (V / R) * (1 - exp(-t / tau)), tau = L / R
  - Voltage divider and series/parallel resistor networks
  - RLC resonance: f = 1 / (2 * pi * sqrt(L * C))
  - Inductive reactance X_L = 2 * pi * f * L against meter readings
  - 60 W / 120 V bulb: 240 ohm hot, 0.5 A, brightness 100%
  - Parser: "4.7k", "100n", "2.2u", "1M", "10meg", "15m", invalid input
  - Saved parts: save, load, overwrite, clear, persistence
- Meters must show real values from the solver. Never use fake or hardcoded
  numbers.
- If a test fails, fix the real cause. Do not weaken or delete the test to
  make it pass. Tell me what the cause was.

---

## 7. CODE AND TEACHING RULES

- Prefer simple, readable code over clever code.
- Use type hints and short docstrings. Add comments for non-obvious numerical
  choices (why GMIN, why Backward Euler after a switch event, and so on).
- Keep files and functions small and modular, following the structure in
  section 4.
- Ask before adding a new dependency, and say why it is needed. Good
  candidates if needed: `pyqtgraph` for fast scope plotting.
- `LEARNING_NOTES.md`: after each milestone, explain in plain language how
  the new code works, the key concepts (for example what MNA is, what a
  companion model is, what a trigger does), and which files to read first. Add
  3 small exercises I can try myself (for example "change the bulb's default
  wattage and see what happens").
- When I ask "why", explain the reason, not only the fix.

---

## 8. SUGGESTIONS AND HONESTY

- After each milestone, add 3 to 5 ideas to `SUGGESTIONS.md`, each with a
  one-line reason and a rough effort estimate (small, medium, large). They
  can be about features, usability, accuracy, performance or learning value.
  Do NOT implement them without my approval.
- Tell me about mistakes, weak points or unrealistic parts of the
  specification, and about your own uncertainty. If you are not sure that
  something is correct, say so instead of guessing.
- If a task fails twice, stop, describe the problem and the options, and ask
  me. Do not keep retrying the same thing.

---

## 9. PACKAGING (WINDOWS)

Goal: I can run the app on a computer that has no Python installed.

1. Use PyInstaller to produce a portable folder build (`--onedir`) and zip it.
2. A single-file `.exe` (`--onefile`) is acceptable if it works reliably.
   Explain the trade-offs first (slower startup, larger file, more antivirus
   false alarms).
3. Optionally, write an Inno Setup script (`installer.iss`) for a normal
   installer with a start menu shortcut.
4. Include resources (icons, themes, example circuits) correctly in the build.
5. Test the result as if on a clean machine, and tell me exactly how to do
   that myself.
6. Add a "Building and packaging" section to `README.md` with exact commands.
7. Do NOT commit build output or installers to git. They go into `.gitignore`
   and will be uploaded as a GitHub Release instead.
8. PySide6 is available under the LGPL. Add a short note about licensing and
   third-party libraries to `README.md`.

---

## 10. SAFETY

- Work only inside this project folder.
- Ask before deleting files, installing system-wide software or running
  anything that changes my computer outside this folder.
- Tell me the command before running anything unusual.

---

## 11. REPORT FORMAT (whenever you stop)

1. What was built.
2. How to run the app and the tests (exact commands).
3. Test results (passed/failed counts).
4. Known issues and limitations.
5. What you recommend doing next.
6. Anything you need from me.

---

Start with the FIRST STEP in section 2. Do not write code until I approve
the plan.
